from datetime import datetime, timedelta, date
from functools import wraps

from flask import (Blueprint, render_template, jsonify, request,
                   redirect, url_for, flash)
from flask_login import current_user, login_required, current_user
from sqlalchemy import func

from app import db
from app.services import audit
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
    before = {'is_admin': u.is_admin}
    u.is_admin = not u.is_admin
    db.session.commit()
    audit.log('user.toggle_admin', entity=u,
              summary=f"{u.username} admin set to {u.is_admin}",
              before=before, after={'is_admin': u.is_admin})
    flash(f"{u.username}: admin={'ON' if u.is_admin else 'OFF'}")
    return redirect(url_for('admin.users_page'))


@admin_bp.route('/users/<int:uid>/toggle_active', methods=['POST'])
@admin_required
def toggle_active(uid):
    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash("You can't deactivate yourself")
        return redirect(url_for('admin.users_page'))
    before = {'is_active': u.is_active}
    u.is_active = not u.is_active
    db.session.commit()
    audit.log('user.toggle_active', entity=u,
              summary=f"{u.username} active set to {u.is_active}",
              before=before, after={'is_active': u.is_active})
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
        audit.log('user.reset_password', entity=u,
                  summary=f"Password reset for {u.username} by admin")
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
    before = {'email_verified': u.email_verified}
    u.email_verified = True
    u.email_verified_at = datetime.utcnow()
    db.session.commit()
    audit.log('user.verify_email', entity=u,
              summary=f"Manually verified email for {u.username}",
              before=before, after={'email_verified': True})
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
    audit.log('user.unverify_email', entity=u,
              summary=f"Unverified email for {u.username}",
              after={'email_verified': False})
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


# =============================================================================
# Audit log viewer
# =============================================================================
@admin_bp.route('/audit')
@admin_required
def audit_log():
    from app.models.audit_log import AuditLog
    from app.models.user import User

    page = max(1, int(request.args.get('page', '1')))
    per_page = min(200, max(20, int(request.args.get('per_page', '50'))))
    action_filter = request.args.get('action', '').strip()
    actor_filter = request.args.get('actor', '').strip()

    q = AuditLog.query
    if action_filter:
        q = q.filter(AuditLog.action.like(f"{action_filter}%"))
    if actor_filter:
        q = q.filter(AuditLog.actor_username == actor_filter)

    q = q.order_by(AuditLog.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    # Distinct actions for filter dropdown
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct().all()]
    actors = [r[0] for r in db.session.query(AuditLog.actor_username).distinct().all() if r[0]]

    return render_template('admin/audit.html',
        rows=rows, page=page, per_page=per_page, total=total,
        pages=(total + per_page - 1) // per_page,
        action_filter=action_filter, actor_filter=actor_filter,
        actions=sorted(actions), actors=sorted(actors),
    )


# =============================================================================
# AI Assistant
# =============================================================================
@admin_bp.route('/assistant')
@admin_required
def assistant_page():
    from app.services import assistant
    findings = assistant.scan_all()
    s = assistant.summary(findings)
    return render_template('admin/assistant.html', findings=findings, summary=s)


@admin_bp.route('/api/assistant/scan')
@admin_required
def assistant_scan():
    from app.services import assistant
    findings = assistant.scan_all()
    s = assistant.summary(findings)
    return jsonify({
        'summary': s,
        'findings': [f.to_dict() for f in findings],
    })


