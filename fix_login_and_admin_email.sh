#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "== Fix login forgot-password link + admin email verification UI =="

# --- 1. Patch login template: add forgot-password + resend links ---
python3 - << 'PYEOF'
from pathlib import Path
import re
p = Path.home() / "aflathoon_exchange" / "app" / "templates" / "auth" / "login.html"
src = p.read_text()

if 'forgot-password' in src:
    print("  [skip] login.html already has forgot-password link")
else:
    pattern = r'<div class="foot">[^<]*<a href="/auth/register">Register</a></div>'
    match = re.search(pattern, src)
    if match:
        replacement = (
            '<div class="foot">'
            '<a href="/auth/forgot-password">Forgot password?</a>'
            ' &middot; '
            '<a href="/auth/resend-verification">Resend verification</a>'
            '</div>\n'
            '  <div class="foot">No account? <a href="/auth/register">Register</a></div>'
        )
        src = src.replace(match.group(0), replacement, 1)
        p.write_text(src)
        print("  [add ] login.html: forgot-password + resend-verification links")
    else:
        print("  [warn] login.html anchor not found - manual edit needed")
PYEOF

# --- 2. Admin routes: verify email + resend + bulk ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "routes" / "admin.py"
src = p.read_text()

if "admin_verify_email" in src:
    print("  [skip] admin email-verify routes already present")
else:
    extra = '''

# =============================================================================
# Email verification admin actions
# =============================================================================
@admin_bp.route('/users/<int:uid>/verify_email', methods=['POST'])
@admin_required
def admin_verify_email(uid):
    """Manually mark a user's email as verified (bypasses link)."""
    from app.models.user import User
    from datetime import datetime

    u = User.query.get_or_404(uid)
    u.email_verified = True
    u.email_verified_at = datetime.utcnow()
    db.session.commit()
    flash(f"Email manually verified for {u.username}.")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/<int:uid>/send_verification', methods=['POST'])
@admin_required
def admin_send_verification(uid):
    """Trigger a fresh verification email for a user."""
    from app.models.user import User
    from app.routes.auth import send_verification_email

    u = User.query.get_or_404(uid)
    if u.email_verified:
        flash(f"{u.username}'s email is already verified.")
    else:
        try:
            send_verification_email(u)
            flash(f"Verification email sent to {u.email}.")
        except Exception as e:
            flash(f"Failed to send: {e}")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/<int:uid>/unverify_email', methods=['POST'])
@admin_required
def admin_unverify_email(uid):
    """Mark email as NOT verified (for testing or compliance)."""
    from app.models.user import User
    u = User.query.get_or_404(uid)
    u.email_verified = False
    u.email_verified_at = None
    db.session.commit()
    flash(f"Email unverified for {u.username}.")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/send_verification_all', methods=['POST'])
@admin_required
def admin_send_verification_all():
    """Send verification emails to every unverified user."""
    from app.models.user import User
    from app.routes.auth import send_verification_email

    unverified = User.query.filter_by(email_verified=False).all()
    sent = 0
    for u in unverified:
        try:
            send_verification_email(u)
            sent += 1
        except Exception:
            pass
    flash(f"Sent verification emails to {sent} of {len(unverified)} unverified users.")
    return redirect(url_for('admin.users_page'))
'''
    p.write_text(src + extra)
    print("  [add ] admin email verification routes")
PYEOF

# --- 3. Update admin users template ---
cat > app/templates/admin/users.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}Users — Aflathoon{% endblock %}
{% block search_placeholder %}Search users…{% endblock %}

{% block content %}
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
  <h1 class="afl-page-title" style="margin:0">Users</h1>
  <form method="post" action="/admin/users/send_verification_all" style="margin:0">
    <button class="afl-btn secondary" style="padding:.5rem 1rem">
      📧 Send verification to all unverified
    </button>
  </form>
</div>

<div class="tabs" style="margin:1rem 0">
  <a href="/admin/">Overview</a>
  <a href="/admin/blotter">Blotter</a>
  <a href="/admin/positions">Positions</a>
  <a class="active" href="/admin/users">Users</a>
  <a href="/admin/companies">Companies</a>
</div>

{% with messages = get_flashed_messages() %}
  {% if messages %}{% for m in messages %}
    <div class="afl-card" style="border-left:3px solid var(--green);padding:.7rem 1rem;margin-bottom:1rem">{{ m }}</div>
  {% endfor %}{% endif %}
{% endwith %}

