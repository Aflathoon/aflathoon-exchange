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