# =============================================================================
# AI Assistant action runner
# =============================================================================
@admin_bp.route('/api/assistant/run', methods=['POST'])
@admin_required
def assistant_run():
    from app.services import audit
    from app.models.user import User

    data = request.get_json(silent=True) or {}
    kind = (data.get('kind') or '').strip()
    payload = data.get('payload') or {}
    result = {'ok': False, 'message': 'Unknown action.'}

    if kind == 'resend_verification_all':
        from app.routes.auth import send_verification_email
        unverified = User.query.filter_by(email_verified=False).all()
        sent = 0
        for u in unverified:
            try:
                send_verification_email(u)
                sent += 1
            except Exception:
                pass
        result = {'ok': True, 'message': f'Sent verification emails to {sent} user(s).'}
        audit.log('assistant.resend_verification_all',
                  summary=f'Bulk resend verification: {sent} sent',
                  after={'sent': sent, 'total': len(unverified)})

    elif kind == 'notify_admins_2fa':
        from app.services import email_sender
        admins = User.query.filter_by(is_admin=True, is_active=True).all()
        missing = [u for u in admins if not u.two_factor_enabled]
        sent = 0
        for u in missing:
            try:
                body = (
                    f"Hi {u.username},\n\n"
                    "As an admin at Aflathoon Exchange, please enable two-factor "
                    "authentication on your account for security.\n\n"
                    "Open your 2FA settings here:\n"
                    "http://127.0.0.1:9105/auth/2fa/manage\n\n"
                    "- Aflathoon Exchange\n"
                )
                email_sender.send_email(
                    u.email,
                    'Enable 2FA on your Aflathoon admin account',
                    body,
                )
                sent += 1
            except Exception:
                pass
        result = {'ok': True, 'message': f'2FA reminder sent to {sent} admin(s).'}
        audit.log('assistant.notify_admins_2fa',
                  summary=f'Notified {sent} admin(s) to enable 2FA',
                  after={'sent': sent})

    elif kind == 'run_backup':
        import subprocess, os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script = os.path.join(root, 'scripts', 'backup_db.sh')
        if not os.path.exists(script):
            result = {'ok': False, 'message': f'Backup script not found: {script}'}
        else:
            try:
                proc = subprocess.run([script], capture_output=True, text=True, timeout=60)
                out = (proc.stdout or '').strip().splitlines()
                last = out[-1] if out else 'done'
                result = {'ok': proc.returncode == 0,
                          'message': f'Backup: {last}' if proc.returncode == 0 else f'Failed: {(proc.stderr or "")[-200:]}'}
                audit.log('assistant.run_backup',
                          summary=f'Manual backup via assistant (exit {proc.returncode})',
                          after={'output': last[:200]})
            except Exception as e:
                result = {'ok': False, 'message': f'Error: {e}'}

    elif kind == 'reset_rate_cache':
        try:
            from app.services.rate_engine import get_engine
            eng = get_engine()
            # Safely clear the cache whatever it's called internally
            cleared = 0
            for attr in ('_cache', '_raw_rates'):
                obj = getattr(eng, attr, None)
                if isinstance(obj, dict):
                    cleared += len(obj)
                    obj.clear()
            # If the engine has a public refresh method, call it
            if hasattr(eng, '_refresh_once'):
                try:
                    eng._refresh_once()
                except Exception:
                    pass
            result = {'ok': True, 'message': f'Rate cache cleared ({cleared} entries).'}
            audit.log('assistant.reset_rate_cache', summary='Rate cache cleared')
        except Exception as e:
            result = {'ok': False, 'message': f'Error: {e}'}

    elif kind == 'list_company_ids':
        ids = payload.get('ids') or []
        result = {'ok': True, 'message': f'{len(ids)} companies pending. Open each from Companies tab.'}

    else:
        result = {'ok': False, 'message': f'Unknown action kind: {kind}'}

    return jsonify(result)


# =============================================================================
# KYC submission review
# =============================================================================
@admin_bp.route('/kyc')
@admin_required
def kyc_review_list():
    from app.models.kyc_submission import KYCSubmission
    status_filter = request.args.get('status', 'pending')
    page = max(1, int(request.args.get('page', '1')))
    per_page = 25

    q = KYCSubmission.query
    if status_filter != 'all':
        q = q.filter(KYCSubmission.status == status_filter)
    q = q.order_by(KYCSubmission.submitted_at.desc())

    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    counts = {
        'pending':  KYCSubmission.query.filter_by(status='pending').count(),
        'approved': KYCSubmission.query.filter_by(status='approved').count(),
        'rejected': KYCSubmission.query.filter_by(status='rejected').count(),
        'all':      KYCSubmission.query.count(),
    }
    return render_template('admin/kyc_list.html',
                           rows=rows, page=page, total=total,
                           pages=(total + per_page - 1) // per_page,
                           status_filter=status_filter, counts=counts)


