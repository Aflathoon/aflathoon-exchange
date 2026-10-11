# Aflathoon Exchange Platform — Project State

> **Purpose of this file:** complete handoff document. If you're a fresh AI session reading this, you now know everything about the project. Read this file, then `ARCHITECTURE.md`, then `ROADMAP.md`. You can resume work immediately.

**Last updated:** 2026-10-11
**Owner:** Aflathoon (GitHub: https://github.com/Aflathoon)
**Repo:** https://github.com/Aflathoon/aflathoon-exchange.git
**Local path:** `~/aflathoon_exchange`
**Host OS:** Ubuntu 26.04 (KDE Plasma)
**Python:** 3.14 (in `venv/`)
**Status:** MVP working — auth, exchange, booking, compliance, admin all functional. Not yet public. Not yet licensed for live trading.

---

## 1. What this project is

A multi-asset exchange and logistics platform that:

- Converts between **fiat, crypto, and commodities** with a **6.5% platform spread**
- Computes **freight, insurance, and war-risk premiums** for shipping
- Tracks **regulatory licenses and compliance deadlines**
- Provides an **admin dashboard** for transactions, positions, users
- Enforces a **license guard** that hard-blocks live trading until licenses are active
- Uses a **light/dark/auto theme** consistently across every page

**Not yet built:** user/company registration expansion, social login, crypto↔fiat booking with real settlement, P2P module, live news ticker, live rate APIs.

---

## 2. Directory structure
~/aflathoon_exchange/
├── app.py # Flask entrypoint, port-pinning with fallback
├── run.sh # Startup wrapper (activates venv, runs app.py)
├── verify_install.sh # Self-check for files, DB, admin user, port
├── requirements.txt # Python deps
├── .env # Secrets (NOT in git)
├── .env.example # Template (safe to commit)
├── .gitignore # Hardened — excludes venv, data, .env, installers
├── PROJECT_STATE.md # ← this file
├── ARCHITECTURE.md # System architecture (generated separately)
├── ROADMAP.md # Next features (generated separately)
│
├── app/
│ ├── init.py # create_app() factory + _resolve_db_uri() + extensions
│ ├── models/
│ │ ├── init.py
│ │ ├── user.py # User (Mixin, kyc_status, is_admin, is_active)
│ │ ├── transaction.py # Transaction, TransactionStatus, TransactionType, next_reference()
│ │ ├── rate.py # ExchangeRate (unused; kept for future rate history)
│ │ ├── shipping.py # Carrier, ShippingQuote
│ │ └── license.py # License, Deadline, ComplianceDocument
│ ├── routes/
│ │ ├── init.py # Registers all blueprints
│ │ ├── main.py # /, /health
│ │ ├── auth.py # /auth/login, /register, /logout, /change-password
│ │ ├── exchange.py # /exchange/, /convert, /book, /source, /rates
│ │ ├── admin.py # /admin/ + API endpoints (stats, positions, pnl, ticker, balance, recent-transactions, blotter, users)
│ │ ├── logistics.py # /logistics/, /quote
│ │ └── compliance.py # /compliance/ + license/deadline/document CRUD + CSV export
│ ├── services/
│ │ ├── init.py
│ │ ├── rate_engine.py # RateEngine with live-API-ready + layered fallback + background refresh
│ │ ├── margin.py # calculate_margin() — single 6.5% spread
│ │ ├── booking.py # book_trade() — persists quote as Transaction
│ │ ├── war_risk.py # Dynamic war-risk premium by corridor
│ │ ├── license_guard.py # assert_live_trading_allowed() + missing_licenses()
│ │ ├── compliance.py # Stubs for KYC/sanctions/PEP (not wired to real provider)
│ │ └── crypto_custody.py # Stub — REQUIRES external provider before use
│ ├── templates/
│ │ ├── base.html # ★ Shared layout: sidebar, topbar, theme toggle, source badge
│ │ ├── index.html # extends base
│ │ ├── auth/
│ │ │ ├── login.html # standalone + theme-aware
│ │ │ ├── register.html # standalone + theme-aware
│ │ │ └── change_password.html # extends base
│ │ ├── exchange/dashboard.html # extends base — Convert + Book trade
│ │ ├── logistics/quote.html # extends base — freight quote
│ │ ├── admin/
│ │ │ ├── dashboard.html # extends base — full Approx-style dashboard
│ │ │ ├── blotter.html # extends base — paginated transaction table
│ │ │ ├── positions.html # extends base — net/out/in by currency
│ │ │ └── users.html # extends base — user management
│ │ └── compliance/overview.html # extends base — licenses, deadlines, documents
│ └── static/css/
│ └── admin.css # ★ Theme variables (dark + light + auto) + layout
│
├── compliance/
│ ├── README.md
│ ├── licenses/ # PDF certificates
│ ├── deadlines/ # Calendar exports
│ ├── documents/ # Uploaded via /compliance/document/upload
│ │ └── private/ # gitignored
│ ├── insurance/ # War-risk policies
│ └── kyc_templates/ # Reusable forms
│
├── scripts/
│ ├── find_free_port.py # Dynamic port finder (9100–9999 range for prod)
│ ├── git-sync.sh # Auto-commit + push (cron)
│ ├── backup_db.sh # SQLite .backup + rotate 30
│ └── backup_full.sh # DB + config snapshot, rotate 14
│
├── data/
│ ├── exchange.db # SQLite (gitignored)
│ └── backups/ # DB snapshots
│
├── logs/ # gitignored
├── tests/ # empty — pytest
└── migrations/ # Flask-Migrate (NOT YET SET UP)

text

---

## 3. Key architectural decisions

### 3.1 Database path resolution (CRITICAL)

`app/__init__.py` has a `_resolve_db_uri()` function:

- Reads `DATABASE_URL` from env, but **only trusts Postgres URLs**
- For SQLite, **always computes an absolute path** from `__file__` → `<project_root>/data/exchange.db`
- Creates the `data/` directory itself before returning

**Why:** Flask-SQLAlchemy silently resolves relative SQLite paths against `instance_path`, not `cwd`. This caused hours of debugging — server read `instance/data/exchange.db` while scripts wrote to `data/exchange.db`.

**Never revert this.** If you see `no such column` or `unable to open database file`, check `[app] DB URI:` printed on startup — it must point to `~/aflathoon_exchange/data/exchange.db`.

### 3.2 Margin model (6.5% single spread)

`app/services/margin.py` + `rate_engine.py`:
mid_rate = market mid (from FALLBACK_RATES or API)
customer_rate = mid_rate × (1 − 0.065) ← spread embedded here
gross = amount × customer_rate
net_to_customer = gross ← NO second deduction
platform_fee = gross × (margin / (1 − margin)) ← informational only

text

**Do NOT** deduct 6.5% twice. Earlier versions did, causing customer to lose ~13%.

`PLATFORM_MARGIN_PCT=0.065` in `.env` is the single source of truth.

### 3.3 Rate engine with layered fallback

`app/services/rate_engine.py` — singleton via `get_engine()`:

1. **Live API** (if `RATES_MODE=live` and API key set) — TickerLayer or SiftingIO
2. **Cache** (last successful fetch, within `RATES_STALE_AFTER_SECONDS=300`)
3. **Fallback** (`FALLBACK_RATES` hardcoded, always available)

Background thread refreshes every `RATES_REFRESH_SECONDS=60`.
`source_info()` returns `{source: 'live'|'cache'|'fallback', last_error, ...}` — surfaced as the badge in the UI.

Currently `RATES_MODE=demo` → always fallback. To go live: set `RATES_MODE=live` and add `TICKERLAYER_API_KEY` (or `SIFTINGIO_API_KEY`) to `.env`.

### 3.4 License guard (safety net)

`app/services/license_guard.py`:

- `assert_live_trading_allowed()` — aborts with 451/503 if licenses missing
- `missing_licenses()` — returns list of license types required but not active

Called from `/exchange/book` only. `/exchange/convert` (indicative quote) is **not** gated — quotes are free, bookings are not. This is intentional and follows real-world practice.

**To enable live booking:**
1. Register all required licenses at `/compliance/`
2. Mark them `status='active'` and set valid `expiry_date`
3. Set `LIVE_TRADING_ENABLED=true` in `.env`
4. Restart

### 3.5 War-risk premium (loss prevention)

`app/services/war_risk.py`:

- `HIGH_RISK_CORRIDORS` — hardcoded list of sanctioned/conflict zones (IR, RU, SY, YE, LY, UA, IL)
- Base premium 0.25% of freight; max 5% for high-risk
- `AUTO_HEDGE=true` adds a surcharge if premium exceeds what the 6.5% margin can absorb

**Why:** war-risk insurance premiums can spike from 0.25% to 3%+ overnight during geopolitical events. Without this, the platform sells below cost.

### 3.6 Booking flow
Client → POST /exchange/convert → quote only (no DB)
Client → POST /exchange/book → creates Transaction row
status = STAGED by default
status = CONFIRMED if admin + LIVE_TRADING_ENABLED + licenses OK

text

Reference format: `TX-YYYY-NNNNNN` (via `next_reference()`).

Margin is snapshotted at booking time in `margin_amount` — P&L always reflects what was actually earned, not what the current rate says.

### 3.7 Theme system

- Cookie `afl_theme` with values `dark` | `light` | `auto`
- Set via `data-theme="..."` on `<html>` before CSS parses (prevents FOUC)
- All colors via CSS variables in `app/static/css/admin.css`:
  - `:root, [data-theme="dark"]` → dark palette
  - `[data-theme="light"]` → light palette
  - `@media (prefers-color-scheme: light) [data-theme="auto"]` → auto
- Every page extends `base.html` **except** `auth/login.html` and `auth/register.html` (standalone, but theme-aware)

**If a new page shows wrong theme:** either it doesn't extend `base.html`, or it hardcodes colors instead of using `var(--…)`.

---

## 4. Environment variables (`.env`)
FLASK_APP=app.py
FLASK_ENV=development
FLASK_PORT=9105 # Pinned — else finds free port above 9100
SECRET_KEY=<64 hex chars> # Generated — DO NOT COMMIT

DATABASE_URL=sqlite:////home/aflathoon/aflathoon_exchange/data/exchange.db

PLATFORM_MARGIN_PCT=0.065
SHIPPING_MARGIN_PCT=0.065
INSURANCE_MARGIN_PCT=0.065

WAR_RISK_BASE_PCT=0.0025
WAR_RISK_MAX_PCT=0.05
WAR_RISK_AUTO_HEDGE=true

RATES_MODE=demo # 'demo' | 'live'
RATES_PRIMARY=tickerlayer # 'tickerlayer' | 'siftingio'
RATES_REFRESH_SECONDS=60
RATES_STALE_AFTER_SECONDS=300
TICKERLAYER_API_KEY= # empty = fallback
SIFTINGIO_API_KEY=

CRYPTO_CUSTODY_MODE=external_multisig
CRYPTO_CUSTODY_PROVIDER=none
CRYPTO_HOT_WALLET_MAX_USD=5000

LICENSE_ENFORCEMENT=strict
LICENSE_JURISDICTION=UK
LICENSE_REQUIRED_TYPES=msb,money_transmitter,crypto_asset
LIVE_TRADING_ENABLED=false # ← blocks live booking until true

CACHE_TYPE=SimpleCache
CACHE_DEFAULT_TIMEOUT=300
RATELIMIT_DEFAULT=100/hour
RATELIMIT_STORAGE_URI=memory://

ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@localhost

text

---

## 5. Database schema (SQLite)

Tables (all auto-created via `db.create_all()`):

### `users`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| username | varchar(64) UNIQUE | |
| email | varchar(120) UNIQUE | |
| password_hash | varchar(256) | scrypt (Werkzeug default) |
| is_admin | bool | |
| is_active | bool | |
| kyc_status | varchar(20) | pending/verified/rejected |
| kyc_tier | int | 0–2 |
| lei_code | varchar(20) | for derivatives |
| created_at, last_login | datetime | |

### `transactions`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| reference | varchar(40) UNIQUE | `TX-YYYY-NNNNNN` |
| user_id | FK users | |
| transaction_type | enum | spot/forward/swap/shipping/insurance |
| status | enum | pre_staged/staged/confirmed/settled/cancelled/failed |
| from_currency, to_currency | varchar(10) | |
| from_amount, to_amount | numeric(20,8) | |
| mid_rate | numeric(20,10) | market mid at booking |
| customer_rate | numeric(20,10) | mid × (1−margin) |
| platform_margin | numeric(20,8) | 0.065 |
| margin_amount | numeric(20,8) | platform revenue |
| rate_source | varchar(20) | live/cache/fallback |
| shipping_cost, insurance_cost, war_risk_premium | numeric(20,8) | 0 for FX |
| carrier_id | FK carriers | nullable |
| kyc_verified, sanctions_checked | bool | compliance snapshot |
| compliance_notes | text | |
| created_at, updated_at, confirmed_at, settled_at, cancelled_at | datetime | |

### `carriers`
| Column | Type |
|---|---|
| id, name, mode, commodity_classes | |
| base_rate_per_km, base_rate_per_kg | numeric |
| insurance_pct, war_risk_multiplier | numeric |
| is_active, created_at | |

### `shipping_quotes`
(Not yet used by UI — future)

### `licenses`
| Column | Type | Notes |
|---|---|---|
| id, name | | |
| license_type | varchar(80) | msb/money_transmitter/crypto_asset |
| jurisdiction, authority, license_number | varchar | |
| status | varchar(30) | pending/active/expired/suspended/revoked |
| issued_date, expiry_date | date | |
| renewal_cost, currency | numeric/varchar | |
| document_path | varchar(400) | |
| notes | text | |
| days_to_expiry, is_valid, urgency | @property | computed |

### `deadlines`
Similar structure — `title`, `category`, `due_date`, `recurrence`, `responsible`, `cost_estimate`, `urgency`, `days_left`.

### `compliance_documents`
| Column | Type |
|---|---|
| id, title, doc_type | |
| file_path, file_size, mime_type | |
| version, issued_by | |
| issued_date, expiry_date | |
| confidential, uploaded_at | |

### `exchange_rates`
(Unused — kept for future rate history/audit)

---

## 6. Routes reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | Landing page |
| GET | `/health` | — | Health check JSON |
| GET/POST | `/auth/login` | — | Login |
| GET/POST | `/auth/register` | — | Register |
| GET | `/auth/logout` | ✔ | Logout |
| GET/POST | `/auth/change-password` | ✔ | Change password |
| GET | `/exchange/` | ✔ | Exchange page |
| POST | `/exchange/convert` | ✔ | Quote (no DB write) |
| POST | `/exchange/book` | ✔ | Persist as Transaction |
| GET | `/exchange/source` | ✔ | Rate engine state |
| GET | `/exchange/rates` | — | All rates for base |
| GET | `/logistics/` | ✔ | Freight quote page |
| POST | `/logistics/quote` | ✔ | Freight calculation |
| GET | `/compliance/` | admin | Overview |
| POST | `/compliance/license/add` | admin | |
| POST | `/compliance/deadline/add` | admin | |
| POST | `/compliance/document/upload` | admin | Multipart, max 16 MB |
| GET | `/compliance/export.csv` | admin | Full CSV export |
| GET | `/compliance/api/upcoming` | admin | Alerts JSON |
| GET | `/admin/` | admin | Dashboard |
| GET | `/admin/api/stats` | admin | |
| GET | `/admin/api/balance` | admin | BTC equiv + net USD |
| GET | `/admin/api/ticker` | admin | Spot rates |
| GET | `/admin/api/pnl?days=30` | admin | Daily margin series |
| GET | `/admin/api/positions` | admin | Net/out/in by currency |
| GET | `/admin/api/recent-transactions?limit=10` | admin | |
| GET | `/admin/blotter` | admin | Paginated table |
| GET | `/admin/positions` | admin | UI for positions |
| GET | `/admin/users` | admin | User list |
| POST | `/admin/users/<id>/toggle_admin` | admin | |
| POST | `/admin/users/<id>/toggle_active` | admin | |
| POST | `/admin/users/<id>/reset_password` | admin | |

---

## 7. Credentials (current dev state)

- **Admin login:** `admin` / `Aflathoon123`
- **Change before exposing publicly.** No password recovery mechanism exists.
- **SECRET_KEY** in `.env` — regenerate with `python -c "import secrets; print(secrets.token_hex(32))"`

---

## 8. Known issues / gotchas

| Issue | Workaround |
|---|---|
| **First Flask-Limiter startup warning** | Cosmetic. Set `RATELIMIT_STORAGE_URI=memory://` (already in `.env`) |
| **Debug reloader spawns two processes** | Fixed: `use_reloader=False` in `app.py` + pinned `FLASK_PORT` |
| **Flask-SQLAlchemy ignores relative SQLite paths** | Fixed: absolute path in `_resolve_db_uri()` |
| **Cache backend name changed in Flask-Caching 2.x** | Fixed: `CACHE_TYPE=SimpleCache` (capitalized) |
| **Adding a model column breaks SQLite** | Manual `ALTER TABLE ADD COLUMN` needed; **Flask-Migrate not yet set up** |
| **`Query.get()` deprecated in SQLAlchemy 2.x** | Fixed: uses `db.session.get(Model, pk)` |
| **Crypto custody is a stub** | Never enable withdrawals until `crypto_custody.py` is wired to Fireblocks/BitGo/HSM |
| **KYC/sanctions services are stubs** | `compliance.py` returns "clear" for everything — replace before production |

---

## 9. What works today (verified)

- ✅ Flask app boots on pinned port with fallback
- ✅ SQLite DB created at absolute path
- ✅ Admin user seeded
- ✅ Login / logout / change-password
- ✅ Theme toggle (dark/light/auto) across all pages
- ✅ Sidebar layout consistent
- ✅ Rate engine with fallback chain + source badge
- ✅ Exchange quote (USD↔EUR verified: 1000 USD → 860.20 EUR, 59.80 EUR margin)
- ✅ Book trade creates Transaction row
- ✅ Recent transactions table on `/exchange/`
- ✅ Admin dashboard shows balance, ticker, stats, P&L, top currencies, activity
- ✅ Blotter with pagination + filters
- ✅ Positions API + UI
- ✅ Users admin (promote, deactivate, reset password)
- ✅ Compliance: licenses, deadlines, documents, alerts, calendar, CSV export
- ✅ Logistics quote with war-risk premium
- ✅ Backup scripts (DB + full)
- ✅ Verify install script
- ✅ KDE launchers installed
- ✅ Git repo initialized and pushed

---

## 10. What's NOT built yet

- ❌ Real live rate API integration (code exists, key missing)
- ❌ User & company registration expansion (KYC fields, tiered onboarding)
- ❌ Social login (Google, Telegram, Facebook)
- ❌ Email verification / password recovery
- ❌ Crypto↔fiat booking with real settlement
- ❌ P2P module (escrow, reputation, disputes)
- ❌ News ticker (crypto, fiat, gold, silver, iron, commodities)
- ❌ Forward/swap contracts (only spot supported)
- ❌ LEI capture (field exists in User, no UI)
- ❌ Real KYC/sanctions provider (Onfido, Sumsub, Refinitiv)
- ❌ Real crypto custody (Fireblocks, BitGo, multi-sig)
- ❌ Flask-Migrate / Alembic
- ❌ Redis-backed rate limiter + session store
- ❌ Postgres migration
- ❌ Cloudflare Tunnel exposure
- ❌ CSRF protection on forms
- ❌ Failed-login throttling
- ❌ HTTPS / secure cookies
- ❌ Email sending (SMTP / SendGrid / Postmark)
- ❌ Telegram bot notifications
- ❌ Automated tests (pytest)

---

## 11. Commands cheatsheet

```bash
# Enter project + venv (ALWAYS do both)
cd ~/aflathoon_exchange
source venv/bin/activate          # prompt MUST show (venv)

# Start server
./run.sh                          # or: python app.py
# Stop: Ctrl+C

# Kill any stray server
pkill -f "python app.py"

# Verify install
./verify_install.sh

# Backups
./scripts/backup_db.sh
./scripts/backup_full.sh

# Git sync (auto-commit + push)
./scripts/git-sync.sh

# Check port
ss -ltn | grep 9105

# View DB tables
sqlite3 data/exchange.db ".tables"

# Inspect a table schema
sqlite3 data/exchange.db "PRAGMA table_info(transactions);"

# Reset admin password
export NEWPW='YourNewPasswordHere'
python3 - << 'PY'
import os
from app import create_app, db
from app.models.user import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    u.set_password(os.environ['NEWPW'])
    db.session.commit()
    print('OK' if u.check_password(os.environ['NEWPW']) else 'FAIL')
PY
unset NEWPW

# GitHub push (first time, HTTPS)
git push -u origin main

# GitHub push (subsequent)
git push
12. Cron jobs installed
text
15 3 * * * /home/aflathoon/aflathoon_exchange/scripts/git-sync.sh    >> .../logs/git-sync.log 2>&1
30 3 * * * /home/aflathoon/aflathoon_exchange/scripts/backup_full.sh >> .../logs/backup.log  2>&1
Verify: crontab -l

13. Tech stack
LayerChoiceWhy
Web frameworkFlask 3.xLightweight, easy to reason about
ORMSQLAlchemy 2.x via Flask-SQLAlchemyStandard
Migrations— (planned: Flask-Migrate/Alembic)Manual ALTER TABLE for now
AuthFlask-LoginSession-based
PasswordsWerkzeug generate_password_hash (scrypt)Framework default
CachingFlask-Caching (SimpleCache)Move to Redis for prod
Rate limitingFlask-Limiter (memory)Move to Redis for prod
DB (dev)SQLiteSimple, no daemon
DB (prod target)PostgreSQLConcurrency, JSON columns
FrontendVanilla JS + CSS variablesNo build step
Server (prod target)Gunicorn + NginxStandard
14. Security posture
Working:

Session cookies: HttpOnly, SameSite=Lax, unique name aflathoon_session

Password hashing: scrypt (strong)

License guard blocks live trading

Crypto custody stub refuses to hold keys

.env gitignored

.gitignore hardened

Missing (add before public exposure):

HTTPS

CSRF tokens on POST forms

Failed-login throttling (currently unlimited attempts)

Secure flag on cookies (currently False because HTTP)

Per-user rate limiting (currently per-IP only)

CSP headers

2FA for admin

Audit log table

15. Resume instructions for next session
Read this file entirely.

cd ~/aflathoon_exchange && source venv/bin/activate — venv MUST be active for all Python work.

./verify_install.sh — confirms environment is intact.

./run.sh — starts server on port 9105 (prints [app] DB URI: on startup — verify it points to ~/aflathoon_exchange/data/exchange.db).

Log in at http://127.0.0.1:9105/auth/login as admin / Aflathoon123.

git log --oneline -10 and git status — check what was last committed.

Read ROADMAP.md for next features (in priority order).

Long-paste warning: never paste >15 lines as shell commands. Use cat > file << 'EOF' … EOF heredocs. The 'EOF' in single quotes prevents variable expansion.

Common failure modes:

ModuleNotFoundError: No module named 'flask' → venv not active

no such column → SQLite needs ALTER TABLE ADD COLUMN

unable to open database file → absolute DB path got reverted (see §3.1)

Login returns 200 instead of 302 → check [LOGIN] debug lines in server output

Wrong theme → page doesn't extend base.html

16. Contact / attribution
GitHub: https://github.com/Aflathoon

Repo: https://github.com/Aflathoon/aflathoon-exchange.git

Built with assistance from an AI pair-programmer (Claude/Copilot), iteratively, over multiple sessions.

End of project state.
