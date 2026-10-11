"""
CoinGecko free-tier price fetcher. No API key required.

Doc: https://www.coingecko.com/en/api/documentation
Free tier: 10-30 calls/min, cache for 60s to stay well under.

Returns a normalised dict for the ticker. Falls back to a small
hardcoded table if CoinGecko is unreachable, so the UI never breaks.
"""
import os
import time
import threading
import requests


CG_BASE = os.getenv('COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')
REFRESH_SECONDS = int(os.getenv('COINGECKO_REFRESH_SECONDS', '90'))
HTTP_TIMEOUT = 10

# What we track. CoinGecko ids + display symbol.
TRACKED = [
    ('bitcoin',   'BTC'),
    ('ethereum',  'ETH'),
    ('solana',    'SOL'),
    ('ripple',    'XRP'),
    ('cardano',   'ADA'),
    ('dogecoin',  'DOGE'),
]

# Fallback prices if the API is unreachable (USD)
FALLBACK = {
    'BTC': 66666.66, 'ETH': 3500.00, 'SOL': 180.00,
    'XRP': 2.20,     'ADA': 0.90,    'DOGE': 0.35,
}


class CryptoPrices:
    def __init__(self):
        self._prices = {}
        self._last_ok = None
        self._last_err = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._source = 'fallback'

    def _fetch(self):
        ids = ','.join(i for i, _ in TRACKED)
        url = f"{CG_BASE}/simple/price"
        params = {'ids': ids, 'vs_currencies': 'usd', 'include_24hr_change': 'true'}
        r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        out = {}
        for cg_id, sym in TRACKED:
            row = data.get(cg_id) or {}
            if 'usd' in row:
                out[sym] = {
                    'price': float(row['usd']),
                    'change_24h': float(row.get('usd_24h_change', 0.0)),
                }
        return out if out else None

    def _refresh_once(self):
        try:
            parsed = self._fetch()
            with self._lock:
                if parsed:
                    self._prices = parsed
                    self._last_ok = time.time()
                    self._last_err = None
                    self._source = 'live'
                else:
                    self._last_err = 'empty response'
                    self._source = 'fallback'
                    if not self._prices:
                        self._prices = {s: {'price': p, 'change_24h': 0.0} for s, p in FALLBACK.items()}
        except Exception as e:
            with self._lock:
                self._last_err = f"{type(e).__name__}: {e}"
                self._source = 'fallback'
                if not self._prices:
                    self._prices = {s: {'price': p, 'change_24h': 0.0} for s, p in FALLBACK.items()}

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._refresh_once()
            except Exception:
                pass
            self._stop.wait(REFRESH_SECONDS)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='crypto-prices')
        self._thread.start()

    def snapshot(self):
        with self._lock:
            age = None if not self._last_ok else int(time.time() - self._last_ok)
            return {
                'source': self._source,
                'last_ok_seconds_ago': age,
                'last_error': self._last_err,
                'prices': dict(self._prices),
            }


_singleton = None

def get_prices():
    global _singleton
    if _singleton is None:
        _singleton = CryptoPrices()
        _singleton.start()
    return _singleton