@admin_bp.route('/kyc/<int:sid>')
@admin_required
def kyc_review_detail(sid):
    from app.models.kyc_submission import KYCSubmission
    sub = KYCSubmission.query.get_or_404(sid)
    return render_template('admin/kyc_detail.html', sub=sub)


@admin_bp.route('/kyc/<int:sid>/approve', methods=['POST'])
@admin_required
def kyc_approve(sid):
    from app.models.kyc_submission import KYCSubmission
    from app.models.user import User
    sub = KYCSubmission.query.get_or_404(sid)
    tier = int(request.form.get('tier') or sub.tier_requested or 2)

    sub.status = 'approved'
    sub.reviewer_id = current_user.id
    sub.reviewed_at = datetime.utcnow()
    sub.tier_requested = tier

    u = User.query.get(sub.user_id)
    if u:
        u.kyc_status = 'verified'
        u.kyc_tier = tier
    db.session.commit()

    audit.log('kyc.approve', entity=sub,
              summary=f'KYC approved for user {sub.user_id} (tier {tier})')
    flash(f'KYC approved for user {sub.user_id}. Tier set to {tier}.')
    return redirect(url_for('admin.kyc_review_list'))


@admin_bp.route('/kyc/<int:sid>/reject', methods=['POST'])
@admin_required
def kyc_reject(sid):
    from app.models.kyc_submission import KYCSubmission
    from app.models.user import User
    sub = KYCSubmission.query.get_or_404(sid)
    notes = (request.form.get('notes') or '').strip() or 'Did not meet requirements'

    sub.status = 'rejected'
    sub.reviewer_id = current_user.id
    sub.reviewed_at = datetime.utcnow()
    sub.reviewer_notes = notes

    u = User.query.get(sub.user_id)
    if u:
        u.kyc_status = 'rejected'
    db.session.commit()

    audit.log('kyc.reject', entity=sub,
              summary=f'KYC rejected for user {sub.user_id}: {notes[:80]}')
    flash('KYC rejected. User has been notified.')
    return redirect(url_for('admin.kyc_review_list'))


# =============================================================================
# Alerts management
# =============================================================================
@admin_bp.route('/alerts')
@admin_required
def alerts_page():
    from app.models.alert import Alert
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    active = Alert.query.filter(
        (Alert.expires_at.is_(None)) | (Alert.expires_at > now)
    ).order_by(Alert.created_at.desc()).all()

    expired = Alert.query.filter(
        Alert.expires_at.isnot(None),
        Alert.expires_at <= now,
    ).order_by(Alert.created_at.desc()).limit(50).all()

    return render_template('admin/alerts.html', active=active, expired=expired, now=now)


@admin_bp.route('/alerts/create', methods=['POST'])
@admin_required
def alerts_create():
    from app.models.alert import Alert
    from datetime import datetime, timedelta

    title = (request.form.get('title') or '').strip()
    if not title:
        flash('Title is required')
        return redirect(url_for('admin.alerts_page'))

    hours = int(request.form.get('hours') or 24)
    a = Alert(
        severity=request.form.get('severity') or 'info',
        title=title[:200],
        body=(request.form.get('body') or '').strip() or None,
        link_url=(request.form.get('link_url') or '').strip() or None,
        link_label=(request.form.get('link_label') or '').strip() or None,
        created_by_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=hours) if hours > 0 else None,
    )
    db.session.add(a)
    db.session.commit()
    audit.log('alert.create', entity=a, summary=f"Created alert: {title[:60]}")
    flash(f'Alert "{title[:40]}" created.')
    return redirect(url_for('admin.alerts_page'))


@admin_bp.route('/alerts/<int:aid>/delete', methods=['POST'])
@admin_required
def alerts_delete(aid):
    from app.models.alert import Alert
    a = Alert.query.get_or_404(aid)
    title = a.title
    db.session.delete(a)
    db.session.commit()
    audit.log('alert.delete', summary=f"Deleted alert: {title[:60]}")
    flash('Alert deleted.')
    return redirect(url_for('admin.alerts_page'))
