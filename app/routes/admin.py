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
