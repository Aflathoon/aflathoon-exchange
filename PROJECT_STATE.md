
# Aflathoon Exchange Platform — Project State

> Handoff doc. Read this, then ARCHITECTURE.md, then ROADMAP.md.

**Last updated:** 2026-10-11
**Owner:** Aflathoon
**Repo:** https://github.com/Aflathoon/aflathoon-exchange.git
**Local path:** ~/aflathoon_exchange
**Host OS:** Ubuntu 26.04 (KDE Plasma)
**Python:** 3.14 (in venv/)
**Port:** 9105
**Status:** MVP complete. Not yet public.

---

## 1. What this project is

Multi-asset exchange and logistics platform with:

- Fiat ↔ fiat conversion with 6.5% embedded platform spread
- Freight booking with cost snapshots, waybills, carrier assignment
- KYC submission with document upload and admin review
- Company accounts with admin verification workflow
- Two-factor auth (TOTP + backup codes) for admin accounts
- Audit log of every admin action
- Live crypto prices (CoinGecko) + market data + trending
- RSS news from 5 crypto outlets with thumbnails
- Self-monitoring via rule-based AI Assistant + auto-alert engine
- Dark / light / auto theme across every page

Not yet built: crypto ↔ fiat booking, P2P, real KYC/sanctions,
production deployment.


---

