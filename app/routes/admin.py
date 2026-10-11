from datetime import datetime, timedelta, date
from functools import wraps

from flask import (Blueprint, render_template, jsonify, request,
                   redirect, url_for, flash)
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models.user import User
from app.models.transaction import Transaction, TransactionStatus
from app.models.license import License

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def d(*a, **k):
        if not current_user.is_admin:
            return jsonify({'error': 'admin only'}), 403
        return f(*a, **k)
    return d


# ------------------------------------------------------------------ dashboard
@admin_bp.route('/')
@admin_required
def dashboard():
    return render_template('admin/dashboard.html')


@admin_bp.route('/api/stats')
@admin_required
def stats():
    total_volume = float(db.session.query(func.sum(Transaction.from_amount)).scalar() or 0)
    total_margin = float(db.session.query(func.sum(Transaction.margin_amount)).scalar() or 0)
    return jsonify({
        'total_volume':   total_volume,
        'total_margin':   total_margin,
        'transactions':   Transaction.query.count(),
        'users':          User.query.count(),
        'licenses_active':  License.query.filter_by(status='active').count(),
        'licenses_pending': License.query.filter_by(status='pending').count(),
    })


# ------------------------------------------------------------------ blotter
@admin_bp.route('/blotter')
@admin_required
def blotter():
    page = max(1, int(request.args.get('page', '1')))
    per_page = min(200, max(10, int(request.args.get('per_page', '50'))))
    status_filter = request.args.get('status', '').strip()
    currency_filter = request.args.get('currency', '').strip()

    q = Transaction.query
    if status_filter:
        try:
            q = q.filter(Transaction.status == TransactionStatus(status_filter))
        except ValueError:
            pass
    if currency_filter:
        q = q.filter(
            (Transaction.from_currency == currency_filter) |
            (Transaction.to_currency == currency_filter)
        )

    total = q.count()
    rows = q.order_by(Transaction.created_at.desc()) \
            .offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        'admin/blotter.html',
        rows=rows, page=page, per_page=per_page, total=total,
        pages=(total + per_page - 1) // per_page,
        status_filter=status_filter, currency_filter=currency_filter,
        statuses=[s.value for s in TransactionStatus],
    )


# ------------------------------------------------------------------ positions
@admin_bp.route('/positions')
@admin_required
def positions_page():
    return render_template('admin/positions.html')


@admin_bp.route('/api/positions')
@admin_required
def positions_api():
    """Net position per currency across CONFIRMED + SETTLED transactions."""
    statuses = [TransactionStatus.CONFIRMED, TransactionStatus.SETTLED]

    out_rows = (db.session.query(
                    Transaction.from_currency.label('ccy'),
                    func.sum(Transaction.from_amount).label('amount'))
                .filter(Transaction.status.in_(statuses))
                .group_by(Transaction.from_currency).all())

    in_rows = (db.session.query(
                   Transaction.to_currency.label('ccy'),
                   func.sum(Transaction.to_amount).label('amount'))
               .filter(Transaction.status.in_(statuses))
               .group_by(Transaction.to_currency).all())

    net = {}
    for ccy, amt in out_rows:
        net[ccy] = net.get(ccy, 0) - float(amt or 0)
    for ccy, amt in in_rows:
        net[ccy] = net.get(ccy, 0) + float(amt or 0)

    return jsonify({
        'net': [{'currency': k, 'net': v} for k, v in sorted(net.items())],
        'outflows': [{'currency': c, 'amount': float(a or 0)} for c, a in out_rows],
        'inflows':  [{'currency': c, 'amount': float(a or 0)} for c, a in in_rows],
    })


