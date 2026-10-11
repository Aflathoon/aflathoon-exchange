#!/usr/bin/env bash
# =============================================================================
# Phase 2.1 + 2.2 — Enhanced User Profile + Company Accounts
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "== Phase 2.1 + 2.2 build =="

# --- 1. Company model ---
cat > app/models/company.py << 'PYEOF'
from datetime import datetime
from app import db


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    registration_number = db.Column(db.String(80))
    jurisdiction = db.Column(db.String(80))
    tax_id = db.Column(db.String(80))
    lei_code = db.Column(db.String(20))                    # Legal Entity Identifier
    website = db.Column(db.String(200))
    industry = db.Column(db.String(120))

    # Verification lifecycle
    status = db.Column(db.String(30), default='pending')   # pending / verified / rejected / suspended
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rejection_reason = db.Column(db.Text)

    # Contact
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(80))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='company', lazy='dynamic',
                            foreign_keys='User.company_id')
    verified_by = db.relationship('User', foreign_keys=[verified_by_id], post_update=True)

    @property
    def is_verified(self):
        return self.status == 'verified'

    @property
    def user_count(self):
        return self.users.count()

    def __repr__(self):
        return f'<Company {self.name}>'
PYEOF

# --- 2. Extend User model ---
cat > app/models/user.py << 'PYEOF'
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Identity
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date)
    country = db.Column(db.String(80))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))

    # Account flags
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    account_type = db.Column(db.String(20), default='individual')   # individual / company
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))

    # KYC / compliance
    kyc_status = db.Column(db.String(20), default='pending')
    kyc_tier = db.Column(db.Integer, default=0)
    lei_code = db.Column(db.String(20))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Transactions
    transactions = db.relationship('Transaction', backref='user', lazy='dynamic')

    def set_password(self, p):
        self.password_hash = generate_password_hash(p)

    def check_password(self, p):
        return check_password_hash(self.password_hash, p)

    def __repr__(self):
        return f'<User {self.username}>'
PYEOF

# --- 3. Register Company in models/__init__.py ---
cat > app/models/__init__.py << 'PYEOF'
from app.models.user import User
from app.models.company import Company
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.rate import ExchangeRate
from app.models.shipping import ShippingQuote, Carrier
from app.models.license import License, Deadline, ComplianceDocument

__all__ = [
    'User', 'Company',
    'Transaction', 'TransactionStatus', 'TransactionType',
    'ExchangeRate', 'ShippingQuote', 'Carrier',
    'License', 'Deadline', 'ComplianceDocument',
]
PYEOF

# --- 4. Replace auth routes (register/profile) ---
cat > app/routes/auth.py << 'PYEOF'
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify)
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, date
from app import db
from app.models.user import User
from app.models.company import Company

auth_bp = Blueprint('auth', __name__)


