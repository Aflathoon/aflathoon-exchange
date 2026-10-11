#!/usr/bin/env bash
# =============================================================================
# Phase 2.5 — Two-Factor Authentication for Admin
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "== Building 2FA for admin =="

# --- 1. Extend User model with 2FA fields ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "models" / "user.py"
src = p.read_text()

if "two_factor_secret" in src:
    print("  [skip] User already has 2FA fields")
else:
    needle = "    # Timestamps\n    created_at = db.Column(db.DateTime, default=datetime.utcnow)"
    inject = (
        "    # Two-factor authentication\n"
        "    two_factor_secret = db.Column(db.String(64))              # TOTP secret (base32)\n"
        "    two_factor_enabled = db.Column(db.Boolean, default=False)\n"
        "    two_factor_backup_codes = db.Column(db.Text)             # JSON list of hashed codes\n"
        "    two_factor_confirmed_at = db.Column(db.DateTime)\n"
        "\n"
        "    # Timestamps\n"
        "    created_at = db.Column(db.DateTime, default=datetime.utcnow)"
    )
    if needle not in src:
        raise SystemExit("anchor for timestamps not found in user.py")
    src = src.replace(needle, inject, 1)
    p.write_text(src)
    print("  [add ] User 2FA fields")
PYEOF

# --- 2. Create 2FA service module ---
cat > app/services/two_factor.py << 'PYEOF'
"""
Two-factor authentication helpers.

Uses TOTP (RFC 6238) — compatible with Google Authenticator, Authy,
1Password, Bitwarden, Aegis, and every other standard authenticator app.

Backup codes:
- 10 codes, each 10 chars (base32-ish, human friendly)
- Stored as bcrypt hashes in User.two_factor_backup_codes (JSON list)
- Each code is one-time-use: on success it's removed from the list
"""
import base64
import io
import json
import secrets
import string

import pyotp
import qrcode
from werkzeug.security import generate_password_hash, check_password_hash


ISSUER = "Aflathoon Exchange"


