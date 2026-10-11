from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next') or '/'

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        print(f"[LOGIN] POST user={username!r} pw_len={len(password)} next={next_url!r}", flush=True)

        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            login_user(u, remember=True)
            print(f"[LOGIN] OK -> redirect {next_url!r}", flush=True)
            return redirect(next_url)

        print(f"[LOGIN] FAILED", flush=True)
        flash('Invalid credentials')

    return render_template('auth/login.html', next=next_url)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username taken')
            return redirect(url_for('auth.register'))
        u = User(username=request.form['username'], email=request.form['email'])
        u.set_password(request.form['password'])
        db.session.add(u); db.session.commit()
        flash('Registered. Await KYC review.')
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
    from flask_login import current_user
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
