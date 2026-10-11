# Aflathoon Exchange Platform — Project State

> Complete handoff document. Read this file, then ARCHITECTURE.md, then ROADMAP.md.

**Last updated:** 2026-10-11
**Owner:** Aflathoon (GitHub: https://github.com/Aflathoon)
**Repo:** https://github.com/Aflathoon/aflathoon-exchange.git
**Local path:** ~/aflathoon_exchange
**Host OS:** Ubuntu 26.04 (KDE Plasma)
**Python:** 3.14 (in venv/)
**Status:** MVP working — auth, exchange, booking, compliance, admin all functional. Not yet public.

---

## 1. What this project is

A multi-asset exchange and logistics platform that:

- Converts between fiat, crypto, and commodities with a 6.5% platform spread
- Computes freight, insurance, and war-risk premiums for shipping
- Tracks regulatory licenses and compliance deadlines
- Provides an admin dashboard for transactions, positions, users
- Enforces a license guard that hard-blocks live trading until licenses are active
- Uses a light/dark/auto theme consistently across every page

Not yet built: user/company registration expansion, social login, crypto-to-fiat booking with real settlement, P2P module, live news ticker, live rate APIs.

---

## 2. Directory structure
~/aflathoon_exchange/
app.py Flask entrypoint, port-pinning with fallback
run.sh Startup wrapper
verify_install.sh Self-check
requirements.txt Python deps
.env Secrets (NOT in git)
.env.example Template
.gitignore Hardened
PROJECT_STATE.md This file
ARCHITECTURE.md
ROADMAP.md

app/
init.py create_app() factory + _resolve_db_uri()
models/
user.py, transaction.py, rate.py, shipping.py, license.py
routes/
main.py, auth.py, exchange.py, admin.py, logistics.py, compliance.py
services/
rate_engine.py, margin.py, booking.py, war_risk.py,
license_guard.py, compliance.py, crypto_custody.py
templates/
base.html, index.html
auth/{login,register,change_password}.html
exchange/dashboard.html
logistics/quote.html
admin/{dashboard,blotter,positions,users}.html
compliance/overview.html
static/css/admin.css

compliance/{licenses,deadlines,documents,insurance,kyc_templates}/
scripts/{find_free_port.py,git-sync.sh,backup_db.sh,backup_full.sh}
data/exchange.db
logs/
tests/
migrations/ Flask-Migrate (NOT YET SET UP)

text

---

## 3. Key architectural decisions

### 3.1 Database path resolution (CRITICAL)

app/__init__.py has _resolve_db_uri():
- Reads DATABASE_URL, only trusts Postgres URLs
- For SQLite, always computes absolute path from __file__
- Creates data/ directory before returning

Why: Flask-SQLAlchemy resolves relative SQLite paths against instance_path, not cwd. Caused hours of debugging.

Never revert. If you see "no such column" or "unable to open database file", check [app] DB URI: printed on startup — must point to ~/aflathoon_exchange/data/exchange.db

### 3.2 Margin model (6.5% single spread)

mid_rate        = market mid
customer_rate   = mid_rate x (1 - 0.065)
gross           = amount x customer_rate
net_to_customer = gross (NO second deduction)
platform_fee    = gross x (margin / (1 - margin))  informational only

Do NOT deduct 6.5% twice. PLATFORM_MARGIN_PCT=0.065 in .env is the single source of truth.

### 3.3 Rate engine with layered fallback

1. Live API (if RATES_MODE=live and API key set)
2. Cache (last fetch within RATES_STALE_AFTER_SECONDS=300)
3. Fallback (FALLBACK_RATES hardcoded)

Background thread refreshes every 60s. source_info() returns {source, last_error}.

Currently RATES_MODE=demo. To go live: set RATES_MODE=live and add API key.

### 3.4 License guard (safety net)

- assert_live_trading_allowed() — aborts with 451/503 if licenses missing
- missing_licenses() — returns list of required licenses not active

Called from /exchange/book only. /exchange/convert is NOT gated — quotes are free, bookings are not.

To enable live booking:
1. Register licenses at /compliance/
2. Mark status=active with valid expiry_date
3. Set LIVE_TRADING_ENABLED=true in .env
4. Restart

### 3.5 War-risk premium (loss prevention)

- HIGH_RISK_CORRIDORS hardcoded (IR, RU, SY, YE, LY, UA, IL)
- Base premium 0.25% of freight; max 5% for high-risk
- AUTO_HEDGE=true adds surcharge if premium exceeds what margin can absorb

### 3.6 Booking flow

Client -> POST /exchange/convert   -> quote only
Client -> POST /exchange/book      -> creates Transaction row
                                      status = STAGED by default
                                      status = CONFIRMED if admin + live + licenses OK

Reference format: TX-YYYY-NNNNNN. Margin snapshotted at booking time.

### 3.7 Theme system

- Cookie afl_theme: dark | light | auto
- data-theme="..." on <html> before CSS parses
- All colors via CSS variables in app/static/css/admin.css

Every page extends base.html EXCEPT auth/login.html and auth/register.html.

---

## 4. Environment variables (.env)
FLASK_APP=app.py
FLASK_ENV=development
FLASK_PORT=9105
SECRET_KEY=<64 hex chars>
DATABASE_URL=sqlite:////home/aflathoon/aflathoon_exchange/data/exchange.db
PLATFORM_MARGIN_PCT=0.065
WAR_RISK_BASE_PCT=0.0025
WAR_RISK_MAX_PCT=0.05
WAR_RISK_AUTO_HEDGE=true
RATES_MODE=demo
RATES_PRIMARY=tickerlayer
RATES_REFRESH_SECONDS=60
RATES_STALE_AFTER_SECONDS=300
TICKERLAYER_API_KEY=
SIFTINGIO_API_KEY=
CRYPTO_CUSTODY_MODE=external_multisig
CRYPTO_CUSTODY_PROVIDER=none
CRYPTO_HOT_WALLET_MAX_USD=5000
LICENSE_ENFORCEMENT=strict
LICENSE_JURISDICTION=UK
LICENSE_REQUIRED_TYPES=msb,money_transmitter,crypto_asset
LIVE_TRADING_ENABLED=false
CACHE_TYPE=SimpleCache
CACHE_DEFAULT_TIMEOUT=300
RATELIMIT_DEFAULT=100/hour
RATELIMIT_STORAGE_URI=memory://
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@localhost

text

---

## 5. Database schema

### users
id, username (unique), email (unique), password_hash (scrypt), is_admin, is_active, kyc_status, kyc_tier, lei_code, created_at, last_login

### transactions
id, reference, user_id, transaction_type, status, from_currency, to_currency, from_amount, to_amount, mid_rate, customer_rate, platform_margin, margin_amount, rate_source, shipping_cost, insurance_cost, war_risk_premium, carrier_id, kyc_verified, sanctions_checked, compliance_notes, created_at, updated_at, confirmed_at, settled_at, cancelled_at

### carriers
id, name, mode, commodity_classes, base_rate_per_km, base_rate_per_kg, insurance_pct, war_risk_multiplier, is_active, created_at

### licenses
id, name, license_type, jurisdiction, authority, license_number, status, issued_date, expiry_date, renewal_cost, currency, document_path, notes, created_at, updated_at

### deadlines
id, title, category, due_date, recurrence, responsible, cost_estimate, currency, status, linked_license_id, document_path, notes, created_at

### compliance_documents
id, title, doc_type, file_path, file_size, mime_type, version, issued_by, issued_date, expiry_date, confidential, uploaded_at

---

## 6. Routes reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | / | - | Landing page |
| GET | /health | - | Health check |
| GET/POST | /auth/login | - | Login |
| GET/POST | /auth/register | - | Register |
| GET | /auth/logout | yes | Logout |
| GET/POST | /auth/change-password | yes | Change password |
| GET | /exchange/ | yes | Exchange page |
| POST | /exchange/convert | yes | Quote |
| POST | /exchange/book | yes | Persist Transaction |
| GET | /exchange/source | yes | Rate engine state |
| GET | /exchange/rates | - | All rates for base |
| GET | /logistics/ | yes | Freight page |
| POST | /logistics/quote | yes | Freight calc |
| GET | /compliance/ | admin | Overview |
| POST | /compliance/license/add | admin | |
| POST | /compliance/deadline/add | admin | |
| POST | /compliance/document/upload | admin | |
| GET | /compliance/export.csv | admin | |
| GET | /admin/ | admin | Dashboard |
| GET | /admin/api/stats | admin | |
| GET | /admin/api/balance | admin | |
| GET | /admin/api/ticker | admin | |
| GET | /admin/api/pnl | admin | |
| GET | /admin/api/positions | admin | |
| GET | /admin/api/recent-transactions | admin | |
| GET | /admin/blotter | admin | |
| GET | /admin/positions | admin | |
| GET | /admin/users | admin | |
| POST | /admin/users/<id>/toggle_admin | admin | |
| POST | /admin/users/<id>/toggle_active | admin | |
| POST | /admin/users/<id>/reset_password | admin | |

---

## 7. Credentials (dev)

- Admin: admin / Aflathoon123
- Change before exposing publicly.
- Regenerate SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"

---

## 8. Known issues / gotchas

| Issue | Workaround |
|---|---|
| Flask-Limiter startup warning | Cosmetic. RATELIMIT_STORAGE_URI=memory:// set |
| Debug reloader double-process | Fixed: use_reloader=False + pinned port |
| Flask-SQLAlchemy relative SQLite path | Fixed: absolute path in _resolve_db_uri() |
| Cache backend name Flask-Caching 2.x | Fixed: CACHE_TYPE=SimpleCache |
| Adding model column breaks SQLite | Manual ALTER TABLE; Flask-Migrate not set up |
| Query.get() deprecated SQLAlchemy 2.x | Fixed: db.session.get(Model, pk) |
| Crypto custody is a stub | Never enable withdrawals until wired |
| KYC/sanctions services are stubs | Replace before production |

---

## 9. What works today (verified)

- Flask app boots on pinned port with fallback
- SQLite DB at absolute path
- Admin user seeded
- Login / logout / change-password
- Theme toggle across all pages
- Sidebar layout consistent
- Rate engine with fallback + source badge
- Exchange quote (USD->EUR verified: 1000 USD -> 860.20 EUR, 59.80 EUR margin)
- Book trade creates Transaction row
- Recent transactions table on /exchange/
- Admin dashboard: balance, ticker, stats, P&L, top currencies, activity
- Blotter with pagination + filters
- Positions API + UI
- Users admin (promote, deactivate, reset password)
- Compliance: licenses, deadlines, documents, alerts, calendar, CSV
- Logistics quote with war-risk premium
- Backup scripts (DB + full)
- Verify install script
- KDE launchers installed
- Git repo initialized and pushed

---

## 10. What's NOT built yet

- Real live rate API integration
- User & company registration expansion
- Social login (Google, Telegram, Facebook)
- Email verification / password recovery
- Crypto-to-fiat booking with settlement
- P2P module
- News ticker
- Forward/swap contracts
- LEI capture UI
- Real KYC/sanctions provider
- Real crypto custody
- Flask-Migrate / Alembic
- Redis cache + rate limiter
- Postgres migration
- Cloudflare Tunnel
- CSRF protection
- Failed-login throttling
- HTTPS / secure cookies
- Email sending
- Telegram bot
- Automated tests

---

## 11. Commands cheatsheet

cd ~/aflathoon_exchange
source venv/bin/activate
./run.sh
pkill -f "python app.py"
./verify_install.sh
./scripts/backup_db.sh
./scripts/backup_full.sh
./scripts/git-sync.sh
ss -ltn | grep 9105
sqlite3 data/exchange.db ".tables"

Reset admin password:
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

---

## 12. Cron jobs

15 3 * * * .../scripts/git-sync.sh    >> .../logs/git-sync.log 2>&1
30 3 * * * .../scripts/backup_full.sh >> .../logs/backup.log  2>&1

Verify: crontab -l

---

## 13. Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3.x |
| ORM | SQLAlchemy 2.x |
| Migrations | planned: Flask-Migrate |
| Auth | Flask-Login |
| Passwords | Werkzeug scrypt |
| Caching | Flask-Caching SimpleCache |
| Rate limiting | Flask-Limiter memory |
| DB dev | SQLite |
| DB prod target | PostgreSQL |
| Frontend | Vanilla JS + CSS vars |
| Server prod target | Gunicorn + Nginx |

---

## 14. Security posture

Working:
- Session cookies HttpOnly, SameSite=Lax, unique name aflathoon_session
- scrypt password hashing
- License guard blocks live trading
- Crypto custody stub refuses to hold keys
- .env gitignored

Missing:
- HTTPS
- CSRF tokens
- Failed-login throttling
- Secure cookie flag
- Per-user rate limiting
- CSP headers
- 2FA for admin
- Audit log table

---

## 15. Resume instructions

1. Read this file entirely.
2. cd ~/aflathoon_exchange && source venv/bin/activate
3. ./verify_install.sh
4. ./run.sh
5. Log in at http://127.0.0.1:9105/auth/login as admin / Aflathoon123
6. git log --oneline -10
7. Read ROADMAP.md for next features

Long-paste warning: use nano or heredocs. Never paste >15 lines directly.

Common failure modes:
- ModuleNotFoundError: flask -> venv not active
- no such column -> SQLite needs ALTER TABLE
- unable to open database file -> absolute DB path reverted
- Login returns 200 -> check [LOGIN] debug lines
- Wrong theme -> page doesn't extend base.html

---

## 16. Contact

- GitHub: https://github.com/Aflathoon
- Repo: https://github.com/Aflathoon/aflathoon-exchange.git

End of project state.
Then in nano:

Press Ctrl+O → Enter to save

Press Ctrl+X to exit

Verify:

bash
wc -l PROJECT_STATE.md
head -20 PROJECT_STATE.md
Should show ~380 lines and the header.

Step 4 — Push to GitHub
bash
cd ~/aflathoon_exchange
./scripts/git-sync.sh