def _parse_date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next') or '/'

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        print(f"[LOGIN] POST user={username!r} pw_len={len(password)} next={next_url!r}", flush=True)

        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            if not u.is_active:
                flash('Account deactivated. Contact support.')
                return render_template('auth/login.html', next=next_url)
            u.last_login = datetime.utcnow()
            db.session.commit()
            login_user(u, remember=True)
            print(f"[LOGIN] OK -> redirect {next_url!r}", flush=True)
            return redirect(next_url)

        print("[LOGIN] FAILED", flush=True)
        flash('Invalid credentials')

    return render_template('auth/login.html', next=next_url)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        account_type = request.form.get('account_type', 'individual')

        # Validation
        if len(password) < 10:
            flash('Password must be at least 10 characters')
            return render_template('auth/register.html'), 400
        if User.query.filter_by(username=username).first():
            flash('Username taken')
            return render_template('auth/register.html'), 400
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return render_template('auth/register.html'), 400

        # Create user
        u = User(
            username=username,
            email=email,
            full_name=request.form.get('full_name', '').strip() or None,
            phone=request.form.get('phone', '').strip() or None,
            country=request.form.get('country', '').strip() or None,
            account_type=account_type,
        )
        u.set_password(password)

        # Create company if requested
        if account_type == 'company':
            company_name = (request.form.get('company_name') or '').strip()
            if not company_name:
                flash('Company name is required for company accounts')
                return render_template('auth/register.html'), 400
            c = Company(
                name=company_name,
                registration_number=request.form.get('company_registration', '').strip() or None,
                jurisdiction=request.form.get('company_jurisdiction', '').strip() or None,
                tax_id=request.form.get('company_tax_id', '').strip() or None,
                lei_code=request.form.get('company_lei', '').strip() or None,
                industry=request.form.get('company_industry', '').strip() or None,
                contact_email=email,
                status='pending',
            )
            db.session.add(c)
            db.session.flush()          # get c.id
            u.company_id = c.id

        db.session.add(u)
        db.session.commit()

        flash('Registered. Please log in.')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password') or ''
        new_pw = request.form.get('new_password') or ''
        confirm = request.form.get('confirm_password') or ''

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect')
        elif len(new_pw) < 10:
            flash('New password must be at least 10 characters')
        elif new_pw != confirm:
            flash('New passwords do not match')
        elif new_pw == current_pw:
            flash('New password must be different from current')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash('Password changed successfully')
            return redirect(url_for('main.index'))

    return render_template('auth/change_password.html')


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        u = current_user
        u.full_name     = request.form.get('full_name', '').strip() or None
        u.phone         = request.form.get('phone', '').strip() or None
        u.country       = request.form.get('country', '').strip() or None
        u.address_line1 = request.form.get('address_line1', '').strip() or None
        u.address_line2 = request.form.get('address_line2', '').strip() or None
        u.city          = request.form.get('city', '').strip() or None
        u.postal_code   = request.form.get('postal_code', '').strip() or None
        dob = _parse_date(request.form.get('date_of_birth'))
        if dob:
            u.date_of_birth = dob

        # Company fields (if user has a company)
        if u.company_id:
            c = Company.query.get(u.company_id)
            if c:
                c.name                = request.form.get('company_name', c.name).strip() or c.name
                c.registration_number = request.form.get('company_registration', '').strip() or None
                c.jurisdiction        = request.form.get('company_jurisdiction', '').strip() or None
                c.tax_id              = request.form.get('company_tax_id', '').strip() or None
                c.lei_code            = request.form.get('company_lei', '').strip() or None
                c.industry            = request.form.get('company_industry', '').strip() or None
                c.contact_phone       = request.form.get('phone', '').strip() or None

        db.session.commit()
        flash('Profile updated')
        return redirect(url_for('auth.profile'))

    company = Company.query.get(current_user.company_id) if current_user.company_id else None
    return render_template('auth/profile.html', user=current_user, company=company)
PYEOF

echo "  - models and routes written"

# --- 5. Templates: register (updated), profile (new) ---
mkdir -p app/templates/auth

cat > app/templates/auth/register.html << 'HTMLEOF'
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Register — Aflathoon</title>
<link rel="stylesheet" href="/static/css/admin.css">
<script id="afl-theme-init">
  (function(){
    document.documentElement.classList.add("no-transition");
    var m = document.cookie.match(/(?:^|; )afl_theme=([^;]+)/);
    var t = m ? decodeURIComponent(m[1]) : "dark";
    document.documentElement.setAttribute("data-theme", t);
  })();