# ----------------------------------------------------------------- secret
def generate_secret() -> str:
    """Return a fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str, issuer: str = ISSUER) -> str:
    """Return the otpauth:// URI for QR codes."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def qr_png_data_uri(uri: str, box_size: int = 8) -> str:
    """Render the otpauth URI as a PNG and return as a data: URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ----------------------------------------------------------------- verify
def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows ±1 window (30s) for clock drift."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ----------------------------------------------------------------- backup codes
_BACKUP_ALPHABET = string.ascii_uppercase + string.digits


def generate_backup_codes(count: int = 10, length: int = 10) -> list:
    """Human-friendly codes: 10 chars, uppercase + digits. Skip confusing chars."""
    alphabet = _BACKUP_ALPHABET.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    codes = []
    for _ in range(count):
        codes.append("".join(secrets.choice(alphabet) for _ in range(length)))
    return codes


def hash_backup_codes(codes: list) -> str:
    """Hash each code and return JSON-encoded list of hashes."""
    hashes = [generate_password_hash(c) for c in codes]
    return json.dumps(hashes)


def consume_backup_code(stored_json: str, candidate: str):
    """
    Check `candidate` against the stored hashes.
    Returns (matched: bool, new_json: str).
    If matched, the used hash is removed from the list.
    """
    if not stored_json:
        return False, stored_json
    try:
        hashes = json.loads(stored_json)
    except (ValueError, TypeError):
        return False, stored_json

    candidate = candidate.strip().upper().replace(" ", "").replace("-", "")
    for i, h in enumerate(hashes):
        if check_password_hash(h, candidate):
            remaining = hashes[:i] + hashes[i + 1:]
            return True, json.dumps(remaining)
    return False, stored_json


def remaining_backup_codes(stored_json: str) -> int:
    if not stored_json:
        return 0
    try:
        return len(json.loads(stored_json))
    except (ValueError, TypeError):
        return 0
PYEOF

echo "  [add ] app/services/two_factor.py"

# --- 3. Extend auth routes with 2FA logic ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "routes" / "auth.py"
src = p.read_text()

if "two_factor_setup" in src:
    print("  [skip] auth routes already have 2FA")
else:
    extra = '''

# =============================================================================
# Two-factor authentication
# =============================================================================
from app.services import two_factor as tf


def _require_2fa_or_redirect():
    """
    If the current user has 2FA enabled but hasn't verified this session,
    redirect to /auth/2fa/verify with the original URL as `next`.
    Returns None if OK, or a Flask redirect response if the user must verify.
    """
    from flask import session, request, redirect, url_for
    if not current_user.is_authenticated:
        return None
    if not getattr(current_user, 'two_factor_enabled', False):
        return None
    if session.get('two_factor_verified') is True:
        return None
    return redirect(url_for('auth.two_factor_verify', next=request.path))


@auth_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def two_factor_setup():
    from flask import session

    # Only allow setup when 2FA is currently OFF
    if current_user.two_factor_enabled:
        flash('2FA is already enabled. Disable it first to reconfigure.')
        return redirect(url_for('auth.two_factor_manage'))

    # Generate (or reuse) a pending secret stored in session
    if 'pending_2fa_secret' not in session:
        session['pending_2fa_secret'] = tf.generate_secret()
    secret = session['pending_2fa_secret']

    uri = tf.provisioning_uri(secret, current_user.username)
    qr = tf.qr_png_data_uri(uri)

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        if not tf.verify_code(secret, code):
            flash('Invalid code. Make sure your phone\'s clock is accurate, then try again.')
            return render_template('auth/2fa_setup.html',
                                   secret=secret, uri=uri, qr=qr, step='verify')

        # Generate and store backup codes
        codes = tf.generate_backup_codes(10)
        current_user.two_factor_secret = secret
        current_user.two_factor_enabled = True
        current_user.two_factor_backup_codes = tf.hash_backup_codes(codes)
        current_user.two_factor_confirmed_at = datetime.utcnow()
        db.session.commit()

        # Mark this session as 2FA-verified
        session['two_factor_verified'] = True
        session.pop('pending_2fa_secret', None)

        # Show backup codes once
        return render_template('auth/2fa_backup_codes.html', codes=codes)

    return render_template('auth/2fa_setup.html',
                           secret=secret, uri=uri, qr=qr, step='scan')


@auth_bp.route('/2fa/verify', methods=['GET', 'POST'])
def two_factor_verify():
    from flask import session

    next_url = request.args.get('next') or request.form.get('next') or '/'

    # Only meaningful if user is logged in but unverified
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=next_url))
    if not current_user.two_factor_enabled:
        session['two_factor_verified'] = True
        return redirect(next_url)
    if session.get('two_factor_verified') is True:
        return redirect(next_url)

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()

        # Try TOTP first
        if tf.verify_code(current_user.two_factor_secret, code):
            session['two_factor_verified'] = True
            return redirect(next_url)

        # Try backup code
        ok, new_json = tf.consume_backup_code(current_user.two_factor_backup_codes, code)
        if ok:
            current_user.two_factor_backup_codes = new_json
            db.session.commit()
            session['two_factor_verified'] = True
            remaining = tf.remaining_backup_codes(new_json)
            flash(f'Backup code accepted. {remaining} remaining.')
            return redirect(next_url)

        flash('Invalid code.')

    return render_template('auth/2fa_verify.html', next=next_url)


@auth_bp.route('/2fa/manage')
@login_required
def two_factor_manage():
    remaining = tf.remaining_backup_codes(current_user.two_factor_backup_codes or '')
    return render_template('auth/2fa_manage.html', remaining=remaining)


@auth_bp.route('/2fa/disable', methods=['POST'])
@login_required
def two_factor_disable():
    from flask import session

    password = request.form.get('password') or ''
    if not current_user.check_password(password):
        flash('Password incorrect. 2FA not disabled.')
        return redirect(url_for('auth.two_factor_manage'))

    current_user.two_factor_secret = None
    current_user.two_factor_enabled = False
    current_user.two_factor_backup_codes = None
    current_user.two_factor_confirmed_at = None
    db.session.commit()

    session.pop('two_factor_verified', None)
    flash('2FA disabled.')
    return redirect(url_for('auth.two_factor_manage'))


@auth_bp.route('/2fa/regenerate-backup-codes', methods=['POST'])
@login_required
def two_factor_regen_backup():
    if not current_user.two_factor_enabled:
        flash('Enable 2FA first.')
        return redirect(url_for('auth.two_factor_manage'))

    password = request.form.get('password') or ''
    if not current_user.check_password(password):
        flash('Password incorrect.')
        return redirect(url_for('auth.two_factor_manage'))

    codes = tf.generate_backup_codes(10)
    current_user.two_factor_backup_codes = tf.hash_backup_codes(codes)
    db.session.commit()
    return render_template('auth/2fa_backup_codes.html', codes=codes)


# =============================================================================
# Login post-hook: require 2FA verification
# =============================================================================
# We hook into Flask-Login's `session_protection` and rely on a
# before_request to enforce 2FA for users who have it enabled.
'''

    p.write_text(src + extra)
    print("  [add ] 2FA routes")
PYEOF

# --- 4. Before-request enforcement in create_app ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "__init__.py"
src = p.read_text()

if "enforce_2fa" in src:
    print("  [skip] 2FA enforcement already wired")
else:
    needle = "    # --- Create tables ---"
    inject = '''    # --- Enforce 2FA after login ---
    @app.before_request
    def enforce_2fa():
        from flask import request, redirect, url_for, session
        from flask_login import current_user

        # Whitelist: static files, auth routes, 2FA routes
        path = request.path or ''
        if path.startswith(('/static/', '/auth/2fa/', '/auth/logout',
                            '/auth/login', '/auth/register', '/health')):
            return None

        if not current_user.is_authenticated:
            return None
        if not getattr(current_user, 'two_factor_enabled', False):
            return None
        if session.get('two_factor_verified') is True:
            return None

        # Must verify 2FA
        return redirect(url_for('auth.two_factor_verify', next=path))

    # --- Create tables ---'''
    if needle not in src:
        raise SystemExit("anchor '# --- Create tables ---' not found")
    src = src.replace(needle, inject, 1)
    p.write_text(src)
    print("  [add ] 2FA enforcement hook")
PYEOF

echo "  [done] backend"

# --- 5. Templates ---
cat > app/templates/auth/2fa_setup.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}Set Up 2FA — Aflathoon{% endblock %}
{% block search_placeholder %}Two-factor authentication{% endblock %}

{% block content %}
<h1 class="afl-page-title">Set Up Two-Factor Authentication</h1>

<div class="afl-card" style="max-width:620px">
  {% with messages = get_flashed_messages() %}
    {% if messages %}{% for m in messages %}
      <div style="padding:.6rem .9rem;border-radius:8px;margin-bottom:.8rem;background:rgba(239,68,68,.12);color:var(--red-fg);border:1px solid rgba(239,68,68,.25)">{{ m }}</div>
    {% endfor %}{% endif %}
  {% endwith %}

  {% if step == 'scan' %}
    <h3 class="afl-h3">Step 1 — Scan the QR code</h3>
    <p style="color:var(--text-2);line-height:1.6">
      Open your authenticator app (Google Authenticator, Authy, 1Password, Bitwarden, Aegis — any TOTP app works).
      Tap <strong>Add account</strong> → <strong>Scan QR code</strong>, then point at the image below.
    </p>

    <div style="text-align:center;background:#fff;padding:1rem;border-radius:12px;display:inline-block;margin:.5rem 0">
      <img src="{{ qr }}" alt="2FA QR code" style="width:220px;height:220px;display:block">
    </div>

    <details style="margin-top:1rem">
      <summary style="cursor:pointer;color:var(--accent);font-weight:600">Can't scan? Enter this code manually</summary>
      <div style="margin-top:.6rem;padding:.8rem;background:var(--input-bg);border:1px solid var(--border);border-radius:8px;font-family:monospace;font-size:1rem;letter-spacing:.15em;color:var(--text);word-break:break-all">
        {{ secret }}
      </div>
    </details>

    <h3 class="afl-h3" style="margin-top:1.4rem">Step 2 — Enter the 6-digit code</h3>
    <form method="post">
      <input name="code" placeholder="123 456" inputmode="numeric" pattern="[0-9 ]*" maxlength="7"
             autocomplete="one-time-code" autofocus class="afl-in" style="width:200px;font-size:1.4rem;letter-spacing:.3em;text-align:center">
      <button class="afl-btn" style="margin-left:.5rem">Verify &amp; activate</button>
    </form>
  {% endif %}
</div>
{% endblock %}
HTMLEOF

cat > app/templates/auth/2fa_backup_codes.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}Backup Codes — Aflathoon{% endblock %}
{% block search_placeholder %}Backup codes{% endblock %}

{% block content %}
<h1 class="afl-page-title">Save your backup codes</h1>

<div class="afl-card" style="max-width:620px;border-left:4px solid var(--amber)">
  <h3 class="afl-h3">⚠ One-time view</h3>
  <p style="color:var(--text-2);line-height:1.6">
    Store these somewhere safe. Each code works <strong>once</strong>, in place of a 6-digit TOTP code.
    If you lose your phone and your backup codes, you'll lose access to your account.
  </p>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin:1.2rem 0;font-family:monospace;font-size:1.05rem">
    {% for c in codes %}
    <div style="padding:.6rem .8rem;background:var(--input-bg);border:1px solid var(--border);border-radius:8px;text-align:center;color:var(--text);letter-spacing:.15em">
      {{ c }}
    </div>
    {% endfor %}
  </div>

  <div style="display:flex;gap:.6rem;flex-wrap:wrap">
    <button type="button" class="afl-btn secondary" onclick="copyAll()">📋 Copy all</button>
    <button type="button" class="afl-btn secondary" onclick="printCodes()">🖨 Print</button>
    <a href="/auth/2fa/manage" class="afl-btn" style="text-decoration:none">I've saved them →</a>
  </div>

  <p style="color:var(--muted);font-size:.8rem;margin-top:1rem">
    This page won't show again. If you lose the codes, use
    <strong>Regenerate backup codes</strong> from the 2FA management page.
  </p>
</div>

<script>
function copyAll() {
  const codes = {{ codes | tojson }};
  navigator.clipboard.writeText(codes.join('\n')).then(() => alert('Copied ' + codes.length + ' codes to clipboard.'));
}
function printCodes() {
  const w = window.open('', '', 'width=600,height=800');
  const codes = {{ codes | tojson }};
  w.document.write('<h2>Aflathoon Exchange — Backup Codes</h2><pre style="font-size:18px;letter-spacing:3px">' + codes.join('\n') + '</pre>');
  w.document.close();
  w.print();
}
</script>
{% endblock %}
HTMLEOF

cat > app/templates/auth/2fa_verify.html << 'HTMLEOF'
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verify 2FA — Aflathoon</title>
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
.auth-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:2rem;width:420px;max-width:95vw;box-shadow:var(--shadow);text-align:center}
.auth-card h2{margin:0 0 1rem;color:var(--accent);font-size:1.4rem}
.auth-card input{width:100%;padding:.9rem;margin:.6rem 0;background:var(--input-bg);border:1px solid var(--border);color:var(--text);border-radius:10px;box-sizing:border-box;font-size:1.4rem;letter-spacing:.4em;text-align:center;font-family:monospace}
.auth-card input:focus{outline:none;border-color:var(--accent)}
.auth-card button{width:100%;padding:.85rem;background:var(--accent);color:#fff;border:0;border-radius:10px;cursor:pointer;font-weight:600;font-size:1rem;margin-top:.4rem}
.auth-card .msg{padding:.6rem .9rem;border-radius:8px;margin-bottom:.8rem;font-size:.88rem;background:rgba(239,68,68,.12);color:var(--red-fg);border:1px solid rgba(239,68,68,.25);text-align:left}
.auth-card .hint{font-size:.82rem;color:var(--muted);margin-top:.8rem;text-align:center}
.auth-card a{color:var(--accent);text-decoration:none}
</style>
</head>
<body class="afl-auth">
<form class="auth-card" method="post">
  <h2>Two-factor verification</h2>
  {% with messages = get_flashed_messages() %}
    {% if messages %}{% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}{% endif %}
  {% endwith %}
  <input type="hidden" name="next" value="{{ next or '/' }}">
  <p style="color:var(--muted);font-size:.88rem;margin:0 0 .6rem">Enter the 6-digit code from your authenticator app.</p>
  <input name="code" inputmode="numeric" pattern="[0-9A-Za-z ]*" maxlength="12"
         autocomplete="one-time-code" autofocus placeholder="000000">
  <button>Verify</button>
  <p class="hint">Lost your phone? Enter one of your backup codes above.<br>
  <a href="/auth/logout">Cancel and log out</a></p>
</form>
</body></html>
HTMLEOF

cat > app/templates/auth/2fa_manage.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}Two-Factor Authentication — Aflathoon{% endblock %}
{% block search_placeholder %}2FA settings{% endblock %}

{% block content %}
<h1 class="afl-page-title">Two-Factor Authentication</h1>

{% with messages = get_flashed_messages() %}
  {% if messages %}{% for m in messages %}
    <div class="afl-card" style="border-left:3px solid var(--green);padding:.7rem 1rem;margin-bottom:1rem">{{ m }}</div>
  {% endfor %}{% endif %}
{% endwith %}

<div class="afl-card" style="max-width:640px">
  {% if current_user.two_factor_enabled %}
    <h3 class="afl-h3">✓ 2FA is <span style="color:var(--green-fg)">enabled</span></h3>
    <p style="color:var(--text-2);line-height:1.6">
      Your account is protected by a TOTP authenticator. Every login requires a fresh code.
    </p>

    <table class="afl-table" style="margin-top:1rem">
      <tr><td class="afl-k">Enabled on</td><td>{{ current_user.two_factor_confirmed_at.strftime('%Y-%m-%d %H:%M') if current_user.two_factor_confirmed_at else '—' }}</td></tr>
      <tr><td class="afl-k">Backup codes remaining</td><td>{{ remaining }} of 10</td></tr>
    </table>

    <div style="display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1.2rem">
      <form method="post" action="/auth/2fa/regenerate-backup-codes" style="display:flex;gap:.4rem;align-items:center">
        <input name="password" type="password" placeholder="Your password" class="afl-in" required>
        <button class="afl-btn secondary">Regenerate backup codes</button>
      </form>
    </div>

    <hr style="border:0;border-top:1px solid var(--border);margin:1.4rem 0">

    <h3 class="afl-h3" style="color:var(--red-fg)">Danger zone</h3>
    <p style="color:var(--muted);font-size:.85rem">Disabling 2FA reduces your account security.</p>
    <form method="post" action="/auth/2fa/disable" style="display:flex;gap:.4rem;align-items:center">
      <input name="password" type="password" placeholder="Confirm your password" class="afl-in" required>
      <button class="afl-btn" style="background:var(--red)">Disable 2FA</button>
    </form>
  {% else %}
    <h3 class="afl-h3">2FA is currently <span style="color:var(--amber-fg)">disabled</span></h3>
    <p style="color:var(--text-2);line-height:1.6">
      Add a second layer of security. After enabling, you'll need a code from your authenticator app
      (Google Authenticator, Authy, 1Password, Bitwarden, Aegis) on every login.
    </p>
    <p style="color:var(--muted);font-size:.85rem;margin-top:.6rem">
      <strong>Admins should enable 2FA.</strong> It's the single most effective protection
      against credential stuffing and phishing.
    </p>
    <a href="/auth/2fa/setup" class="afl-btn" style="text-decoration:none;display:inline-block;margin-top:1rem">Set up 2FA →</a>
  {% endif %}
</div>

<div class="afl-card" style="max-width:640px;margin-top:1rem">
  <h3 class="afl-h3">How it works</h3>
  <ol style="color:var(--text-2);line-height:1.8;margin:.4rem 0 0 1.2rem;padding:0;font-size:.88rem">
    <li>You scan a QR code with your authenticator app — done once, at setup.</li>
    <li>The app generates a new 6-digit code every 30 seconds.</li>
    <li>On login, you enter the current code after your password.</li>
    <li>If you lose your phone, use one of the 10 backup codes.</li>
  </ol>
</div>
{% endblock %}
HTMLEOF

echo "  [add ] 2FA templates"

# --- 6. Add link to sidebar ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "templates" / "base.html"
src = p.read_text()

if '/auth/2fa/manage' in src:
    print("  [skip] sidebar already has 2FA link")
else:
    needle = '<a href="/auth/change-password">'
    if needle in src:
        indent = '      '
        insert = f'{indent}<a href="/auth/2fa/manage"><span class="ico">🔐</span> 2FA</a>\n{indent}'
        src = src.replace(needle, insert + needle, 1)
        p.write_text(src)
        print("  [add ] sidebar 2FA link")
    else:
        print("  [skip] change-password link not found in sidebar")
PYEOF

# --- 7. Generate migration ---
echo ""
echo "== Generating migration =="
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['app/models/user.py','app/routes/auth.py','app/services/two_factor.py','app/__init__.py']]; print('syntax OK')"

flask db migrate -m "add two-factor authentication fields"
flask db upgrade

# --- 8. Verify ---
echo ""
echo "== Verifying =="
sqlite3 data/exchange.db "PRAGMA table_info(users);" | grep -E "two_factor" || echo "(no two_factor columns found - check migration)"

echo ""
echo "== DONE =="
echo "Restart the server and visit /auth/2fa/manage while logged in as admin."
echo ""
