import enum
from datetime import datetime
from app import db


class TransactionStatus(enum.Enum):
    PRE_STAGED = 'pre_staged'
    STAGED     = 'staged'
    CONFIRMED  = 'confirmed'
    SETTLED    = 'settled'
    CANCELLED  = 'cancelled'
    FAILED     = 'failed'


class TransactionType(enum.Enum):
    SPOT      = 'spot'
    FORWARD   = 'forward'
    SWAP      = 'swap'
    SHIPPING  = 'shipping'
    INSURANCE = 'insurance'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    transaction_type = db.Column(db.Enum(TransactionType), default=TransactionType.SPOT)
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PRE_STAGED)

    from_currency = db.Column(db.String(10), nullable=False)
    to_currency   = db.Column(db.String(10), nullable=False)
    from_amount   = db.Column(db.Numeric(20, 8), nullable=False)
    to_amount     = db.Column(db.Numeric(20, 8))

    # Pricing snapshot at booking time
    mid_rate       = db.Column(db.Numeric(20, 10))
    customer_rate  = db.Column(db.Numeric(20, 10))
    platform_margin = db.Column(db.Numeric(20, 8), default=0.065)
    margin_amount  = db.Column(db.Numeric(20, 8))
    fee_amount     = db.Column(db.Numeric(20, 8), default=0)

    # Rate source at booking time
    rate_source    = db.Column(db.String(20))   # live / cache / fallback

    # Logistics (future)
    shipping_cost   = db.Column(db.Numeric(20, 8), default=0)
    insurance_cost  = db.Column(db.Numeric(20, 8), default=0)
    war_risk_premium= db.Column(db.Numeric(20, 8), default=0)
    carrier_id      = db.Column(db.Integer, db.ForeignKey('carriers.id'))

    # Compliance snapshot
    kyc_verified     = db.Column(db.Boolean, default=False)
    sanctions_checked= db.Column(db.Boolean, default=False)
    compliance_notes = db.Column(db.Text)

    # Audit trail
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime)
    settled_at   = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Tx {self.reference} {self.from_amount}{self.from_currency}->{self.to_currency}>'


def next_reference() -> str:
    """Generate TX-YYYY-NNNNNN reference. Not atomic; fine for a single writer."""
    from datetime import datetime
    year = datetime.utcnow().year
    prefix = f"TX-{year}-"
    last = (Transaction.query
            .filter(Transaction.reference.like(f"{prefix}%"))
            .order_by(Transaction.reference.desc())
            .first())
    if last:
        try:
            seq = int(last.reference.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:06d}"