</script>
<style>
body.afl-auth{display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;
  background:radial-gradient(1200px 800px at 100% -10%,rgba(138,111,255,.10),transparent 60%),
             radial-gradient(900px 600px at -10% 110%,rgba(111,140,255,.10),transparent 60%),var(--bg);
  color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
.auth-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:2rem;width:520px;max-width:95vw;box-shadow:var(--shadow)}
.auth-card h2{margin:0 0 1rem;color:var(--accent);font-size:1.4rem}
.auth-card input,.auth-card select{width:100%;padding:.7rem .9rem;margin:.35rem 0;background:var(--input-bg);border:1px solid var(--border);color:var(--text);border-radius:10px;box-sizing:border-box;font-size:.95rem;font-family:inherit}
.auth-card input:focus,.auth-card select:focus{outline:none;border-color:var(--accent)}
.auth-card button{width:100%;padding:.8rem;background:var(--accent);color:#fff;border:0;border-radius:10px;cursor:pointer;font-weight:600;font-size:1rem;margin-top:.8rem}
.auth-card .row{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}
.auth-card .msg{padding:.6rem .9rem;border-radius:8px;margin-bottom:.8rem;font-size:.88rem;background:rgba(239,68,68,.12);color:var(--red-fg);border:1px solid rgba(239,68,68,.25)}
.auth-card a{color:var(--accent);text-decoration:none}
.auth-card .foot{font-size:.85rem;color:var(--muted);margin-top:1rem;text-align:center}
.auth-brand{display:flex;align-items:center;gap:.7rem;justify-content:center;margin-bottom:1.2rem}
.auth-brand-mark{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent-2));display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;font-size:1.2rem}
.auth-brand-name{font-weight:700;font-size:1.1rem;color:var(--text)}
.auth-brand-name small{display:block;font-weight:400;color:var(--muted);font-size:.72rem}
.auth-theme{position:fixed;top:1rem;right:1rem;background:var(--surface);border:1px solid var(--border);color:var(--text);width:40px;height:40px;border-radius:10px;cursor:pointer;font-size:1.1rem}
.tabs{display:flex;gap:.5rem;margin:.5rem 0 1rem}
.tabs button{background:var(--surface-2);color:var(--text-2);border:1px solid var(--border);padding:.6rem 1rem;border-radius:10px;cursor:pointer;font-weight:500;font-size:.9rem;width:auto;margin:0}
.tabs button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.company-fields{display:none}
.company-fields.visible{display:block}
.hint{font-size:.78rem;color:var(--muted);margin:-.2rem 0 .4rem}
</style>
</head>
<body class="afl-auth">

<button id="themeToggle" class="auth-theme" title="Theme">☾</button>

<form class="auth-card" method="post" autocomplete="off">
  <div class="auth-brand">
    <div class="auth-brand-mark">A</div>
    <div class="auth-brand-name">Aflathoon<small>Exchange Platform</small></div>
  </div>
  <h2>Create account</h2>

  {% with messages = get_flashed_messages() %}
    {% if messages %}{% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}{% endif %}
  {% endwith %}

  <div class="tabs">
    <button type="button" id="tab-individual" class="active" onclick="pickType('individual')">Individual</button>
    <button type="button" id="tab-company" onclick="pickType('company')">Company</button>
  </div>
  <input type="hidden" name="account_type" id="account_type" value="individual">

  <input name="full_name" placeholder="Full name" autofocus>
  <div class="row">
    <input name="username" placeholder="Username" required autocomplete="username">
    <input name="email" type="email" placeholder="Email" required>
  </div>
  <div class="row">
    <input name="phone" placeholder="Phone (optional)">
    <input name="country" placeholder="Country">
  </div>
  <input name="password" type="password" placeholder="Password (min 10 characters)" required minlength="10" autocomplete="new-password">

  <div id="company-fields" class="company-fields">
    <hr style="border:0;border-top:1px solid var(--border);margin:1rem 0">
    <div class="hint">Company details (verified by admin after signup)</div>
    <input name="company_name" placeholder="Company legal name">
    <div class="row">
      <input name="company_registration" placeholder="Registration number">
      <input name="company_jurisdiction" placeholder="Jurisdiction (e.g. UK)">
    </div>
    <div class="row">
      <input name="company_tax_id" placeholder="Tax ID / VAT">
      <input name="company_lei" placeholder="LEI (optional)">
    </div>
    <input name="company_industry" placeholder="Industry (e.g. commodities, shipping)">
  </div>

  <button>Register</button>
  <div class="foot">Already have an account? <a href="/auth/login">Sign in</a></div>
