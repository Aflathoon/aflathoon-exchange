"""
Rate engine with live API support + layered fallback.

Priority order for a rate:
    1. Fresh live API value (if within RATES_REFRESH_SECONDS)
    2. Last-known-good cache (up to RATES_STALE_AFTER_SECONDS)
    3. Hardcoded FALLBACK_RATES

Source tracking tells the UI whether the number is live or fallback.
"""
import os
import time
import json
import threading
from datetime import datetime, timezone
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Hardcoded baseline (USD = 1.0). Always available.
# ---------------------------------------------------------------------------
FALLBACK_RATES = {
    'USD': 1.0,
    'EUR': 0.92,
    'GBP': 0.79,
    'JPY': 149.50,
    'CHF': 0.88,
    'AUD': 1.52,
    'CAD': 1.36,
    'CNY': 7.24,
    'BTC': 0.000015,
    'ETH': 0.00025,
    'XAU': 0.00048,   # gold
    'WTI': 0.014,     # crude
    'BRENT': 0.0135,  # brent crude
    'NG': 0.030,      # natural gas
}

# Mapping: our symbol -> common API symbol
API_SYMBOLS = {
    'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'JPY': 'JPY',
    'CHF': 'CHF', 'AUD': 'AUD', 'CAD': 'CAD', 'CNY': 'CNY',
    'BTC': 'BTC', 'ETH': 'ETH',
    'XAU': 'XAU',   # gold spot
    'WTI': 'WTI',   # WTI crude
    'BRENT': 'BRENT',
    'NG': 'NG',
}


class RateEngine:
    """Thread-safe rate manager with live fetch + layered fallback."""

    def __init__(self):
        self.margin = float(os.getenv('PLATFORM_MARGIN_PCT', '0.065'))
        self.mode = os.getenv('RATES_MODE', 'demo').lower()
        self.primary = os.getenv('RATES_PRIMARY', 'tickerlayer').lower()
        self.refresh_seconds = int(os.getenv('RATES_REFRESH_SECONDS', '60'))
        self.stale_after = int(os.getenv('RATES_STALE_AFTER_SECONDS', '300'))
        self.http_timeout = int(os.getenv('RATES_HTTP_TIMEOUT', '10'))

        # Layered state
        self._raw_rates = dict(FALLBACK_RATES)   # current best-known raw rates
        self._last_success_ts: Optional[float] = None
        self._last_error: Optional[str] = None
        self._source = 'fallback'                # 'live' | 'cache' | 'fallback'

        self._lock = threading.RLock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ state
    def source_info(self) -> dict:
        with self._lock:
            age = None if self._last_success_ts is None else int(time.time() - self._last_success_ts)
            return {
                'mode': self.mode,
                'source': self._source,
                'last_success_seconds_ago': age,
                'last_error': self._last_error,
                'symbols': sorted(self._raw_rates.keys()),
            }

    # ------------------------------------------------------------------ fetch
    def _fetch_tickerlayer(self) -> Optional[dict]:
        api_key = os.getenv('TICKERLAYER_API_KEY', '').strip()
        if not api_key:
            return None
        base = os.getenv('TICKERLAYER_BASE_URL', 'https://api.tickerlayer.com/v1').rstrip('/')
        symbols = ','.join(API_SYMBOLS[s] for s in FALLBACK_RATES if s != 'USD')
        # Placeholder endpoint shape — align to TickerLayer's actual docs.
        url = f"{base}/rates?base=USD&symbols={symbols}"
        r = requests.get(url, headers={'Authorization': f'Bearer {api_key}'}, timeout=self.http_timeout)
        r.raise_for_status()
        return r.json()

    def _fetch_siftingio(self) -> Optional[dict]:
        api_key = os.getenv('SIFTINGIO_API_KEY', '').strip()
        if not api_key:
            return None
        base = os.getenv('SIFTINGIO_BASE_URL', 'https://api.sifting.io/v1').rstrip('/')
        url = f"{base}/forex/rates?base=USD"
        r = requests.get(url, headers={'X-API-Key': api_key}, timeout=self.http_timeout)
        r.raise_for_status()
        return r.json()

    def _parse_response(self, payload: dict, provider: str) -> Optional[dict]:
        """
        Normalise the API response into {symbol: units_per_usd}.
        Adjust the shape here once you see the real provider payload.
        """
        if not payload:
            return None

        # Try common response shapes
        data = payload.get('rates') or payload.get('data') or payload.get('prices')
        if not isinstance(data, dict):
            return None

        out = {'USD': 1.0}
        for sym in FALLBACK_RATES:
            if sym == 'USD':
                continue
            api_sym = API_SYMBOLS.get(sym, sym)
            val = data.get(api_sym)
            if val is None:
                continue
            try:
                f = float(val)
                if f > 0:
                    # Conventions differ: some APIs return units-per-USD directly,
                    # others return USD-per-unit. We assume the former; flip if not.
                    out[sym] = f
            except (TypeError, ValueError):
                continue
        return out if len(out) > 1 else None

    def _refresh_once(self) -> None:
        if self.mode != 'live':
            with self._lock:
                self._source = 'fallback'
            return

        payload = None
        err = None
        try:
            if self.primary == 'tickerlayer':
                payload = self._fetch_tickerlayer()
                if payload is None:
                    payload = self._fetch_siftingio()
            else:
                payload = self._fetch_siftingio()
                if payload is None:
                    payload = self._fetch_tickerlayer()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        parsed = self._parse_response(payload, self.primary) if payload else None

        with self._lock:
            if parsed:
                self._raw_rates = parsed
                self._last_success_ts = time.time()
                self._last_error = None
                self._source = 'live'
            else:
                self._last_error = err or 'no data / missing API key'
                # Keep old cache; mark source based on age
                if self._last_success_ts and (time.time() - self._last_success_ts) < self.stale_after:
                    self._source = 'cache'
                else:
                    self._source = 'fallback'
                    self._raw_rates = dict(FALLBACK_RATES)

    def _background_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._refresh_once()
            except Exception:
                pass
            self._stop_evt.wait(self.refresh_seconds)

    def start_background_refresh(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._background_loop, daemon=True, name='rate-refresh')
        self._thread.start()

    def stop_background_refresh(self) -> None:
        self._stop_evt.set()

    # ------------------------------------------------------------------ rates
    def get_mid_rate(self, f: str, t: str) -> float:
        with self._lock:
            rf = self._raw_rates.get(f, FALLBACK_RATES.get(f, 1.0))
            rt = self._raw_rates.get(t, FALLBACK_RATES.get(t, 1.0))
        if rf == 0:
            return 0.0
        return rt / rf

    def get_rate(self, f: str, t: str) -> float:
        """Customer-facing rate = mid × (1 − margin)."""
        mid = self.get_mid_rate(f, t)
        return mid * (1 - self.margin)

    def get_all_rates(self, base: str = 'USD') -> dict:
        with self._lock:
            syms = list(self._raw_rates.keys())
        return {c: self.get_rate(base, c) for c in syms if c != base}


# Module-level singleton so Flask and any background jobs share state
_engine_singleton: Optional[RateEngine] = None


def get_engine() -> RateEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = RateEngine()
        _engine_singleton.start_background_refresh()
    return _engine_singleton
