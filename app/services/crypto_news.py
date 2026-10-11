"""
Curated crypto news + trend data.

Free sources (no key):
  - CoinGecko trending coins
  - CoinGecko global market data

Optional (needs NEWSAPI_KEY):
  - NewsAPI.org headlines from a whitelist of crypto outlets

Design: we never surface user-generated or unknown-source text.
Every headline comes from a source we explicitly trust, or is omitted.
"""
import os
import time
import threading
import requests


CG_BASE = os.getenv('COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')
REFRESH_SECONDS = int(os.getenv('NEWS_REFRESH_SECONDS', '300'))
HTTP_TIMEOUT = 10

# Whitelisted news sources for the optional NewsAPI mode
NEWSAPI_WHITELIST = os.getenv(
    'NEWSAPI_WHITELIST',
    'coindesk,cointelegraph,theblock,decrypt,bitcoinmagazine'
).split(',')


class CryptoNews:
    def __init__(self):
        self._items = []
        self._trending = []
        self._global = {}
        self._last_ok = None
        self._last_err = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._source = 'fallback'

    # ---------------------------------------------------------------- fetchers
    def _fetch_trending(self):
        r = requests.get(f"{CG_BASE}/search/trending", timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        out = []
        for entry in (data.get('coins') or [])[:7]:
            item = entry.get('item') or {}
            out.append({
                'symbol': (item.get('symbol') or '').upper(),
                'name': item.get('name') or '',
                'rank': item.get('market_cap_rank'),
                'slug': item.get('id') or '',
            })
        return out

    def _fetch_global(self):
        r = requests.get(f"{CG_BASE}/global", timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json().get('data') or {}
        return {
            'market_cap_usd': (data.get('total_market_cap') or {}).get('usd'),
            'volume_24h_usd': (data.get('total_volume') or {}).get('usd'),
            'btc_dominance': (data.get('market_cap_percentage') or {}).get('btc'),
            'eth_dominance': (data.get('market_cap_percentage') or {}).get('eth'),
            'market_cap_change_24h': data.get('market_cap_change_percentage_24h_usd'),
        }

    def _fetch_newsapi(self):
        key = (os.getenv('NEWSAPI_KEY') or '').strip()
        if not key:
            return []
        try:
            r = requests.get(
                'https://newsapi.org/v2/everything',
                params={
                    'q': 'crypto OR bitcoin OR ethereum',
                    'language': 'en',
                    'sortBy': 'publishedAt',
                    'pageSize': 15,
                },
                headers={'X-Api-Key': key},
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            articles = r.json().get('articles') or []
        except Exception:
            return []

        out = []
        for a in articles:
            src = ((a.get('source') or {}).get('id') or '').lower()
            name = ((a.get('source') or {}).get('name') or '').lower()
            if not any(w in src or w in name for w in NEWSAPI_WHITELIST):
                continue
            out.append({
                'title': (a.get('title') or '')[:200],
                'url': a.get('url'),
                'source': (a.get('source') or {}).get('name') or '',
                'published_at': a.get('publishedAt'),
            })
            if len(out) >= 8:
                break
        return out

    # ---------------------------------------------------------------- refresh
    def _refresh_once(self):
        with self._lock:
            trending = self._trending
            glob = self._global
            news = self._items
        ok = False
        try:
            t = self._fetch_trending()
            if t:
                with self._lock:
                    self._trending = t
                ok = True
        except Exception:
            pass
        try:
            g = self._fetch_global()
            if g:
                with self._lock:
                    self._global = g
                ok = True
        except Exception:
            pass
        try:
            n = self._fetch_newsapi()
            if n:
                with self._lock:
                    self._items = n
        except Exception:
            pass

        with self._lock:
            if ok:
                self._last_ok = time.time()
                self._last_err = None
                self._source = 'live'
            else:
                self._source = 'fallback'
                self._last_err = self._last_err or 'no data'

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
        self._thread = threading.Thread(target=self._loop, daemon=True, name='crypto-news')
        self._thread.start()

    def snapshot(self):
        with self._lock:
            age = None if not self._last_ok else int(time.time() - self._last_ok)
            return {
                'source': self._source,
                'last_ok_seconds_ago': age,
                'last_error': self._last_err,
                'trending': list(self._trending),
                'global': dict(self._global),
                'news': list(self._items),
                'has_newsapi': bool((os.getenv('NEWSAPI_KEY') or '').strip()),
            }


_singleton = None

def get_news():
    global _singleton
    if _singleton is None:
        _singleton = CryptoNews()
        _singleton.start()
    return _singleton
