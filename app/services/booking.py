"""
Book a quote into a real Transaction row.

Rules:
  - Staged by default. Booking is a quote-accept action.
  - Confirm immediately ONLY if license guard allows AND user is admin.
  - Otherwise stays STAGED for admin review.
"""
from datetime import datetime
from flask import current_app

from app import db
from app.models.transaction import Transaction, TransactionStatus, TransactionType, next_reference
from app.services.rate_engine import get_engine
from app.services.margin import calculate_margin
from app.services.license_guard import missing_licenses


def book_trade(user, from_currency, to_currency, amount,
               auto_confirm=False, transaction_type=TransactionType.SPOT):
    """
    Returns (transaction, error_dict).
    error_dict is None on success.
    """
    if amount <= 0:
        return None, {'error': 'amount must be positive'}

    if from_currency == to_currency:
        return None, {'error': 'from and to currencies must differ'}

    engine = get_engine()
    info = engine.source_info()
    mid_rate      = engine.get_mid_rate(from_currency, to_currency)
    customer_rate = engine.get_rate(from_currency, to_currency)
    margin        = calculate_margin(amount, customer_rate, current_app.config['PLATFORM_MARGIN'])

    to_amount = margin['net_to_customer']

    tx = Transaction(
        reference         = next_reference(),
        user_id           = user.id,
        transaction_type  = transaction_type,
        status            = TransactionStatus.STAGED,
        from_currency     = from_currency,
        to_currency       = to_currency,
        from_amount       = amount,
        to_amount         = to_amount,
        mid_rate          = mid_rate,
        customer_rate     = customer_rate,
        platform_margin   = current_app.config['PLATFORM_MARGIN'],
        margin_amount     = margin['total_fee'],
        rate_source       = info.get('source', 'unknown'),
        kyc_verified      = getattr(user, 'kyc_status', 'pending') == 'verified',
        sanctions_checked = False,
    )

    # Auto-confirm only if admin AND licenses OK
    if auto_confirm and getattr(user, 'is_admin', False):
        missing = missing_licenses()
        if not missing:
            tx.status = TransactionStatus.CONFIRMED
            tx.confirmed_at = datetime.utcnow()
        else:
            tx.compliance_notes = f"Cannot auto-confirm: missing licenses {missing}"

    db.session.add(tx)
    db.session.commit()
    return tx, None