# ------------------------------------------------------------------ P&L
@admin_bp.route('/api/pnl')
@admin_required
def pnl_api():
    """Daily platform margin (revenue) for the last 30 days."""
    days = int(request.args.get('days', '30'))
    days = min(365, max(7, days))
    start = datetime.utcnow() - timedelta(days=days)

    rows = (db.session.query(
                func.date(Transaction.created_at).label('day'),
                func.sum(Transaction.margin_amount).label('revenue'),
                func.count(Transaction.id).label('count'))
            .filter(Transaction.created_at >= start)
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at)).all())

    # Fill gaps
    out = []
    idx = {str(r.day): (float(r.revenue or 0), int(r.count or 0)) for r in rows}
    cur = start.date()
    end = date.today()
    while cur <= end:
        rev, cnt = idx.get(cur.isoformat(), (0.0, 0))
        out.append({'date': cur.isoformat(), 'revenue': rev, 'count': cnt})
        cur += timedelta(days=1)

    return jsonify({'series': out, 'total': sum(x['revenue'] for x in out)})


# ------------------------------------------------------------------ users
@admin_bp.route('/users')
@admin_required
def users_page():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/<int:uid>/toggle_admin', methods=['POST'])
@admin_required
def toggle_admin(uid):
    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash("You can't demote yourself")
        return redirect(url_for('admin.users_page'))
    u.is_admin = not u.is_admin
    db.session.commit()
    flash(f"{u.username}: admin={'ON' if u.is_admin else 'OFF'}")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/<int:uid>/toggle_active', methods=['POST'])
@admin_required
def toggle_active(uid):
    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash("You can't deactivate yourself")
        return redirect(url_for('admin.users_page'))
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"{u.username}: active={'ON' if u.is_active else 'OFF'}")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/<int:uid>/reset_password', methods=['POST'])
@admin_required
def reset_password(uid):
    u = User.query.get_or_404(uid)
    new_pw = request.form.get('new_password', '').strip()
    if len(new_pw) < 10:
        flash('Password must be at least 10 characters')
    else:
        u.set_password(new_pw)
        db.session.commit()
        flash(f"Password reset for {u.username}")
    return redirect(url_for('admin.users_page'))


# ------------------------------------------------------------------ Recent transactions feed
@admin_bp.route('/api/recent-transactions')
@admin_required
def recent_transactions():
    """Last N transactions for the admin dashboard table."""
    limit = min(50, max(1, int(request.args.get('limit', '10'))))
    rows = Transaction.query.order_by(Transaction.created_at.desc()).limit(limit).all()
    out = []
    for t in rows:
        out.append({
            'id': t.id,
            'reference': t.reference,
            'user': t.user.username if t.user else '—',
            'invoice': f"INV-{1000 + (t.id or 0)}",
            'details': f"{t.from_currency} → {t.to_currency}",
            'date': t.created_at.isoformat() if t.created_at else None,
            'amount': float(t.from_amount or 0),
            'currency': t.from_currency,
            'status': (t.status.value if t.status else 'unknown'),
        })
    return jsonify(out)


# ------------------------------------------------------------------ Live ticker
@admin_bp.route('/api/ticker')
@admin_required
def ticker():
    """Spot rates for the ticker row."""
    from app.services.rate_engine import get_engine
    eng = get_engine()
    pairs = [('BTC','USD'), ('EUR','USD'), ('GBP','USD'), ('XAU','USD')]
    out = []
    for f, t in pairs:
        try:
            rate = eng.get_mid_rate(f, t)
        except Exception:
            rate = 0.0
        out.append({'from': f, 'to': t, 'rate': rate})
    info = eng.source_info()
    return jsonify({'pairs': out, 'source': info.get('source', 'unknown')})


