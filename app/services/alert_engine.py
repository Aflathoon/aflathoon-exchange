"""
Bridges AI Assistant findings to the alert banner system.

Every 5 minutes:
  1. Scan findings
  2. For each critical/warning finding, create or refresh an Alert
  3. When a finding disappears, expire its Alert

Deduplication: alert titles are keyed by finding.key. We look up
an existing alert by title marker (stored as "[finding_key] Title")
so re-runs update instead of duplicate.
"""
import os
import time
import threading
from datetime import datetime, timedelta

from app import db
from app.models.alert import Alert
from app.services import assistant


CHECK_INTERVAL = int(os.getenv('ALERT_ENGINE_INTERVAL', '300'))   # 5 min
# Only raise banners for these severities
RELEVANT = {'critical', 'warning'}


def _marker(key: str) -> str:
    return f"[{key}]"


def _find_existing(key: str):
    return Alert.query.filter(Alert.title.like(f"%{_marker(key)}%")).first()


def _run_once():
    findings = assistant.scan_all()
    now = datetime.utcnow()

    current_keys = set()
    for f in findings:
        if f.severity not in RELEVANT:
            continue
        current_keys.add(f.key)

        title = f"{_marker(f.key)} {f.title}"
        existing = _find_existing(f.key)

        if existing:
            # Refresh: update body if detail changed, extend expiry
            existing.severity = f.severity
            existing.body = f.detail
            existing.link_url = f.action_url
            existing.link_label = f.action_label
            existing.title = title
            # Don't touch created_at or dismissed_by — user's choice persists
            existing.expires_at = now + timedelta(hours=24)
        else:
            db.session.add(Alert(
                severity=f.severity,
                title=title,
                body=f.detail,
                link_url=f.action_url,
                link_label=f.action_label,
                expires_at=now + timedelta(hours=24),
                created_by_id=None,   # system-generated
            ))

    # Expire alerts whose finding is gone
    stale = Alert.query.filter(Alert.title.like('[%')).all()
    for a in stale:
        # Extract key from title
        t = a.title or ''
        if not t.startswith('['):
            continue
        close = t.find(']')
        if close == -1:
            continue
        key = t[1:close]
        if key not in current_keys:
            a.expires_at = now - timedelta(minutes=1)

    db.session.commit()


def _loop():
    while True:
        try:
            _run_once()
        except Exception as e:
            print(f"[alert_engine] scan failed: {e}", flush=True)
        time.sleep(CHECK_INTERVAL)


_started = False

def start_engine():
    """Called once from create_app. Safe to call multiple times."""
    global _started
    if _started:
        return
    _started = True
    # Delay first run so app finishes booting
    def _delayed():
        time.sleep(15)
        _loop()
    t = threading.Thread(target=_delayed, daemon=True, name='alert-engine')
    t.start()
    print("[alert_engine] started (interval=%ds)" % CHECK_INTERVAL, flush=True)