</form>

<script>
function pickType(t){
  document.getElementById('account_type').value = t;
  document.getElementById('tab-individual').classList.toggle('active', t === 'individual');
  document.getElementById('tab-company').classList.toggle('active', t === 'company');
  document.getElementById('company-fields').classList.toggle('visible', t === 'company');
}

// theme cycle
(function(){
  function currentTheme(){var m=document.cookie.match(/(?:^|; )afl_theme=([^;]+)/);return m?decodeURIComponent(m[1]):'dark';}
  function apply(t){document.documentElement.setAttribute('data-theme',t);
    var icons={dark:'☾',light:'☀',auto:'◐'};var el=document.getElementById('themeToggle');if(el)el.textContent=icons[t]||'☾';}
  function cycle(){var order=['dark','light','auto'];var cur=currentTheme();
    var next=order[(order.indexOf(cur)+1)%order.length];
    document.cookie='afl_theme='+encodeURIComponent(next)+'; path=/; max-age='+(60*60*24*365)+'; SameSite=Lax';
    apply(next);}
  apply(currentTheme());
  var btn=document.getElementById('themeToggle');if(btn)btn.addEventListener('click',cycle);
  requestAnimationFrame(function(){document.documentElement.classList.remove('no-transition');});
})();
</script>
</body>
</html>
HTMLEOF

cat > app/templates/auth/profile.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}My Profile — Aflathoon{% endblock %}
{% block search_placeholder %}Profile settings{% endblock %}

{% block content %}
<h1 class="afl-page-title">My Profile</h1>

{% with messages = get_flashed_messages() %}
  {% if messages %}{% for m in messages %}<div class="afl-card" style="border-left:3px solid var(--green);padding:.7rem 1rem;margin-bottom:1rem">{{ m }}</div>{% endfor %}{% endif %}
{% endwith %}

