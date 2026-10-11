from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify)
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, date
from app import db
from app.models.user import User
from app.models.company import Company
from app.services.rate_limit import limit

auth_bp = Blueprint('auth', __name__)


def _parse_date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


@auth_bp.route('/login', methods=['GET', 'POST'])
@limit('login', 10, 60, by='form:username')
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
            from app.services.csrf import rotate_token as _rot
            _rot()
            print(f"[LOGIN] OK -> redirect {next_url!r}", flush=True)
            return redirect(next_url)

        print("[LOGIN] FAILED", flush=True)
        flash('Invalid credentials')

    return render_template('auth/login.html', next=next_url)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limit('register', 5, 3600, by='ip')
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
    from app.services.csrf import rotate_token as _rot
    _rot()
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

    # Generate (or reuse) a pending secret — persist it to the DB so
    # a lost session (browser close, cache clear) doesn't wipe setup.
    if current_user.two_factor_secret and not current_user.two_factor_enabled:
        secret = current_user.two_factor_secret
    else:
        secret = tf.generate_secret()
        current_user.two_factor_secret = secret
        current_user.two_factor_enabled = False   # explicit; not yet confirmed
        db.session.commit()

    uri = tf.provisioning_uri(secret, current_user.username)
    qr = tf.qr_png_data_uri(uri)

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        if not tf.verify_code(secret, code):
            flash("Invalid code. Make sure your phone's clock is accurate, then try again.")
            return render_template('auth/2fa_setup.html',
                                   secret=secret, uri=uri, qr=qr, step='verify')

        # Generate and store backup codes, then flip the flag
        codes = tf.generate_backup_codes(10)
        current_user.two_factor_secret = secret
        current_user.two_factor_enabled = True
        current_user.two_factor_backup_codes = tf.hash_backup_codes(codes)
        current_user.two_factor_confirmed_at = datetime.utcnow()
        db.session.commit()
        print(f"[2FA] enabled for user {current_user.username} (id={current_user.id})", flush=True)

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
@limit('resend', 3, 3600, by='form:email')
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
@limit('forgot', 3, 3600, by='form:email')
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
