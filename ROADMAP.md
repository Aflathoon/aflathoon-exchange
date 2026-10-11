# Roadmap — Aflathoon Exchange Platform

Prioritised. Each section is a self-contained build.
Companion to PROJECT_STATE.md and ARCHITECTURE.md.

Legend: EASY (< 1 session) / MEDIUM (1-2 sessions) / HARD (multi-session)

---

## Phase 0 — Foundation (DONE)

- Flask + venv + Python 3.14
- SQLite at absolute path
- Theme system (dark/light/auto)
- Sidebar layout via base.html
- Rate engine with fallback chain
- Margin model (single 6.5% spread)
- Exchange quote
- Book trade -> Transaction
- Admin dashboard
- Blotter with pagination
- Positions UI
- User admin (promote/deactivate/reset)
- Compliance (licenses, deadlines, documents, CSV)
- Logistics quote with war-risk premium
- License guard (blocks live trading)
- Crypto custody stub
- Backups + cron
- Git repo + auto-sync

---

## Phase 1 — Foundation hygiene (DO FIRST)

### 1.1 Flask-Migrate setup (EASY)
- pip install Flask-Migrate
- flask db init
- flask db migrate -m "baseline"
- flask db stamp head

Result: future model changes = flask db migrate + flask db upgrade.

### 1.2 Hardened .gitignore verified (done)

### 1.3 First GitHub push (done)

### 1.4 verify_install.sh extended (EASY)
- Add checks: git repo, cron jobs, backup files exist

---

## Phase 2 — User and company registration

### 2.1 Enhanced user profile (MEDIUM)
- User: full_name, phone, date_of_birth, address, country
- User: email_verified, email_verified_at
- User: two_factor_enabled, two_factor_secret
- Migration via Flask-Migrate

### 2.2 Company accounts (MEDIUM)
- Model Company (name, registration_number, jurisdiction, tax_id, LEI)
- User.company_id FK
- Company registration form
- Admin: verify company docs

### 2.3 Email verification (MEDIUM)
- SMTP in .env (or Postmark / SendGrid)
- EmailToken model (token, user_id, purpose, expiry)
- Send verification email on register
- /auth/verify/<token> route
- Block admin actions until verified

### 2.4 Password reset (EASY)
- Reuse EmailToken with purpose='password_reset'
- /auth/forgot-password + /auth/reset/<token>
- Rate-limit heavily (5/hour per IP)

### 2.5 Two-factor auth (MEDIUM)
- TOTP via pyotp
- QR code generation (qrcode lib)
- Backup codes
- Require for admin users

---

## Phase 3 — Social login

### 3.1 Authlib setup (EASY)
- pip install Authlib
- Register OAuth client in app/__init__.py
- New blueprint oauth_bp

### 3.2 Google login (EASY)
- Google Cloud project + OAuth credentials
- /auth/login/google + callback
- Merge with existing email if match

### 3.3 Telegram login (EASY)
- BotFather -> get bot token + username
- Telegram Login Widget on login page
- /auth/login/telegram/callback (verify HMAC)

### 3.4 Optional: GitHub, Facebook (EASY)
- Same pattern via Authlib

---

## Phase 4 — Real data sources

### 4.1 Live rates (MEDIUM)
- Sign up for TickerLayer or SiftingIO
- Adjust rate_engine._parse_response() to real payload shape
- Set RATES_MODE=live, TICKERLAYER_API_KEY=...
- Verify source badge shows LIVE
- Add graceful degradation test

### 4.2 News ticker (HARD)
- Source: CoinGecko (crypto, free) + NewsAPI
- Cache in DB or Redis (5-10 min TTL)
- Widget in base.html header, scrolls horizontally
- Categories: crypto, fiat, gold, silver, iron, oil, gas
- Symbol -> price chip

### 4.3 Commodity price feeds (MEDIUM)
- Add gold (XAU), silver (XAG), iron ore, copper, wheat, oil (WTI + Brent), natural gas
- Source: TickerLayer or dedicated commodity feed
- Extend API_SYMBOLS in rate engine
- Show in ticker

---

## Phase 5 — Full exchange experience

### 5.1 Crypto <-> fiat booking (HARD)
- Extend book_trade() to handle crypto legs
- On-chain vs off-chain distinction
- Hot wallet for small amounts
- Multi-sig approval for large withdrawals
- Real custody provider integration

### 5.2 Settlement workflow (HARD)
- New model Settlement (transaction_id, status, method, reference, timestamps)
- Fiat: bank transfer instructions, proof of payment upload
- Crypto: TX hash recording
- Admin: mark settled, view on blockchain explorer
- Auto-reconcile from bank statement CSV

### 5.3 Forward contracts (HARD)
- Transaction.type = FORWARD
- settlement_date field
- Rate locked at booking
- Mark-to-market calculation
- LEI capture (already in User model)
- Regulatory reporting hooks

