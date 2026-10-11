
# Roadmap — Aflathoon Exchange Platform

Prioritised. Each section is a self-contained build.
Companion to PROJECT_STATE.md and ARCHITECTURE.md.

**Last updated:** 2026-10-11

Legend: EASY (< 1 session) / MEDIUM (1-2 sessions) /
HARD (multi-session)

---

## Phase 0 — Foundation (DONE)

- Flask + venv + Python 3.14 + SQLite at absolute path
- Multi-theme (dark / light / auto) via CSS variables
- Sidebar layout via base.html
- Rate engine with layered fallback + 27 currencies
- Margin model (single 6.5% spread)
- FX quote + book to ledger
- Admin dashboard (Approx-style)
- Blotter with pagination
- Positions UI
- User admin (promote / deactivate / reset password)
- Compliance: licenses, deadlines, documents, CSV export
- Logistics quote with war-risk premium
- License guard (blocks live trading)
- Crypto custody stub
- DB backups + git auto-sync
- Git repo + auto-sync (cron)
- KDE launchers

---

## Phase 1 — Foundation hygiene (DONE)

- [x] Flask-Migrate setup
- [x] Hardened .gitignore
- [x] First GitHub push
- [x] verify_install.sh
- [x] Engine skip flag for CLI

---

## Phase 2 — Users, companies, compliance (DONE)

- [x] Enhanced user profile (full_name, phone, DOB,
      country, address)
- [x] Company accounts with registration details
- [x] Company admin verification workflow
- [x] Email verification (console + SMTP pluggable)
- [x] Password reset via email link
- [x] Two-factor auth (TOTP + 10 backup codes)
- [x] Password reveal toggle on all password fields
- [x] KYC submission with document upload
- [x] KYC admin review + auto tier upgrade
- [x] Audit log of every admin action
- [x] Per-user rate limiting (login, register,
      forgot-password, book endpoints)
- [x] CSRF protection (forms + AJAX fetch)

---

## Phase 3 — Live data + monitoring (DONE)

- [x] CoinGecko live prices (BTC, ETH, SOL, XRP, ADA, DOGE)
- [x] Global market data (cap, volume, dominance, 24h change)
- [x] Trending coins
- [x] RSS news from 5 crypto outlets
      (CoinDesk, Cointelegraph, The Block,
      Decrypt, Bitcoin Magazine)
- [x] Article thumbnails via 5-strategy extraction
- [x] Live sidebar (news + prices + market + trending)
- [x] AI Assistant (15 checks) with one-click fixes
- [x] Auto-alert engine (findings to banner alerts)
- [x] Price-spike alerts (>5% 24h moves)
- [x] Per-user alert dismissal
- [x] Admin alert management (/admin/alerts)

---

## Phase 4 — Freight booking (DONE)

- [x] Shipment model with full lifecycle
- [x] book_shipment() service
- [x] User booking flow (/logistics/book)
- [x] User bookings list + detail page
- [x] Cancel shipment action
- [x] Admin fulfillment queue (/admin/shipments)
- [x] Status advance buttons + validation
- [x] Carrier assignment
- [x] Waybill / tracking URL management
- [x] Auto-create ledger Transaction on booking
- [x] Currency conversion in quotes
      (27 currencies incl. AED, SAR, JPY, CNY, INR)
- [x] 3 new AI Assistant checks
      (delayed, stuck, unassigned shipments)


---

## Phase 5 — Extended exchange (TODO)

### 5a. Crypto-to-fiat booking (HARD, deferred)

Regulatory prerequisite: UK crypto asset regime launches
25 October 2027, application window 30 Sep 2026 - 28 Feb 2027.
FCA fees ~£11,260 per permission category.

**Do not build until legal counsel confirms.**

- Extend book_trade() to handle crypto legs
- Deposit address display (needs custody provider)
- awaiting_deposit -> awaiting_release -> settled flow
- On-chain TX hash recording
- Real custody provider (Fireblocks / BitGo / Copper)
- Multi-sig approval for large withdrawals
- Hot wallet for small amounts (env cap already set)

### 5b. Settlement workflow (HARD)

- New model: Settlement (bank ref / TX hash / proof)
- Fiat: bank transfer instructions + proof upload
- Crypto: TX hash recording + blockchain explorer link
- Admin: mark settled from blotter
- Auto-reconcile from bank statement CSV

### 5c. Forward contracts (HARD)

- Transaction.type = FORWARD
- settlement_date field
- Rate locked at booking
- Mark-to-market calculation
- LEI capture (field exists in User, no UI yet)
- Regulatory reporting hooks

### 5d. Swap contracts (HARD)

- Two-leg transaction (spot + forward)
- Net settlement

---

## Phase 6 — P2P module (TODO)

### 6a. P2P core (HARD)

- Model P2POffer (maker, asset, fiat, price,
  min/max, payment methods, terms)
- Model P2PTrade (offer, taker, status, timestamps)
- Model P2PDispute
- Escrow: lock seller's crypto
- Release only on mutual confirmation or dispute resolution

