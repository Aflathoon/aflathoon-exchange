# Architecture — Aflathoon Exchange Platform

Companion to `PROJECT_STATE.md`. Focus on **how the pieces fit together**.

---

## 1. High-level diagram
┌──────────────────────────────┐
│ Browser (KDE / any) │
│ Dark/Light theme via cookie │
└──────────────┬───────────────┘
│ HTTP :9105
▼
┌────────────────────────────────────────────────────────────────────┐
│ Flask App (app.py) │
│ - Pinned port (FLASK_PORT=9105) or finds free port above 9100 │
│ - use_reloader=False (avoids double-process port flapping) │
│ - Prints "[app] DB URI: …" on startup │
└──────────────────────────────┬─────────────────────────────────────┘
│
▼
┌────────────────────────────────────────────────────────────────────┐
│ create_app() — app/init.py │
│ - Loads .env via dotenv (top of module) │
│ - _resolve_db_uri() → absolute SQLite path │
│ - Initialises: db, migrate, login_manager, limiter, cache │
│ - Registers 6 blueprints: main, auth, exchange, admin, │
│ logistics, compliance │
│ - db.create_all() (tables auto-created if missing) │
└──────────────────────────────┬─────────────────────────────────────┘
│
┌──────────────────────┼──────────────────────┐
▼ ▼ ▼
┌───────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Routes │ │ Services │ │ Models │
│ (controllers)│ │ (business logic)│ │ (persistence) │
├───────────────┤ ├──────────────────┤ ├──────────────────┤
│ main.py │ │ rate_engine.py │ │ user.py │
│ auth.py │───▶│ margin.py │◀──│ transaction.py │
│ exchange.py │ │ booking.py │ │ license.py │
│ admin.py │ │ war_risk.py │ │ shipping.py │
│ logistics.py │ │ license_guard.py │ │ rate.py │
│ compliance.py │ │ compliance.py │ │ │
│ │ │ crypto_custody.py│ │ │
└───────────────┘ └──────────────────┘ └──────────────────┘
│
▼
┌───────────────────┐
│ SQLite (data/) │
│ exchange.db │
└───────────────────┘

text

---

## 2. Request lifecycle examples

### 2.1 Exchange quote (`POST /exchange/convert`)
Browser → POST /exchange/convert {from, to, amount}
↓
Flask route (app/routes/exchange.py::convert)
↓
get_engine() → RateEngine singleton
├─ if cache fresh: return cached rate
├─ else: compute from self._raw_rates
│ (populated by background thread from API or FALLBACK_RATES)
↓
calculate_margin(amount, customer_rate, 0.065)
↓
jsonify({rate, gross, platform_fee, net_to_customer, source, note})
↓
Browser renders rows

text

No DB write. Idempotent. Safe to spam.

### 2.2 Book trade (`POST /exchange/book`)
Browser → POST /exchange/book {from, to, amount}
↓
exchange.py::book
├─ current_app.config['LIVE_TRADING_ENABLED'] (bool)
├─ missing_licenses() (from license_guard)
└─ auto_confirm = live AND no missing AND current_user.is_admin
↓
book_trade(user, from, to, amount, auto_confirm)
├─ engine.get_mid_rate() + get_rate()
├─ calculate_margin()
├─ next_reference() → "TX-2026-000042"
├─ Transaction(...) → db.session.add + commit
└─ if auto_confirm: set status=CONFIRMED, confirmed_at=now
↓
jsonify({ok, reference, status, ...})
↓
Browser reloads → recent table now shows row

text

### 2.3 Admin dashboard (`GET /admin/`)
Browser → GET /admin/
↓
admin.py::dashboard → render_template('admin/dashboard.html')
↓
Browser renders skeleton, then JavaScript fires 6 parallel fetches:
/admin/api/balance
/admin/api/ticker
/admin/api/stats
/admin/api/recent-transactions?limit=8
/admin/api/pnl?days=30
/admin/api/positions (via /admin/positions)
↓
Each returns JSON; JS paints the DOM
↓
setInterval re-fetches ticker (15s), stats/balance (30s)

text

The dashboard is **static HTML + JS polling** — no server-side rendering of numbers.

---

## 3. Service layer details

### 3.1 `rate_engine.py`

**State:**
- `_raw_rates: dict[str, float]` — current best-known
- `_last_success_ts: float` — unix time of last API success
- `_source: str` — 'live' | 'cache' | 'fallback'
- `_lock: RLock` — thread-safe access
- `_thread: Thread` — background refresher (daemon)

**Key methods:**
- `get_mid_rate(f, t)` — raw rate (no spread)
- `get_rate(f, t)` — customer rate = mid × (1 − margin)
- `get_all_rates(base)` — dict for base pair
- `source_info()` — for the badge
- `start_background_refresh()` / `stop_background_refresh()`