## 2. Directory structure

    ~/aflathoon_exchange/
    ├── app.py                     Flask entrypoint, port pinning
    ├── run.sh / restart.sh        Startup helpers
    ├── verify_install.sh          Self-check
    ├── requirements.txt
    ├── .env / .env.example / .gitignore / .flaskenv
    ├── PROJECT_STATE.md (this) / ARCHITECTURE.md / ROADMAP.md
    ├── app/
    │   ├── __init__.py            create_app + _resolve_db_uri + engines
    │   ├── models/
    │   │   ├── user.py            profile, 2FA, email_verified, company_id
    │   │   ├── company.py         registration, LEI, verification
    │   │   ├── transaction.py     FX + shipping ledger
    │   │   ├── shipment.py        freight booking lifecycle
    │   │   ├── shipping.py        Carrier
    │   │   ├── license.py         License, Deadline, ComplianceDocument
    │   │   ├── email_token.py     verify + reset tokens
    │   │   ├── kyc_submission.py  document upload
    │   │   ├── audit_log.py       admin actions
    │   │   ├── alert.py           banner alerts
    │   │   └── rate.py            future rate history
    │   ├── routes/
    │   │   ├── main.py            /, /health
    │   │   ├── auth.py            login, register, 2FA, password, profile
    │   │   ├── exchange.py        FX quote + book
    │   │   ├── logistics.py       freight quote + book + bookings
    │   │   ├── admin.py           all admin pages + APIs
    │   │   ├── compliance.py      licenses, deadlines, docs, CSV
    │   │   ├── kyc.py             /kyc/
    │   │   ├── ticker.py          /api/prices, /api/news
    │   │   └── alerts.py          /api/alerts/*
    │   ├── services/
    │   │   ├── rate_engine.py     layered fallback + spread
    │   │   ├── margin.py          6.5% spread
    │   │   ├── booking.py         FX book_trade()
    │   │   ├── freight_booking.py freight book_shipment()
    │   │   ├── war_risk.py        dynamic premium
    │   │   ├── license_guard.py   live-trading gate
    │   │   ├── compliance.py      KYC/sanctions stubs
    │   │   ├── crypto_custody.py  stub (never holds keys)
    │   │   ├── email_sender.py    console + SMTP
    │   │   ├── email_templates.py text + HTML
    │   │   ├── two_factor.py      pyotp
    │   │   ├── audit.py           audit writer
    │   │   ├── csrf.py            session-token CSRF
    │   │   ├── rate_limit.py      per-user limiter
    │   │   ├── crypto_prices.py   CoinGecko
    │   │   ├── crypto_news.py     RSS + CoinGecko
    │   │   ├── price_alerts.py    >5% breaking alerts
    │   │   ├── alert_engine.py    findings → banners
    │   │   └── assistant.py       rule-based assistant
    │   ├── templates/             base + auth (12) + admin (11)
    │   └── static/
    │       ├── css/admin.css      themes + layout
    │       └── js/                reveal-password.js, csrf.js
    ├── compliance/                licenses, deadlines, docs, kyc_uploads
    ├── scripts/                   find_free_port, git-sync, backups
    ├── migrations/                Flask-Migrate
    ├── data/                      SQLite DB + backups (gitignored)
    └── logs/ tests/               (gitignored / future)


---

## 3. Key architectural decisions

### 3.1 Database path (CRITICAL)

_resolve_db_uri() always returns an absolute SQLite path under
project_root/data/exchange.db unless a Postgres URL is supplied.
Flask-SQLAlchemy resolves relative paths against instance_path,
causing hours of debugging. Never revert.

Startup prints [app] DB URI: ... verify after every restart.

### 3.2 Margin model (6.5% single spread)

    mid_rate        = market mid
    customer_rate   = mid_rate x (1 - 0.065)   <- spread embedded
    gross           = amount x customer_rate
    net_to_customer = gross                    <- NO second deduction
    platform_fee    = gross x margin/(1-margin) <- informational

PLATFORM_MARGIN_PCT=0.065 in .env is the single source of truth.

### 3.3 Rate engine layered fallback

1. Live API (if RATES_MODE=live and key)
2. Cache (within RATES_STALE_AFTER_SECONDS)
3. Fallback (FALLBACK_RATES - 27 currencies incl. MENA, Asia, metals)

Refresh every 60s. Currently demo mode means always fallback.

### 3.4 License guard

assert_live_trading_allowed() aborts with 451/503 if licenses
missing. Only on /exchange/book - quotes are free, bookings are not.

### 3.5 War-risk premium

High-risk corridors: IR, RU, SY, YE, LY, UA, IL. Base 0.25% of
freight; max 5%. AUTO_HEDGE=true adds surcharge if premium
exceeds margin cover.

### 3.6 Booking flow

    POST /exchange/convert -> quote only (no DB)
    POST /exchange/book    -> Transaction (STAGED or CONFIRMED)
    POST /logistics/book   -> Shipment + linked Transaction

Both snapshot costs at booking time.

### 3.7 Theme system

Cookie afl_theme = dark | light | auto. data-theme set on html
before CSS parses. All colours via CSS variables.

### 3.8 Shipment lifecycle

    quoted -> booked -> picked_up -> in_transit -> customs -> delivered
                        -> delayed       -> cancelled

Admin advances status; each transition stamps a timestamp and logs
to audit. Auto Transaction on booking.

### 3.9 Live data pipeline

- Prices: CoinGecko free, cached 90s
- News: RSS from CoinDesk, Cointelegraph, The Block, Decrypt,
  Bitcoin Magazine - cached 10 min. Images via 5-strategy fallback.
- Trending: CoinGecko /search/trending

### 3.10 Self-monitoring

Two background threads:
- alert_engine - every 5 min, findings to Alert rows
- price_alerts - every 5 min, >5% moves to breaking alerts

Each finding has an optional Fix button. All actions logged as
assistant.* in audit.

Both threads run inside their own app.app_context().

### 3.11 CSRF

Session token _csrf_token injected into POST forms by csrf.js
and into fetch() via wrapped window.fetch.

### 3.12 Rate limiting

services/rate_limit.py with @limit(key, max, window, by=...).
Applied: login 10/min/user, register 5/hr/IP, forgot/resend
3/hr/email, FX book 60/min/user, freight book 30/min/user.

### 3.13 Engine skip flag

FLASK_SKIP_ENGINES=1 prevents engines from starting on
create_app(). Use for CLI scripts, migrations, diagnostics.

---

## 4. Environment variables

    FLASK_APP=app.py
    FLASK_ENV=development
    FLASK_PORT=9105
    SECRET_KEY=<64 hex chars>
    DATABASE_URL=sqlite:////home/aflathoon/aflathoon_exchange/data/exchange.db

    PLATFORM_MARGIN_PCT=0.065
    SHIPPING_MARGIN_PCT=0.065
    INSURANCE_MARGIN_PCT=0.065

    WAR_RISK_BASE_PCT=0.0025
    WAR_RISK_MAX_PCT=0.05
    WAR_RISK_AUTO_HEDGE=true

    RATES_MODE=demo
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

    EMAIL_BACKEND=console
    EMAIL_FROM=Aflathoon Exchange <noreply@aflathoon.local>
    SMTP_HOST=
    SMTP_PORT=587
    SMTP_USER=
    SMTP_PASS=
    SMTP_USE_TLS=true
    EMAIL_VERIFY_TTL=172800
    PASSWORD_RESET_TTL=3600

    COINGECKO_BASE_URL=https://api.coingecko.com/api/v3
    COINGECKO_REFRESH_SECONDS=90
    NEWS_REFRESH_SECONDS=600

    ALERT_ENGINE_INTERVAL=300
    PRICE_ALERT_INTERVAL=300
    PRICE_ALERT_THRESHOLD=5.0
    PRICE_ALERT_WARN=3.0

    CACHE_TYPE=SimpleCache
    RATELIMIT_STORAGE_URI=memory://
    ADMIN_USERNAME=admin
    ADMIN_EMAIL=admin@localhost


---

## 5. Database schema

| Table | Purpose |
|---|---|
| users | Profile, 2FA, KYC, company link, email verify |
| companies | Company accounts + verification |
| transactions | Unified ledger (FX + freight) |
| shipments | Freight bookings |
| carriers | Transport companies |
| licenses | Regulatory licenses |
| deadlines | Compliance deadlines |
| compliance_documents | Uploaded PDFs |
| email_tokens | Verify + reset |
| kyc_submissions | Document upload |
| audit_logs | Admin actions |
| alerts | Banner alerts + dismissal |

Migrations in migrations/versions/.
Current head: abc123_shipment_table.

---

## 6. Routes reference

Public: / , /health

Auth: /auth/login /auth/register /auth/logout
/auth/change-password /auth/profile /auth/verify/<t>
/auth/resend-verification /auth/forgot-password /auth/reset/<t>
/auth/2fa/setup /auth/2fa/verify /auth/2fa/manage /auth/2fa/disable

Exchange: /exchange/ /exchange/convert /exchange/book
/exchange/source /exchange/rates

Logistics: /logistics/ /logistics/quote /logistics/book
/logistics/bookings /logistics/bookings/<id>
/logistics/bookings/<id>/cancel

KYC: /kyc/

Compliance (admin): /compliance/ /compliance/license/add
/compliance/deadline/add /compliance/document/upload
/compliance/export.csv

Admin:
/admin/
/admin/api/stats /admin/api/balance /admin/api/ticker
/admin/api/pnl /admin/api/positions /admin/api/recent-transactions
/admin/api/assistant/scan /admin/api/assistant/run
/admin/blotter /admin/positions /admin/users
/admin/users/<id>/toggle_admin /admin/users/<id>/toggle_active
/admin/users/<id>/reset_password /admin/users/<id>/verify_email
/admin/users/<id>/send_verification /admin/users/<id>/unverify_email
/admin/users/send_verification_all
/admin/companies /admin/companies/<id>
/admin/companies/<id>/verify /admin/companies/<id>/reject
/admin/companies/<id>/suspend
/admin/kyc /admin/kyc/<id> /admin/kyc/<id>/approve /admin/kyc/<id>/reject
/admin/shipments /admin/shipments/<id>
/admin/shipments/<id>/advance /admin/shipments/<id>/assign_carrier
/admin/shipments/<id>/waybill
/admin/alerts /admin/alerts/create /admin/alerts/<id>/delete
/admin/audit /admin/assistant

Public JSON: /api/prices /api/news /api/alerts/active
POST /api/alerts/<id>/dismiss


---

## 7. Credentials

Admin: admin / Aflathoon123

SECRET_KEY regenerate command:
    python -c "import secrets; print(secrets.token_hex(32))"

---

## 8. Known issues

| Symptom | Fix |
|---|---|
| Working outside of application context | Wrap loop in app.app_context() |
| unable to open database file | Check _resolve_db_uri() |
| no such column: X | flask db migrate + flask db upgrade |
| port 9105 busy | pkill -f "python app.py" |
| rates_fallback persists | Set RATES_MODE=live + key |
| Duplicate engine-start lines | FLASK_SKIP_ENGINES=1 |

---

## 9. What works today

- Flask boots on pinned port with fallback scan
- SQLite at absolute path; Flask-Migrate under version control
- Multi-theme (dark / light / auto)
- Registration + email verification + login
- Password reset via email
- 2FA (TOTP + 10 backup codes)
- Enhanced profiles + company accounts + admin verification
- KYC submission + admin review + tier upgrade
- FX quotes + book to ledger
- Freight quotes with war-risk + currency conversion
- Freight booking with waybill, carrier, full lifecycle
- Blotter, positions, P&L chart
- Audit log
- AI Assistant (15 checks) with one-click fixes
- Auto-alert engine + price-spike alerts
- Live crypto prices + market + trending
- RSS news with thumbnails
- Compliance + CSV export
- Rate limiting + CSRF
- License guard + crypto custody stub
- DB backups + git auto-sync
- KDE launchers

---

## 10. What's NOT built yet

- Crypto to fiat booking with settlement
- P2P module
- Forward/swap contracts
- LEI capture UI
- Real KYC / sanctions providers
- Real crypto custody
- Postgres migration
- Cloudflare Tunnel exposure
- Real rate API key
- pytest test suite
- Redis cache / limiter / sessions
- SMTP configured for real email
- Custom domain with SPF/DKIM/DMARC


---

## 11. Commands

    cd ~/aflathoon_exchange
    source venv/bin/activate

    python app.py           # start
    ./restart.sh            # restart
    pkill -f "python app.py"

    FLASK_SKIP_ENGINES=1 flask db current
    FLASK_SKIP_ENGINES=1 flask db migrate -m "msg"
    FLASK_SKIP_ENGINES=1 flask db upgrade

    ./verify_install.sh
    ./scripts/backup_db.sh
    ./scripts/git-sync.sh
    ss -ltn | grep 9105
    sqlite3 data/exchange.db ".tables"
    curl -s http://127.0.0.1:9105/api/prices | python3 -m json.tool
    curl -s http://127.0.0.1:9105/api/news | python3 -m json.tool | head -60

---

## 12. Cron jobs

    15 3 * * * /home/aflathoon/aflathoon_exchange/scripts/git-sync.sh
    30 3 * * * /home/aflathoon/aflathoon_exchange/scripts/backup_full.sh

---

## 13. Tech stack

| Layer | Choice |
|---|---|
| Web | Flask 3.x |
| ORM | SQLAlchemy 2.x |
| Migrations | Flask-Migrate |
| Auth | Flask-Login + TOTP 2FA |
| Passwords | Werkzeug scrypt |
| Caching | Flask-Caching SimpleCache |
| Rate limit | Custom in-process |
| DB dev | SQLite |
| DB prod | PostgreSQL |
| Frontend | Vanilla JS + CSS vars |
| Email | Console + SMTP |
| News | RSS (feedparser + bs4) |
| Market | CoinGecko |
| Server prod | Gunicorn + Nginx |

---

## 14. Security posture

Working:
- HttpOnly cookies, SameSite=Lax, unique name
- scrypt passwords
- TOTP 2FA + backup codes
- CSRF on POST + AJAX
- Per-user / per-IP / per-email rate limits
- Audit log of every admin action
- License guard
- Crypto custody stub refuses keys

Missing:
- HTTPS / HSTS / CSP
- Secure cookie flag
- Password strength meter
- Failed-login lockout
- Dependency scanning
- Custom domain (SPF/DKIM/DMARC)
- Real KYC / sanctions
- Real crypto custody

---

## 15. Resume instructions

1. Read this file
2. cd ~/aflathoon_exchange && source venv/bin/activate
3. ./verify_install.sh
4. ./run.sh
5. Log in at http://127.0.0.1:9105/auth/login
6. git log --oneline -10
7. Read ROADMAP.md

Long-paste warning: use cat > file << 'EOF' heredocs,
split if more than 100 lines.

---

## 16. Contact

- GitHub: https://github.com/Aflathoon
- Repo: https://github.com/Aflathoon/aflathoon-exchange.git

End of project state.
