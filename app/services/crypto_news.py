"""
Crypto news + trend data.

Sources:
  1. CoinGecko (no key): trending coins + global market data
  2. RSS feeds from vetted crypto outlets (no key, no rate limit)

RSS gives us title, URL, published date, and — with a bit of parsing —
lead images. We try multiple fields per item because RSS doesn't
standardise image placement.

Design: we only surface headlines from our whitelist of trusted outlets.
No user-generated text ever hits the UI.
"""
import os
import re
import time
import html
import threading
from datetime import datetime, timezone

import requests
import feedparser
from bs4 import BeautifulSoup


CG_BASE = os.getenv('COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')
REFRESH_SECONDS = int(os.getenv('NEWS_REFRESH_SECONDS', '600'))    # 10 min
HTTP_TIMEOUT = 12
USER_AGENT = 'AflathoonExchange/1.0 (+https://aflathoon.local)'

# Trusted RSS feeds — one per outlet
RSS_FEEDS = [
    ('CoinDesk',        'https://www.coindesk.com/arc/outboundfeeds/rss/'),
    ('Cointelegraph',   'https://cointelegraph.com/rss'),
    ('The Block',       'https://www.theblock.co/rss.xml'),
    ('Decrypt',         'https://decrypt.co/feed'),
    ('Bitcoin Magazine','https://bitcoinmagazine.com/.rss/full/'),
]


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

    # ------------------------------------------------------------ coingecko
    def _fetch_trending(self):
        r = requests.get(f"{CG_BASE}/search/trending",
                         timeout=HTTP_TIMEOUT,
                         headers={'User-Agent': USER_AGENT})
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
        r = requests.get(f"{CG_BASE}/global",
                         timeout=HTTP_TIMEOUT,
                         headers={'User-Agent': USER_AGENT})
        r.raise_for_status()
        data = r.json().get('data') or {}
        return {
            'market_cap_usd': (data.get('total_market_cap') or {}).get('usd'),
            'volume_24h_usd': (data.get('total_volume') or {}).get('usd'),
            'btc_dominance': (data.get('market_cap_percentage') or {}).get('btc'),
            'eth_dominance': (data.get('market_cap_percentage') or {}).get('eth'),
            'market_cap_change_24h': data.get('market_cap_change_percentage_24h_usd'),
        }

    # ---------------------------------------------------------------- RSS
    def _extract_image(self, entry):
        """
        Try every known place RSS feeds put the lead image.
        Returns URL string or None.
        """
        # 1. media:thumbnail / media:content (Yahoo Media RSS)
        for field in ('media_thumbnail', 'media_content'):
            items = entry.get(field) or []
            for m in items:
                url = m.get('url') if isinstance(m, dict) else None
                if url:
                    return url

        # 2. enclosure
        for enc in (entry.get('enclosures') or []):
            url = enc.get('href') or enc.get('url')
            ctype = (enc.get('type') or '').lower()
            if url and (not ctype or ctype.startswith('image')):
                return url

        # 3. <link rel="enclosure">
        for link in (entry.get('links') or []):
            if link.get('rel') == 'enclosure' and link.get('href'):
                ctype = (link.get('type') or '').lower()
                if not ctype or ctype.startswith('image'):
                    return link['href']

        # 4. Inline <img> inside description or content:encoded
        for field in ('summary', 'description', 'content'):
            raw = entry.get(field)
            if not raw:
                continue
            if isinstance(raw, list):
                raw = ' '.join((c.get('value') or '') for c in raw if isinstance(c, dict))
            if not isinstance(raw, str):
                continue
            try:
                soup = BeautifulSoup(raw, 'lxml')
                img = soup.find('img')
                if img and img.get('src'):
                    return img['src']
            except Exception:
                pass

        # 5. Fallback: regex for og:image style URLs in any string field
        for field in ('summary', 'description'):
            raw = entry.get(field)
            if isinstance(raw, str):
                m = re.search(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', raw, re.I)
                if m:
                    return m.group(0)

        return None

    def _clean_text(self, text):
        """Strip HTML tags and unescape entities."""
        if not text:
            return ''
        try:
            soup = BeautifulSoup(text, 'lxml')
            plain = soup.get_text(' ', strip=True)
        except Exception:
            plain = re.sub(r'<[^>]+>', ' ', text)
        return html.unescape(plain).strip()

    def _parse_published(self, entry):
        """Try to extract a sensible ISO datetime from the entry."""
        for key in ('published_parsed', 'updated_parsed', 'created_parsed'):
            t = entry.get(key)
            if t:
                try:
                    dt = datetime(*t[:6], tzinfo=timezone.utc)
                    return dt.isoformat()
                except Exception:
                    pass
        # Fallback: string fields
        return entry.get('published') or entry.get('updated') or None

    def _fetch_one_feed(self, source_name, url):
        """Fetch and parse one RSS feed. Returns list of article dicts."""
        try:
            # Pre-fetch with requests so we control User-Agent and timeouts
            resp = requests.get(url, timeout=HTTP_TIMEOUT,
                                headers={'User-Agent': USER_AGENT,
                                         'Accept': 'application/rss+xml, application/xml, text/xml'})
            if resp.status_code != 200:
                print(f"[news] {source_name}: HTTP {resp.status_code}", flush=True)
                return []
            parsed = feedparser.parse(resp.content)
            if parsed.bozo:
                # Some feeds have minor XML issues; feedparser still parses them
                pass
            items = []
            for entry in parsed.entries[:15]:
                title = self._clean_text(entry.get('title') or '')[:200]
                if not title:
                    continue
                link = entry.get('link') or ''
                if not link:
                    continue
                items.append({
                    'title': title,
                    'url': link,
                    'source': source_name,
                    'published_at': self._parse_published(entry),
                    'image': self._extract_image(entry),
                    'description': self._clean_text(
                        entry.get('summary') or entry.get('description') or ''
                    )[:200] or None,
                })
            return items
        except Exception as e:
            print(f"[news] {source_name} fetch failed: {type(e).__name__}: {e}", flush=True)
            return []

    def _fetch_rss(self):
        """Fetch all feeds sequentially, merge, sort by published_at."""
        all_items = []
        for name, url in RSS_FEEDS:
            items = self._fetch_one_feed(name, url)
            all_items.extend(items)

        def sort_key(a):
            p = a.get('published_at')
            if not p:
                return ''
            return p

        all_items.sort(key=sort_key, reverse=True)
        # Deduplicate by URL
        seen = set()
        unique = []
        for it in all_items:
            if it['url'] in seen:
                continue
            seen.add(it['url'])
            unique.append(it)
            if len(unique) >= 10:
                break

        print(f"[news] RSS: {len(all_items)} total items, {len(unique)} unique shown", flush=True)
        return unique

    # ---------------------------------------------------------------- refresh
    def _refresh_once(self):
        ok = False

        try:
            t = self._fetch_trending()
            if t:
                with self._lock:
                    self._trending = t
                ok = True
        except Exception as e:
            print(f"[news] trending failed: {e}", flush=True)

        try:
            g = self._fetch_global()
            if g:
                with self._lock:
                    self._global = g
                ok = True
        except Exception as e:
            print(f"[news] global failed: {e}", flush=True)

        try:
            items = self._fetch_rss()
            if items:
                with self._lock:
                    self._items = items
                ok = True
        except Exception as e:
            print(f"[news] RSS failed: {e}", flush=True)

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
            except Exception as e:
                print(f"[news] refresh loop error: {e}", flush=True)
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
                'provider': 'rss',
            }


_singleton = None

def get_news():
    global _singleton
    if _singleton is None:
        _singleton = CryptoNews()
        _singleton.start()
    return _singleton