<form method="post">
  <div class="afl-row afl-row-split" style="max-width:1000px">

    <div>
      <div class="afl-card">
        <h3 class="afl-h3">Personal details</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-top:.6rem">
          <input name="full_name" placeholder="Full name" value="{{ user.full_name or '' }}" class="afl-in">
          <input name="phone" placeholder="Phone" value="{{ user.phone or '' }}" class="afl-in">
          <input name="date_of_birth" type="date" value="{{ user.date_of_birth.isoformat() if user.date_of_birth else '' }}" class="afl-in">
          <input name="country" placeholder="Country" value="{{ user.country or '' }}" class="afl-in">
          <input name="address_line1" placeholder="Address line 1" value="{{ user.address_line1 or '' }}" class="afl-in" style="grid-column:1/-1">
          <input name="address_line2" placeholder="Address line 2" value="{{ user.address_line2 or '' }}" class="afl-in" style="grid-column:1/-1">
          <input name="city" placeholder="City" value="{{ user.city or '' }}" class="afl-in">
          <input name="postal_code" placeholder="Postal code" value="{{ user.postal_code or '' }}" class="afl-in">
        </div>
      </div>

      {% if company %}
      <div class="afl-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem">
          <h3 class="afl-h3" style="margin:0">Company</h3>
          <span class="afl-status {% if company.status == 'verified' %}confirmed{% elif company.status == 'pending' %}staged{% else %}failed{% endif %}">{{ company.status }}</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-top:.6rem">
          <input name="company_name" placeholder="Legal name" value="{{ company.name or '' }}" class="afl-in" style="grid-column:1/-1">
          <input name="company_registration" placeholder="Registration #" value="{{ company.registration_number or '' }}" class="afl-in">
          <input name="company_jurisdiction" placeholder="Jurisdiction" value="{{ company.jurisdiction or '' }}" class="afl-in">
          <input name="company_tax_id" placeholder="Tax ID / VAT" value="{{ company.tax_id or '' }}" class="afl-in">
          <input name="company_lei" placeholder="LEI" value="{{ company.lei_code or '' }}" class="afl-in">
          <input name="company_industry" placeholder="Industry" value="{{ company.industry or '' }}" class="afl-in" style="grid-column:1/-1">
        </div>
      </div>
      {% endif %}

      <div class="afl-card">
        <button class="afl-btn">Save changes</button>
        <a href="/auth/change-password" class="afl-btn secondary" style="text-decoration:none;display:inline-block;margin-left:.5rem">Change password</a>
      </div>
    </div>

    <div>
      <div class="afl-card">
        <h3 class="afl-h3">Account</h3>
        <div class="afl-k" style="margin-top:.6rem">Username</div>
        <div style="color:var(--text);margin-bottom:.6rem">{{ user.username }}</div>
        <div class="afl-k">Email</div>
        <div style="color:var(--text);margin-bottom:.6rem">{{ user.email }}</div>
        <div class="afl-k">Account type</div>
        <div style="color:var(--text);margin-bottom:.6rem">{{ user.account_type }}</div>
        <div class="afl-k">KYC status</div>
        <div style="margin-bottom:.6rem">
          <span class="afl-status {% if user.kyc_status == 'verified' %}confirmed{% elif user.kyc_status == 'pending' %}staged{% else %}failed{% endif %}">{{ user.kyc_status }}</span>
        </div>
        <div class="afl-k">Member since</div>
        <div style="color:var(--text)">{{ user.created_at.strftime('%Y-%m-%d') if user.created_at else '—' }}</div>
      </div>

      {% if company %}
      <div class="afl-card">
        <h3 class="afl-h3">Company summary</h3>
        <div class="afl-k" style="margin-top:.6rem">Users</div>
        <div style="color:var(--text)">{{ company.user_count }}</div>
        <div class="afl-k" style="margin-top:.6rem">Verified</div>
        <div style="color:var(--text)">
          {% if company.verified_at %}{{ company.verified_at.strftime('%Y-%m-%d') }}{% else %}Not yet{% endif %}
        </div>
      </div>
      {% endif %}
    </div>
  </div>
</form>
{% endblock %}
HTMLEOF

echo "  - templates written"

# --- 6. Add /profile link to sidebar (base.html) ---
if ! grep -q 'href="/auth/profile"' app/templates/base.html; then
    sed -i 's|<a href="/auth/change-password">.*</a>|<a href="/auth/profile"          class="{{ '"'"'active'"'"' if path.startswith('"'"'/auth/profile'"'"') }}">    <span class="ico">👤</span> Profile</a>\n      <a href="/auth/change-password">|<' app/templates/base.html || true
fi

# Fallback: simple append if sed failed
grep -q 'href="/auth/profile"' app/templates/base.html || \
  sed -i 's|{% if current_user.is_authenticated %}|{% if current_user.is_authenticated %}\n      <a href="/auth/profile"><span class="ico">👤</span> Profile</a>|' app/templates/base.html

echo "  - sidebar link added"

# --- 7. Generate and apply migration ---
echo ""
echo "== Generating migration =="
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['app/models/user.py','app/models/company.py','app/models/__init__.py','app/routes/auth.py']]; print('syntax OK')"

flask db migrate -m "add profile fields and Company model"
flask db upgrade

echo ""
echo "== Verifying =="
sqlite3 data/exchange.db ".tables" | tr ' ' '\n' | grep -E "companies|users" | sort -u

echo ""
echo "== DONE =="
echo "Now run: python app.py"
echo "Then visit: http://127.0.0.1:9105/auth/profile"
echo ""
