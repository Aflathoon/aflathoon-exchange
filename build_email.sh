#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "== Building email verification + password reset =="

# --- EmailToken model ---
cat > app/models/email_token.py << 'PYEOF'
from datetime import datetime, timedelta
from app import db


class EmailToken(db.Model):
    __tablename__ = 'email_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='email_tokens')

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at

    @classmethod
    def new(cls, user_id, purpose, ttl_seconds):
        import secrets
        token = secrets.token_urlsafe(48)
        return cls(
            user_id=user_id,
            token=token,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
        )

    def __repr__(self):
        return f'<EmailToken {self.purpose} user={self.user_id}>'
PYEOF

# --- Email sender service ---
cat > app/services/email_sender.py << 'PYEOF'
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def _env_bool(name, default=False):
    v = os.getenv(name, str(default)).lower()
    return v in ('1', 'true', 'yes', 'on')


def _parse_from():
    raw = os.getenv('EMAIL_FROM', 'Aflathoon <noreply@localhost>')
    name = os.getenv('EMAIL_FROM_NAME', 'Aflathoon Exchange')
    if '<' in raw and '>' in raw:
        left, right = raw.split('<', 1)
        addr = right.split('>', 1)[0].strip()
        if left.strip():
            name = left.strip()
    else:
        addr = raw.strip()
    return name, addr


def send_email(to_addr, subject, body_text, body_html=None, reply_to=None):
    backend = os.getenv('EMAIL_BACKEND', 'console').lower().strip()
    if backend == 'console':
        _print_to_console(to_addr, subject, body_text, body_html)
        return True
    if backend == 'smtp':
        return _send_smtp(to_addr, subject, body_text, body_html, reply_to)
    raise RuntimeError(f"Unknown EMAIL_BACKEND: {backend!r}")


def _print_to_console(to_addr, subject, body_text, body_html):
    bar = '=' * 72
    print()
    print(bar)
    print(f"  [EMAIL] To:      {to_addr}")
    print(f"  [EMAIL] Subject: {subject}")
    print(bar)
    print(body_text)
    if body_html:
        print('-' * 72)
        print('  HTML version (truncated to 500 chars)')
        print(body_html[:500] + ('...' if len(body_html) > 500 else ''))
    print(bar)
    print()


def _send_smtp(to_addr, subject, body_text, body_html, reply_to):
    host = os.getenv('SMTP_HOST', '').strip()
    if not host:
        raise RuntimeError('SMTP_HOST not set but EMAIL_BACKEND=smtp')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER', '').strip()
    pwd  = os.getenv('SMTP_PASS', '').strip()
    use_tls = _env_bool('SMTP_USE_TLS', True)
    from_name, from_addr = _parse_from()

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr((from_name, from_addr))
    msg['To'] = to_addr
    if reply_to:
        msg['Reply-To'] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype='html')

    if use_tls:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=15) as s:
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    return True
PYEOF

# --- Email templates ---
cat > app/services/email_templates.py << 'PYEOF'
BRAND = "Aflathoon Exchange"


def _wrap_html(title, body_html):
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#0b0f1e;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#e8ecf6">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#0b0f1e;padding:32px 0">
    <tr><td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" width="560" style="background:#141a33;border-radius:14px;border:1px solid #222a4a">
        <tr><td style="padding:28px 32px 12px">
          <div style="font-size:1.2rem;font-weight:800;color:#6f8cff">{BRAND}</div>
        </td></tr>
        <tr><td style="padding:8px 32px 32px">
          <h1 style="font-size:1.4rem;color:#fff;margin:0 0 16px">{title}</h1>
          <div style="color:#cbd5e1;line-height:1.65;font-size:15px">{body_html}</div>
          <hr style="border:0;border-top:1px solid #222a4a;margin:24px 0">
          <div style="color:#8892b0;font-size:12px">If you didn't request this, ignore this email.</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def verify_email(user, url):
    text = f"""Hi {user.username},

Welcome to {BRAND}.

Please confirm your email address by clicking the link below:

{url}

This link expires in 48 hours.

- {BRAND}
"""
    html = _wrap_html(
        "Confirm your email",
        f"""<p>Hi <strong>{user.username}</strong>,</p>
            <p>Welcome to {BRAND}. Please confirm your email address to activate your account.</p>
            <p style="margin:24px 0"><a href="{url}" style="background:#6f8cff;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Confirm email</a></p>
            <p style="color:#8892b0;font-size:13px">Or copy: <span style="color:#6f8cff;word-break:break-all">{url}</span></p>"""
    )
    return text, html


def password_reset(user, url):
    text = f"""Hi {user.username},

A password reset was requested for your {BRAND} account.

Reset your password by clicking this link:

{url}

This link expires in 1 hour and can only be used once.

- {BRAND}
"""
    html = _wrap_html(
        "Reset your password",
        f"""<p>Hi <strong>{user.username}</strong>,</p>
            <p>A password reset was requested for your {BRAND} account.</p>
            <p style="margin:24px 0"><a href="{url}" style="background:#6f8cff;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Reset password</a></p>
            <p style="color:#8892b0;font-size:13px">Or copy: <span style="color:#6f8cff;word-break:break-all">{url}</span></p>"""
    )
    return text, html
PYEOF

# --- Register EmailToken ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "models" / "__init__.py"
src = p.read_text()
if "email_token" in src:
    print("  [skip] EmailToken already registered")
