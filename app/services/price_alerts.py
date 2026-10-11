"""
Raise breaking alerts when a tracked crypto moves sharply in 24h.

Rule: |24h change| >= PRICE_ALERT_THRESHOLD (default 5.0) -> critical alert
      |24h change| >= PRICE_ALERT_WARN (default 3.0)      -> warning alert
      else                                              -> no alert

Deduped by finding key `price_spike_<SYM>` so re-runs update.
"""
import os
import time
import threading
from datetime import datetime, timedelta

from app import db
from app.models.alert import Alert
from app.services.crypto_prices import get_prices


CHECK_INTERVAL = int(os.getenv('PRICE_ALERT_INTERVAL', '300'))       # 5 min
THRESHOLD_CRITICAL = float(os.getenv('PRICE_ALERT_THRESHOLD', '5.0'))
THRESHOLD_WARN = float(os.getenv('PRICE_ALERT_WARN', '3.0'))


def _marker(sym: str) -> str:
    return f"[price_spike_{sym}]"


def _run_once():
    snap = get_prices().snapshot()
    now = datetime.utcnow()
    active_keys = set()

    for sym, data in (snap.get('prices') or {}).items():
        change = data.get('change_24h') or 0.0
        price = data.get('price')
        if abs(change) < THRESHOLD_WARN:
            continue

        severity = 'critical' if abs(change) >= THRESHOLD_CRITICAL else 'warning'
        updown = '▲' if change >= 0 else '▼'
        key = f'price_spike_{sym}'
        active_keys.add(key)

        title = f"{_marker(sym)} {sym} {updown} {abs(change):.2f}% in 24h"
        body = (
            f"{sym} is now ${price:,.4f} (24h change {change:+.2f}%). "
            f"Consider reviewing exposure."
        )
        existing = Alert.query.filter(Alert.title.like(f"%{_marker(sym)}%")).first()
        if existing:
            existing.severity = severity
            existing.title = title
            existing.body = body
            existing.expires_at = now + timedelta(hours=6)
        else:
            db.session.add(Alert(
                severity=severity,
                title=title,
                body=body,
                link_url='/exchange/',
                link_label='Open exchange',
                expires_at=now + timedelta(hours=6),
                created_by_id=None,
            ))

    # Expire price alerts whose coin settled
    all_price_alerts = Alert.query.filter(Alert.title.like('[price_spike_%')).all()
    for a in all_price_alerts:
        t = a.title or ''
        close = t.find(']')
        if close == -1:
            continue
        key = t[1:close]
        if key not in active_keys:
            a.expires_at = now - timedelta(minutes=1)

    db.session.commit()


def _loop():
    while True:
        try:
            _run_once()
        except Exception as e:
            print(f"[price_alerts] failed: {e}", flush=True)
        time.sleep(CHECK_INTERVAL)


_started = False

def start_engine():
    global _started
    if _started:
        return
    _started = True
    def _delayed():
        time.sleep(20)
        _loop()
    t = threading.Thread(target=_delayed, daemon=True, name='price-alerts')
    t.start()
    print("[price_alerts] started (interval=%ds, threshold=%.1f%%)" % (CHECK_INTERVAL, THRESHOLD_CRITICAL), flush=True)
