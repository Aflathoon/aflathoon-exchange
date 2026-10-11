from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services.rate_engine import get_engine
from app.services.margin import calculate_margin
from app.services.license_guard import missing_licenses
from app.services.booking import book_trade
from app.models.transaction import Transaction, TransactionStatus

exchange_bp = Blueprint('exchange', __name__)


@exchange_bp.route('/')
@login_required
def dashboard():
    engine = get_engine()
    recent = (Transaction.query
              .filter_by(user_id=current_user.id)
              .order_by(Transaction.created_at.desc())
              .limit(5).all())
    return render_template('exchange/dashboard.html',
                           live_enabled=current_app.config.get('LIVE_TRADING_ENABLED', False),
                           missing=missing_licenses(),
                           source=engine.source_info(),
                           recent=recent)


@exchange_bp.route('/source')
@login_required
def source():
    return jsonify(get_engine().source_info())


@exchange_bp.route('/convert', methods=['POST'])
@login_required
def convert():
    data = request.get_json() or {}
    fc = data.get('from_currency', 'USD')
    tc = data.get('to_currency', 'EUR')
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid amount'}), 400

    engine = get_engine()
    rate = engine.get_rate(fc, tc)
    margin = calculate_margin(amount, rate, current_app.config['PLATFORM_MARGIN'])
    info = engine.source_info()

    return jsonify({
        'from': fc, 'to': tc, 'amount': amount,
        'rate': rate,
        'gross': margin['converted_gross'],
        'platform_fee': margin['total_fee'],
        'margin_pct': margin['margin_pct'],
        'net_to_customer': margin['net_to_customer'],
        'live_trading': current_app.config.get('LIVE_TRADING_ENABLED', False),
        'rate_source': info['source'],
        'rate_source_age_seconds': info['last_success_seconds_ago'],
        'note': 'Indicative quote only. Booking a live trade requires active licenses.',
    })


@exchange_bp.route('/book', methods=['POST'])
@login_required
def book():
    """
    Persist a quote as a Transaction. Default is STAGED.
    Admins with active licenses get CONFIRMED.
    """
    data = request.get_json() or {}
    fc = data.get('from_currency', 'USD')
    tc = data.get('to_currency', 'EUR')
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid amount'}), 400

    # Live-trading gate: if enabled AND licenses are active, allow auto-confirm
    live = current_app.config.get('LIVE_TRADING_ENABLED', False)
    missing = missing_licenses()
    auto_confirm = bool(live and not missing and getattr(current_user, 'is_admin', False))

    tx, err = book_trade(current_user, fc, tc, amount, auto_confirm=auto_confirm)
    if err:
        return jsonify(err), 400

    return jsonify({
        'ok': True,
        'reference': tx.reference,
        'status': tx.status.value,
        'from': tx.from_currency,
        'to': tx.to_currency,
        'amount': float(tx.from_amount),
        'rate': float(tx.customer_rate),
        'net_to_customer': float(tx.to_amount),
        'margin_amount': float(tx.margin_amount),
        'rate_source': tx.rate_source,
        'confirmed_at': tx.confirmed_at.isoformat() if tx.confirmed_at else None,
        'compliance_notes': tx.compliance_notes,
    })


@exchange_bp.route('/rates')
def rates():
    return jsonify(get_engine().get_all_rates(request.args.get('base', 'USD')))