<div class="afl-card">
  <table class="afl-table">
    <tr>
      <th>ID</th>
      <th>Username</th>
      <th>Email</th>
      <th>Email&nbsp;Verified</th>
      <th>Admin</th>
      <th>Active</th>
      <th>KYC</th>
      <th>Created</th>
      <th>Actions</th>
    </tr>
    {% for u in users %}
    <tr>
      <td>{{ u.id }}</td>
      <td>
        <strong>{{ u.username }}</strong>
        {% if u.full_name %}<div style="color:var(--muted);font-size:.72rem">{{ u.full_name }}</div>{% endif %}
      </td>
      <td>{{ u.email }}</td>
      <td>
        {% if u.email_verified %}
          <span class="afl-status confirmed" title="Verified {{ u.email_verified_at.strftime('%Y-%m-%d %H:%M') if u.email_verified_at else '' }}">verified</span>
        {% else %}
          <span class="afl-status failed">unverified</span>
        {% endif %}
      </td>
      <td><span class="afl-status {{ 'confirmed' if u.is_admin else 'failed' }}">{{ 'yes' if u.is_admin else 'no' }}</span></td>
      <td><span class="afl-status {{ 'confirmed' if u.is_active else 'failed' }}">{{ 'yes' if u.is_active else 'no' }}</span></td>
      <td>
        <span class="afl-status {% if u.kyc_status == 'verified' %}confirmed{% elif u.kyc_status == 'pending' %}staged{% else %}failed{% endif %}">
          {{ u.kyc_status }}
        </span>
      </td>
      <td>{{ u.created_at.strftime('%Y-%m-%d') if u.created_at else '—' }}</td>
      <td>
        <div style="display:flex;gap:.35rem;flex-wrap:wrap;align-items:center">
          {% if u.email_verified %}
            <form method="post" action="/admin/users/{{ u.id }}/unverify_email" style="margin:0">
              <button class="afl-btn secondary" style="padding:.3rem .7rem;font-size:.78rem" title="Mark email as unverified">Unverify</button>
            </form>
          {% else %}
            <form method="post" action="/admin/users/{{ u.id }}/send_verification" style="margin:0">
              <button class="afl-btn secondary" style="padding:.3rem .7rem;font-size:.78rem" title="Send a new verification email">Resend</button>
            </form>
            <form method="post" action="/admin/users/{{ u.id }}/verify_email" style="margin:0">
              <button class="afl-btn" style="padding:.3rem .7rem;font-size:.78rem;background:var(--green)" title="Verify manually">Verify</button>
            </form>
          {% endif %}

          <form method="post" action="/admin/users/{{ u.id }}/toggle_admin" style="margin:0">
            <button class="afl-btn secondary" style="padding:.3rem .7rem;font-size:.78rem">{{ 'Demote' if u.is_admin else 'Promote' }}</button>
          </form>
          <form method="post" action="/admin/users/{{ u.id }}/toggle_active" style="margin:0">
            <button class="afl-btn secondary" style="padding:.3rem .7rem;font-size:.78rem">{{ 'Deactivate' if u.is_active else 'Activate' }}</button>
          </form>
          <form method="post" action="/admin/users/{{ u.id }}/reset_password" style="display:flex;gap:.3rem;margin:0">
            <input name="new_password" placeholder="new pw" class="afl-in" style="width:110px;padding:.3rem .5rem;font-size:.78rem" minlength="10">
            <button class="afl-btn secondary" style="padding:.3rem .7rem;font-size:.78rem">Reset</button>
          </form>
        </div>
      </td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="afl-card" style="margin-top:1rem;border-left:3px solid var(--accent)">
  <strong style="color:var(--text)">How email verification works</strong>
  <ul style="color:var(--text-2);line-height:1.7;margin:.5rem 0 0 1.2rem;padding:0;font-size:.88rem">
    <li>New users get a verification email automatically when they register.</li>
    <li><strong>Unverified</strong> users can log in but see an amber banner and have limited features.</li>
    <li><strong>Resend</strong> triggers a fresh link (48h expiry, single-use).</li>
    <li><strong>Verify</strong> marks the email verified immediately (useful when SMTP isn't live yet).</li>
    <li><strong>Unverify</strong> reverses the flag (for testing or compliance review).</li>
  </ul>
</div>
{% endblock %}
HTMLEOF

echo "  [add ] admin users template with email verification column"

# --- 4. Syntax check ---
echo ""
echo "== Syntax check =="
python3 -c "import ast; ast.parse(open('app/routes/admin.py').read()); print('admin.py OK')"

echo ""
echo "== DONE =="