### 6b. Reputation system (MEDIUM)

- Trade completion -> reputation score
- Public trader profile with history
- Minimum reputation to post large offers

### 6c. Payment method integration (HARD)

- Bank transfer (SEPA, Faster Payments, SWIFT)
- Wise / Revolut / Payoneer reference
- Crypto on-chain (BTC, ETH, USDT, USDC)
- Local payment rails per jurisdiction

### 6d. Dispute resolution (MEDIUM)

- Evidence upload
- Admin arbitration panel
- Timeout rules (auto-release after X days)

---

## Phase 7 — Compliance deepening (TODO)

### 7a. Real KYC provider (MEDIUM)

Sign up: Onfido / Sumsub / Jumio

- Replace services/compliance.py stubs
- Document upload -> provider API
- Webhook for status updates
- Tiered limits by KYC level
- Current /kyc/ submission flow stays; provider
  becomes the reviewer

### 7b. Sanctions screening (EASY)

Free option: OpenSanctions (no key required)

- Download their consolidated sanctions + PEP lists
- Local SQLite cache
- Screen on registration + on every high-value trade
- Alert queue for manual review
- Refresh daily via cron

### 7c. PEP checks (MEDIUM)

- Same provider as sanctions
- Enhanced due diligence flag

### 7d. Transaction monitoring (MEDIUM)

- Rules: velocity, structuring, unusual corridor
- Alert queue for admin
- SAR/STR filing support

### 7e. Audit log extensions (EASY)

- Add user-facing "your account activity" page
- Retention policy (keep 7 years)
- Immutable append-only (currently deletable)


---

## Phase 8 — Operations (TODO)

### 8a. Email infrastructure (EASY)

- Currently EMAIL_BACKEND=console
- Pick provider: Resend (best DX), Brevo, Postmark
- Set SMTP_HOST/USER/PASS in .env
- Set EMAIL_BACKEND=smtp
- Add trade confirmation + KYC status templates
- Bounce handling

### 8b. Telegram bot (EASY)

- BotFather token
- Notify: new trade, license expiry, KYC submission,
  delayed shipment
- Admin commands: /stats, /positions, /users

### 8c. Monitoring (MEDIUM)

- Sentry for exceptions
- Prometheus + Grafana for metrics
- UptimeRobot free tier for external check

### 8d. Analytics (MEDIUM)

- Trading volume over time
- Margin capture rate
- Customer acquisition
- Retention cohorts

---

## Phase 9 — Production deployment (TODO)

### 9a. Infrastructure (MEDIUM)

- PostgreSQL migration
- Redis for cache + rate limit + sessions
- Gunicorn systemd unit
- Nginx + Let's Encrypt
- Cloudflare Tunnel

### 9b. Security hardening (MEDIUM)

- SESSION_COOKIE_SECURE=True
- HTTPS-only + HSTS
- CSP headers
- Failed-login lockout
- Per-user rate limits at Nginx
- Disable debug mode
- Rotate all secrets
- Dependency scanning (pip-audit)

### 9c. Legal (paperwork)

- Engage lawyer -- licensing per jurisdiction
- MSB / money transmitter / crypto asset registration
- Terms of Service
- Privacy Policy (GDPR / UK DPA)
- AML/CTF policy document
- Insurance (professional indemnity, cyber)
- Register with regulator before going live

### 9d. Launch

- Beta with 5-10 trusted users
- Bug bash
- Public launch

---

## Quick wins backlog

- /admin/api/export-all.csv (full DB dump)
- CSV import for bulk rate overrides
- Duplicate transaction button in blotter
- Rate history chart per pair
- Notification bell in topbar
- Keyboard shortcuts (g h for home, g e for exchange)
- Recently viewed cache
- PWA manifest
- Print-friendly compliance stylesheet
- QR code generation for crypto addresses
- Copy-to-clipboard buttons on reference IDs
- Dark / light / auto cycle via keyboard shortcut

---

## Current recommendation

**Path 1 — Continue building features (safe):**

1. Phase 7b -- sanctions screening (free via OpenSanctions)
2. Phase 8a -- SMTP configured for real email
3. Phase 5b -- settlement workflow (fiat-only first)
4. Phase 9a -- PostgreSQL migration

**Path 2 — Prepare for launch:**

1. Phase 9b -- security hardening
2. Phase 9c -- legal review
3. Phase 8c -- monitoring (Sentry + UptimeRobot)
4. Phase 9a -- Cloudflare Tunnel
5. Beta with 5-10 users

**Do NOT build Phase 5a (crypto booking)** until legal
counsel has confirmed the licensing route. UK regime is
still being finalised with fees around £11,260 per
permission category and mandatory FCA authorisation.

**Never enable LIVE_TRADING_ENABLED=true** until:

- Real licenses are registered
- KYC is wired to a real provider
- Sanctions screening is live
- Written legal advice confirms the platform can operate

End of roadmap.