**Singleton:** `get_engine()` — first call creates + starts thread. All routes must use this, not `RateEngine()` directly (else multiple threads fight over state).

### 3.2 `margin.py`

Pure function, no state:

```python
calculate_margin(amount, customer_rate, margin_pct=0.065)
    → {converted_gross, margin, total_fee, net_to_customer, margin_pct}
Invariant: net_to_customer == converted_gross (spread is already in customer_rate). The margin/total_fee fields are for accounting only — never deducted a second time.

3.3 booking.py
One function: book_trade(user, from, to, amount, auto_confirm=False, transaction_type=SPOT).

Returns (transaction, error_dict_or_None).

Snapshots at booking time:

mid_rate, customer_rate

margin_amount (platform revenue)

rate_source ('live'/'cache'/'fallback')

This means P&L is historically accurate, not recalculated from current rates.

3.4 license_guard.py
python
REQUIRED = os.getenv('LICENSE_REQUIRED_TYPES', 'msb').split(',')
JURISDICTION = os.getenv('LICENSE_JURISDICTION', 'UK')
ENFORCEMENT = os.getenv('LICENSE_ENFORCEMENT', 'strict')
LIVE_ENABLED = os.getenv('LIVE_TRADING_ENABLED', 'false').lower() == 'true'

assert_live_trading_allowed()
    - if ENFORCEMENT != 'strict': return  # dev mode bypass
    - if not LIVE_ENABLED: abort(503)
    - missing = missing_licenses()
    - if missing: abort(451, description=...)
Only /exchange/book calls this. Adding it to new money-moving routes is mandatory.

3.5 war_risk.py
python
HIGH_RISK_CORRIDORS = {('IR','*'), ('RU','*'), ...}

compute_war_risk_premium(base_freight, route=(origin, dest))
    - pct = 0.05 if high_risk else 0.0025
    - return base_freight * pct

adjust_for_hedge(premium, base_freight)
    - if premium > margin_cover (6.5% of freight):
        return premium + (premium - margin_cover) * 0.5
    - else return premium
This is a loss-prevention mechanism. Without it, a geopolitical spike in insurance costs would exceed the platform's margin and produce a loss per shipment.

3.6 crypto_custody.py — STUB
Deliberately raises if used. request_withdrawal() throws CustodyNotConfigured when CRYPTO_CUSTODY_PROVIDER=none.

Do not remove this guard. The server must never hold private keys. Real deployments use:

Fireblocks / BitGo / Copper custody APIs

Hardware Security Module (HSM)

Multi-signature wallets with independently held keys

4. Database resolution — the tricky part
python
def _resolve_db_uri() -> str:
    env_url = (os.environ.get('DATABASE_URL') or '').strip()
    if env_url.startswith(('postgresql://', 'postgres://', 'postgresql+psycopg2://')):
        return env_url
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    db_file = os.path.join(data_dir, 'exchange.db')
    return f"sqlite:///{db_file}"
Why the SQLite path is computed and not read from env:

.env is read by dotenv at module import, but env vars may not be available at the time create_app() runs (import order)

Flask-SQLAlchemy resolves sqlite:///relative/path against instance_path, not cwd — silently creating instance/data/exchange.db

Absolute path computed from __file__ works regardless of cwd

Startup verification: app/__init__.py prints [app] DB URI: sqlite:////home/aflathoon/aflathoon_exchange/data/exchange.db. If it points anywhere else, investigate immediately.

5. Template inheritance
text
base.html
├── index.html
├── auth/
│   └── change_password.html
├── exchange/dashboard.html
├── logistics/quote.html
├── admin/
│   ├── dashboard.html
│   ├── blotter.html
│   ├── positions.html
│   └── users.html
└── compliance/overview.html

# Standalone (theme-aware, no sidebar — intentional)
auth/login.html
auth/register.html
base.html provides:

Sidebar with brand mark + nav

Topbar with source badge, theme toggle, avatar

Shared theme init script (runs before CSS parses)

Shared JS: theme handler, source badge refresher

Blocks: title, search_placeholder, head, content, scripts

Adding a new page: extend base.html, fill {% block content %}. Do not add <!doctype html> or <html> tags.

6. CSS variable system
app/static/css/admin.css:

css
:root, [data-theme="dark"] {
  --bg: #0b0f1e;
  --surface: #141a33;
  --border: #222a4a;
  --text: #e8ecf6;
  --muted: #8892b0;
  --accent: #6f8cff;
  --accent-2: #8a6fff;
  --green: #22c55e;
  --amber: #f59e0b;
  --red: #ef4444;
  ...
}
[data-theme="light"] {
  --bg: #f5f7fc;
  --surface: #ffffff;
  ...
}
@media (prefers-color-scheme: light) {
  [data-theme="auto"] { /* light values */ }
}
Rule: never hardcode a color in a template. Always use var(--…).

Component classes available: .afl-card, .afl-row, .afl-table, .afl-btn, .afl-in, .afl-pill, .afl-status, .afl-k, .afl-v, .afl-h3, .tabs.

7. Auth flow
Flask-Login based.

User model implements UserMixin (from flask_login)

login_manager.user_loader registered inside create_app():

python
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
login_manager.login_view = 'auth.login' — redirect for @login_required

Login route: check_password → login_user(u, remember=True) → redirect(next_url)

Session cookie: aflathoon_session, HttpOnly, SameSite=Lax, unique name

Logout: logout_user() → redirect to /

Session cookie uniqueness matters: aflathoon_session (not session) prevents collisions with other localhost dev servers.

8. Rate limiting
Flask-Limiter, in-memory backend.

Global default: RATELIMIT_DEFAULT=100/hour (from env, not currently enforced)

No per-route decorators yet — add before production

Move to Redis: RATELIMIT_STORAGE_URI=redis://localhost:6379/0

Recommended limits to add:

/auth/login: 5/minute per IP + per username

/exchange/book: 60/minute per user

/admin/api/*: 300/minute per admin

9. Backup & sync architecture
Database
Hot backup: scripts/backup_db.sh uses sqlite3 .backup (safe while running)

Retention: 30 daily copies in data/backups/

Scheduled: cron at 03:30

Full snapshot
Script: scripts/backup_full.sh

Includes: DB copy, .env shape (secrets redacted), manifest

Retention: 14 snapshots in backups/

Scheduled: cron at 03:30

Git sync
Script: scripts/git-sync.sh

Stages all, commits if changes, pushes to current branch

Scheduled: cron at 03:15

Note: DB, .env, venv/, installers are gitignored — only source code syncs

10. Failure modes and their signatures
SymptomRoot causeFix
ModuleNotFoundError: No module named 'flask'venv not activesource venv/bin/activate
unable to open database fileDB path resolution brokenCheck _resolve_db_uri(); ensure data/ exists
no such column: XModel changed, table not migratedALTER TABLE ADD COLUMN OR set up Flask-Migrate
Login POST returns 200Wrong password, cookie dropped, or stale browser cookieCheck [LOGIN] debug lines in server output
Port already in useAnother process on FLASK_PORTpkill -f "python app.py" or change port
Two banners printedDebug reloader runningConfirm use_reloader=False in app.py
Wrong themeTemplate hardcodes colors or doesn't extend baseCheck grep -L "extends"
Template not foundMissing directorymkdir -p app/templates/<dir>
11. Extensibility points (for next features)
Adding a new service
app/services/new_service.py

Import in relevant route

If it holds state, add a get_singleton() pattern like rate_engine

If it calls an external API, put keys in .env and read via os.getenv()

Adding a new model
Create app/models/new_model.py

Register in app/models/__init__.py

ALTER TABLE in SQLite OR (better) set up Flask-Migrate

If it needs admin CRUD, add routes to admin.py

Adding a new route module
app/routes/new_module.py with new_bp = Blueprint('new', __name__)

Register in app/routes/__init__.py

Register in create_app(): app.register_blueprint(new_bp, url_prefix='/new')

Adding a new template
app/templates/new/page.html

Must start with {% extends "base.html" %}

Fill {% block content %}

Optional: override {% block scripts %} for page JS

Adding a new admin API
Add route to admin.py with @admin_required decorator

Return jsonify(...)

Consume from the dashboard JS

Adding a new theme
Add [data-theme="yourtheme"] { --bg: ...; --surface: ...; ... } to admin.css

Add option to base.html theme menu

Add to order array in theme cycle if applicable

12. Production target (future)
text
Cloudflare (DNS + WAF)
    ↓
Cloudflare Tunnel (no exposed ports)
    ↓
Nginx (TLS termination, static files, reverse proxy)
    ↓
Gunicorn (4 workers, threads)  →  Flask app
    ↓
PostgreSQL 16 (primary)  +  Redis (cache + rate limit + sessions)
Deployment checklist (partial — full version in ROADMAP.md):

□ Rotate SECRET_KEY
□ Change admin password
□ Set FLASK_ENV=production
□ SESSION_COOKIE_SECURE=True
□ Configure CSRF (Flask-WTF)
□ Configure Redis for cache + limiter + sessions
□ Configure PostgreSQL and migrate
□ Set up Gunicorn systemd unit
□ Nginx config + Let's Encrypt
□ Cloudflare Tunnel
□ Monitoring (Sentry, Prometheus)
□ Logging aggregation
□ Real KYC / sanctions providers
□ Real crypto custody
□ Legal review of licensing requirements
End of architecture.
