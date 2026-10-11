#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cat > ARCHITECTURE.md << 'ARCH_END'
# Architecture — Aflathoon Exchange Platform

Companion to PROJECT_STATE.md. How the pieces fit together.

---

## 1. High-level diagram

---

## 2. Request lifecycle

### 2.1 Exchange quote — POST /exchange/convert

Browser -> POST /exchange/convert {from, to, amount}
         |
Flask route (app/routes/exchange.py::convert)
         |
get_engine() -> RateEngine singleton
         |- if cache fresh: return cached
         |- else: compute from self._raw_rates
         |
calculate_margin(amount, customer_rate, 0.065)
         |
jsonify({rate, gross, platform_fee, net_to_customer, source, note})

No DB write. Idempotent.

### 2.2 Book trade — POST /exchange/book

Browser -> POST /exchange/book {from, to, amount}
         |
exchange.py::book
         |- current_app.config['LIVE_TRADING_ENABLED']
         |- missing_licenses()
         |- auto_confirm = live AND no missing AND current_user.is_admin
         |
book_trade(user, from, to, amount, auto_confirm)
         |- engine.get_mid_rate() + get_rate()
         |- calculate_margin()
         |- next_reference() -> "TX-2026-000042"
         |- Transaction(...) -> db.session.add + commit
         |- if auto_confirm: status=CONFIRMED, confirmed_at=now
         |
jsonify({ok, reference, status, ...})

### 2.3 Admin dashboard — GET /admin/

Browser renders skeleton, then JS fires parallel fetches:
  /admin/api/balance
  /admin/api/ticker
  /admin/api/stats
  /admin/api/recent-transactions?limit=8
  /admin/api/pnl?days=30

JS paints the DOM. setInterval re-fetches ticker 15s, stats/balance 30s.

---

## 3. Service layer

### 3.1 rate_engine.py

State:
  _raw_rates         current best-known rates
  _last_success_ts   unix time of last API success
  _source            'live' | 'cache' | 'fallback'
  _lock              RLock
  _thread            background refresher

Methods:
  get_mid_rate(f, t)      raw rate (no spread)
  get_rate(f, t)          customer rate = mid x (1 - margin)
  get_all_rates(base)     dict for base pair
  source_info()           for the badge
  start_background_refresh()
  stop_background_refresh()

Singleton: get_engine()

### 3.2 margin.py

calculate_margin(amount, customer_rate, margin_pct=0.065)
    -> {converted_gross, margin, total_fee, net_to_customer, margin_pct}

Invariant: net_to_customer == converted_gross.

### 3.3 booking.py

book_trade(user, from, to, amount, auto_confirm=False, transaction_type=SPOT)
Returns (transaction, error_dict_or_None).

Snapshots: mid_rate, customer_rate, margin_amount, rate_source.

### 3.4 license_guard.py

REQUIRED      = os.getenv('LICENSE_REQUIRED_TYPES', 'msb').split(',')
JURISDICTION  = os.getenv('LICENSE_JURISDICTION', 'UK')
ENFORCEMENT   = os.getenv('LICENSE_ENFORCEMENT', 'strict')
LIVE_ENABLED  = os.getenv('LIVE_TRADING_ENABLED', 'false').lower() == 'true'

assert_live_trading_allowed()
    - if ENFORCEMENT != 'strict': return
    - if not LIVE_ENABLED: abort(503)
    - missing = missing_licenses()
    - if missing: abort(451, description=...)

### 3.5 war_risk.py

HIGH_RISK_CORRIDORS = {('IR','*'), ('RU','*'), ('SY','*'), ('YE','*'),
                       ('LY','*'), ('UA','*'), ('IL','*')}

compute_war_risk_premium(base_freight, route=(origin, dest))
    - pct = 0.05 if high_risk else 0.0025
    - return base_freight * pct

adjust_for_hedge(premium, base_freight)
    - if premium > margin_cover (6.5% of freight):
        return premium + (premium - margin_cover) * 0.5
    - else return premium

### 3.6 crypto_custody.py -- STUB

Deliberately raises if used. Do not remove this guard.
Real deployments use Fireblocks / BitGo / Copper / HSM / multi-sig.

---

## 4. Database resolution

def _resolve_db_uri() -> str:
    env_url = (os.environ.get('DATABASE_URL') or '').strip()
    if env_url.startswith(('postgresql://', 'postgres://')):
        return env_url
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    db_file = os.path.join(data_dir, 'exchange.db')
    return f"sqlite:///{db_file}"

Absolute path works regardless of cwd. Startup prints [app] DB URI: ...

---

## 5. Template inheritance

base.html
  index.html
  auth/change_password.html
  exchange/dashboard.html
  logistics/quote.html
  admin/dashboard.html
  admin/blotter.html
  admin/positions.html
  admin/users.html
  compliance/overview.html