# ------------------------------------------------------------------ Balance snapshot
@admin_bp.route('/api/balance')
@admin_required
def balance():
    """
    Balance snapshot. Without a real ledger table yet, we derive:
      - cash_usd  = incoming - outgoing in USD equivalent (naive, from transactions)
      - btc_equiv = cash_usd converted via rate engine
    """
    from app.services.rate_engine import get_engine
    from sqlalchemy import func
    statuses = [TransactionStatus.CONFIRMED, TransactionStatus.SETTLED]

    incoming = float(db.session.query(func.sum(Transaction.to_amount))
                     .filter(Transaction.status.in_(statuses)).scalar() or 0)
    outgoing = float(db.session.query(func.sum(Transaction.from_amount))
                     .filter(Transaction.status.in_(statuses)).scalar() or 0)
    net_usd = incoming - outgoing

    eng = get_engine()
    try:
        btc_rate = eng.get_mid_rate('BTC', 'USD')  # USD per BTC
        btc_equiv = (net_usd / btc_rate) if btc_rate else 0.0
    except Exception:
        btc_equiv = 0.0

    return jsonify({
        'net_usd': net_usd,
        'btc_equiv': btc_equiv,
        'boost_pct': 11.1,   # keep the visual parity; wire to real metric later
    })


# ------------------------------------------------------------------ companies
@admin_bp.route('/companies')
@admin_required
def companies_page():
    """List companies, filtered by status."""
    from app.models.company import Company

    status_filter = request.args.get('status', 'pending').strip() or 'pending'
    page = max(1, int(request.args.get('page', '1')))
    per_page = min(100, max(10, int(request.args.get('per_page', '25'))))

    q = Company.query
    if status_filter != 'all':
        q = q.filter(Company.status == status_filter)
    q = q.order_by(Company.created_at.desc())

    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    counts = {
        'pending':   Company.query.filter_by(status='pending').count(),
        'verified':  Company.query.filter_by(status='verified').count(),
        'rejected':  Company.query.filter_by(status='rejected').count(),
        'suspended': Company.query.filter_by(status='suspended').count(),
        'all':       Company.query.count(),
    }

    return render_template(
        'admin/companies.html',
        rows=rows, page=page, per_page=per_page, total=total,
        pages=(total + per_page - 1) // per_page,
        status_filter=status_filter, counts=counts,
    )


@admin_bp.route('/companies/<int:cid>')
@admin_required
def company_detail(cid):
    from app.models.company import Company
    from app.models.user import User

    company = Company.query.get_or_404(cid)
    users = User.query.filter_by(company_id=cid).all()
    return render_template('admin/company_detail.html', company=company, users=users)


@admin_bp.route('/companies/<int:cid>/verify', methods=['POST'])
@admin_required
def company_verify(cid):
    from app.models.company import Company
    from app.models.user import User
    from datetime import datetime

    company = Company.query.get_or_404(cid)
    company.status = 'verified'
    company.verified_at = datetime.utcnow()
    company.verified_by_id = current_user.id
    company.rejection_reason = None

    # Upgrade KYC for all users of this company
    users = User.query.filter_by(company_id=cid).all()
    for u in users:
        u.kyc_status = 'verified'
        u.kyc_tier = 2

    db.session.commit()
    flash(f"Company '{company.name}' verified. {len(users)} user(s) upgraded to KYC tier 2.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/reject', methods=['POST'])
@admin_required
def company_reject(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    reason = (request.form.get('reason') or '').strip() or 'Not specified'

    company.status = 'rejected'
    company.rejection_reason = reason
    company.verified_at = None
    company.verified_by_id = current_user.id

    db.session.commit()
    flash(f"Company '{company.name}' rejected.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/suspend', methods=['POST'])
@admin_required
def company_suspend(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    company.status = 'suspended'
    db.session.commit()
    flash(f"Company '{company.name}' suspended.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/reinstate', methods=['POST'])
@admin_required
def company_reinstate(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    company.status = 'pending'
    company.rejection_reason = None
    db.session.commit()
    flash(f"Company '{company.name}' moved back to pending.")
    return redirect(url_for('admin.company_detail', cid=cid))


# ------------------------------------------------------------------ stats update
@admin_bp.route('/api/company-stats')
@admin_required
def company_stats():
    from app.models.company import Company
    return jsonify({
        'pending':  Company.query.filter_by(status='pending').count(),
        'verified': Company.query.filter_by(status='verified').count(),
        'rejected': Company.query.filter_by(status='rejected').count(),
        'total':    Company.query.count(),
    })


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