else:
    src = src.replace(
        "from app.models.license import License, Deadline, ComplianceDocument",
        "from app.models.license import License, Deadline, ComplianceDocument\n"
        "from app.models.email_token import EmailToken"
    )
    src = src.replace(
        "'License', 'Deadline', 'ComplianceDocument',",
        "'License', 'Deadline', 'ComplianceDocument', 'EmailToken',"
    )
    p.write_text(src)
    print("  [add ] EmailToken registered")
PYEOF

# --- Extend User model ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "models" / "user.py"
src = p.read_text()
if "email_verified" in src:
    print("  [skip] User already has email_verified")
else:
    needle = "    # Two-factor authentication"
    inject = (
        "    # Email verification\n"
        "    email_verified = db.Column(db.Boolean, default=False)\n"
        "    email_verified_at = db.Column(db.DateTime)\n"
        "\n"
        "    # Two-factor authentication"
    )
    if needle not in src:
        raise SystemExit("anchor for two-factor block not found")
    p.write_text(src.replace(needle, inject, 1))
    print("  [add ] User email_verified fields")
PYEOF

# --- Auth routes: verify / resend / forgot / reset ---
cat > /tmp/email_routes.py << 'PYEOF'

# =============================================================================
# Email verification + password reset
# =============================================================================
import os
from datetime import datetime
from flask import current_app, url_for
from app.models.email_token import EmailToken
from app.services import email_sender, email_templates


def _external_url(endpoint, **values):
    try:
        return url_for(endpoint, _external=True, **values)
    except Exception:
        base = os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:9105')
        path = url_for(endpoint, **values)
        return base.rstrip('/') + path


def send_verification_email(user):
    ttl = int(os.getenv('EMAIL_VERIFY_TTL', '172800'))
    token = EmailToken.new(user.id, 'email_verify', ttl)
    db.session.add(token)
    db.session.commit()
    url = _external_url('auth.verify_email', token=token.token)
    text, html = email_templates.verify_email(user, url)
    try:
        email_sender.send_email(user.email, 'Confirm your Aflathoon Exchange email', text, html)
    except Exception as e:
        current_app.logger.exception('Failed to send verification email: %s', e)
    return token


@auth_bp.route('/verify/<token>')
def verify_email(token):
    row = EmailToken.query.filter_by(token=token, purpose='email_verify').first()
    if not row or not row.is_valid:
        flash('Verification link is invalid or expired.')
        return redirect(url_for('auth.resend_verification'))
    user = User.query.get(row.user_id)
    if not user:
        flash('Account not found.')
        return redirect(url_for('auth.login'))
    if user.email_verified:
        flash('Email already verified. You can log in.')
        return redirect(url_for('auth.login'))
    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    row.used_at = datetime.utcnow()
    db.session.commit()
    flash('Email verified. You can log in now.')
    return redirect(url_for('auth.login'))


@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and not user.email_verified:
            send_verification_email(user)
        flash('If that email is registered and unverified, a new link has been sent.')
        return redirect(url_for('auth.login'))
    return render_template('auth/resend_verification.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            ttl = int(os.getenv('PASSWORD_RESET_TTL', '3600'))
            token = EmailToken.new(user.id, 'password_reset', ttl)
            db.session.add(token)
            db.session.commit()
            url = _external_url('auth.reset_password', token=token.token)
            text, html = email_templates.password_reset(user, url)
            try:
                email_sender.send_email(user.email, 'Reset your Aflathoon Exchange password', text, html)
            except Exception as e:
                current_app.logger.exception('Failed to send reset email: %s', e)
        flash('If that email is registered, a reset link has been sent.')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    row = EmailToken.query.filter_by(token=token, purpose='password_reset').first()
    if not row or not row.is_valid:
        flash('Reset link is invalid or expired.')
        return redirect(url_for('auth.forgot_password'))
    user = User.query.get(row.user_id)
    if not user:
        flash('Account not found.')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        new_pw = request.form.get('new_password') or ''
        confirm = request.form.get('confirm_password') or ''
        if len(new_pw) < 10:
            flash('Password must be at least 10 characters.')
        elif new_pw != confirm:
            flash('Passwords do not match.')
        else:
            user.set_password(new_pw)
            row.used_at = datetime.utcnow()
            db.session.commit()
            flash('Password reset successful. Please log in.')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)
PYEOF

# Append the routes file to auth.py (only if not already there)
if ! grep -q "forgot_password" app/routes/auth.py; then
    cat /tmp/email_routes.py >> app/routes/auth.py
    echo "  [add ] auth routes appended"
else
    echo "  [skip] auth routes already have email flows"
fi

# --- Syntax check ---
echo ""
echo "== Syntax check =="
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['app/models/user.py','app/models/email_token.py','app/models/__init__.py','app/routes/auth.py','app/services/email_sender.py','app/services/email_templates.py']]; print('all OK')"

# --- Migration ---
echo ""
echo "== Generating migration =="
flask db migrate -m "add EmailToken model and email_verified fields"
flask db upgrade

echo ""
echo "== Verifying =="
sqlite3 data/exchange.db ".tables" | tr ' ' '\n' | grep -E "^(email_tokens|users)$" || true
sqlite3 data/exchange.db "PRAGMA table_info(users);" | grep -E "email_verified" || true

echo ""
echo "== DONE =="