Standalone (theme-aware, no sidebar):
  auth/login.html
  auth/register.html

base.html provides: sidebar, topbar with source badge + theme toggle + avatar,
theme init script, shared JS, blocks title / search_placeholder / head /
content / scripts.

---

## 6. CSS variable system

app/static/css/admin.css:

:root, [data-theme="dark"] {
  --bg: #0b0f1e; --surface: #141a33; --border: #222a4a;
  --text: #e8ecf6; --muted: #8892b0;
  --accent: #6f8cff; --accent-2: #8a6fff;
  --green: #22c55e; --amber: #f59e0b; --red: #ef4444;
}

[data-theme="light"] { --bg: #f5f7fc; --surface: #ffffff; ... }

@media (prefers-color-scheme: light) {
  [data-theme="auto"] { /* light values */ }
}

Never hardcode colors in templates. Always var(--...).

Component classes: .afl-card, .afl-row, .afl-table, .afl-btn, .afl-in,
.afl-pill, .afl-status, .afl-k, .afl-v, .afl-h3, .tabs.

---

## 7. Auth flow

Flask-Login. User implements UserMixin.
login_manager.user_loader uses db.session.get(User, int(user_id)).
Session cookie aflathoon_session, HttpOnly, SameSite=Lax.
Unique name prevents collisions with other localhost dev servers.

Login: check_password -> login_user(u, remember=True) -> redirect(next_url)
Logout: logout_user() -> redirect to /

---

## 8. Rate limiting

Flask-Limiter, in-memory backend.
Global default RATELIMIT_DEFAULT=100/hour.

Recommended to add:
  /auth/login           5/minute per IP + per username
  /exchange/book        60/minute per user
  /admin/api/*          300/minute per admin

Move to Redis for production: RATELIMIT_STORAGE_URI=redis://localhost:6379/0

---

## 9. Backup and sync

Database:
  scripts/backup_db.sh uses sqlite3 .backup (safe while running)
  30 daily copies in data/backups/
  Cron 03:30

Full snapshot:
  scripts/backup_full.sh
  DB copy + .env shape (redacted) + manifest
  14 snapshots in backups/

Git sync:
  scripts/git-sync.sh — stages all, commits if changes, pushes
  Cron 03:15
  DB, .env, venv/, installers gitignored

---

## 10. Failure modes

| Symptom | Root cause | Fix |
|---|---|---|
| ModuleNotFoundError: flask | venv not active | source venv/bin/activate |
| unable to open database file | DB path broken | Check _resolve_db_uri() |
| no such column: X | Model changed, table not migrated | ALTER TABLE or Flask-Migrate |
| Login POST returns 200 | Wrong password / cookie dropped | Check [LOGIN] debug lines |
| Port already in use | Another process | pkill -f "python app.py" |
| Two banners printed | Debug reloader running | Check use_reloader=False |
| Wrong theme | Doesn't extend base | grep -L "extends" |
| Template not found | Missing directory | mkdir -p app/templates/<dir> |

---

## 11. Extensibility

Adding a service:
  app/services/new_service.py -> import in route
  If stateful, add get_singleton() pattern like rate_engine

Adding a model:
  app/models/new_model.py -> register in __init__.py
  ALTER TABLE in SQLite OR set up Flask-Migrate

Adding a route module:
  app/routes/new_module.py with new_bp = Blueprint('new', __name__)
  Register in app/routes/__init__.py
  Register in create_app(): app.register_blueprint(new_bp, url_prefix='/new')

Adding a template:
  app/templates/new/page.html
  Must start with {% extends "base.html" %}
  Fill {% block content %}

Adding an admin API:
  In admin.py with @admin_required decorator
  Return jsonify(...)

Adding a theme:
  Add [data-theme="yourtheme"] { --bg: ...; } to admin.css
  Add option to base.html theme menu

---

## 12. Production target (future)

Cloudflare (DNS + WAF)
    |
Cloudflare Tunnel (no exposed ports)
    |
Nginx (TLS termination, static files, reverse proxy)
    |
Gunicorn (4 workers) -> Flask app
    |
PostgreSQL 16 + Redis (cache + rate limit + sessions)

Deployment checklist:
  [ ] Rotate SECRET_KEY
  [ ] Change admin password
  [ ] FLASK_ENV=production
  [ ] SESSION_COOKIE_SECURE=True
  [ ] CSRF (Flask-WTF)
  [ ] Redis for cache + limiter + sessions
  [ ] PostgreSQL migration
  [ ] Gunicorn systemd unit
  [ ] Nginx + Let's Encrypt
  [ ] Cloudflare Tunnel
  [ ] Sentry / Prometheus monitoring
  [ ] Real KYC / sanctions providers
  [ ] Real crypto custody
  [ ] Legal review of licensing

End of architecture.
ARCH_END

echo "ARCHITECTURE.md written ($(wc -l < ARCHITECTURE.md) lines)"