### 5.4 Swap contracts (HARD)
- Two-leg transaction (spot + forward)
- Net settlement

---

## Phase 6 — P2P module

### 6.1 P2P core (HARD)
- Model P2POffer (maker, asset, fiat, price, min/max, payment methods, terms)
- Model P2PTrade (offer, taker, status, timestamps)
- Model P2PDispute
- Escrow: lock seller's crypto in custodial wallet
- Release only on mutual confirmation or dispute resolution

### 6.2 Reputation system (MEDIUM)
- Trade completion -> reputation score
- Public trader profile with history
- Minimum reputation to post large offers

### 6.3 Payment method integration (HARD)
- Bank transfer (SEPA, Faster Payments, SWIFT)
- Wise / Revolut / Payoneer reference
- Crypto on-chain (BTC, ETH, USDT, USDC)
- Local payment rails per jurisdiction

### 6.4 Dispute resolution (MEDIUM)
- Evidence upload
- Admin arbitration panel
- Timeout rules (auto-release after X days)

---

## Phase 7 — Compliance deepening

### 7.1 Real KYC provider (MEDIUM)
- Sign up: Onfido / Sumsub / Jumio
- Replace stubs in services/compliance.py
- Document upload -> provider API
- Webhook for status updates
- Tiered limits by KYC level

### 7.2 Sanctions screening (MEDIUM)
- Provider: Refinitiv World-Check / ComplyAdvantage / OpenSanctions
- Screen on registration + on every high-value trade
- Alerting + manual review queue

### 7.3 PEP checks (MEDIUM)
- Same provider as sanctions
- Enhanced due diligence flag

### 7.4 Transaction monitoring (MEDIUM)
- Rules: velocity, structuring, unusual corridor
- Alert queue for admin
- SAR/STR filing support

### 7.5 Audit log (EASY)
- Model AuditLog (actor, action, entity, before, after, IP, UA, timestamp)
- Log every admin action
- Immutable append-only

---

## Phase 8 — Operations

### 8.1 Email infrastructure (MEDIUM)
- Transactional provider (Postmark / SendGrid / Mailgun)
- Templates: welcome, verification, reset, trade confirmation, alert
- Bounce handling

### 8.2 Telegram bot (EASY)
- BotFather -> token
- Send notifications: new trade, license expiry warning, KYC submission
- Admin commands: /stats, /positions, /users

### 8.3 Monitoring (MEDIUM)
- Sentry for exceptions
- Prometheus + Grafana for metrics
- Uptime check (UptimeRobot, free tier)

### 8.4 Analytics (MEDIUM)
- Trading volume over time
- Margin capture rate
- Customer acquisition
- Retention cohorts

---

## Phase 9 — Production deployment

### 9.1 Infrastructure (MEDIUM)
- PostgreSQL migration
- Redis for cache + limiter + sessions
- Gunicorn systemd unit
- Nginx config + Let's Encrypt
- Cloudflare Tunnel

### 9.2 Security hardening (MEDIUM)
- CSRF tokens (Flask-WTF)
- SESSION_COOKIE_SECURE=True
- HTTPS-only
- CSP headers
- HSTS
- Failed-login throttling
- Per-user rate limits
- Disable debug mode
- Rotate all secrets

### 9.3 Legal (paperwork)
- Engage lawyer — licensing requirements per jurisdiction
- Money transmitter / MSB / crypto asset registration
- Terms of Service
- Privacy Policy (GDPR / UK DPA)
- AML/CTF policy document
- Insurance (professional indemnity, cyber)
- Register with regulator before going live

### 9.4 Launch
- Beta with 5-10 trusted users
- Bug bash
- Public launch

---

## Quick wins backlog

- /admin/api/export-all.csv (full DB dump)
- CSV import for bulk rate overrides
- "duplicate transaction" button in blotter
- Rate history chart per pair
- Notification bell in topbar
- Keyboard shortcuts (g+h, g+e)
- Recently viewed cache
- PWA manifest
- Print-friendly stylesheet for compliance docs
- QR code generation for crypto addresses
- Copy-to-clipboard buttons on reference IDs

---

## Current recommendation

1. Phase 1 (Flask-Migrate) first
2. Phase 2 (user/company + email + 2FA)
3. Phase 4 (live rates + news ticker)

P2P (Phase 6) is largest — schedule after real users + KYC infrastructure.

Before ANY public exposure:
1. Phase 9.2 (security)
2. Phase 9.3 (legal)
3. Phase 7.1-7.2 (KYC + sanctions)

Never enable live trading (LIVE_TRADING_ENABLED=true) until:
- Real licenses registered
- KYC wired to real provider
- Sanctions screening live
- Written legal advice confirming you can operate

End of roadmap.
