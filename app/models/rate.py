from datetime import datetime
from app import db

class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'
    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.String(10), nullable=False, index=True)
    quote_currency = db.Column(db.String(10), nullable=False, index=True)
    rate = db.Column(db.Numeric(20, 8), nullable=False)
    bid = db.Column(db.Numeric(20, 8))
    ask = db.Column(db.Numeric(20, 8))
    spread_pct = db.Column(db.Numeric(8, 6), default=0.065)
    source = db.Column(db.String(50), default='internal')
    asset_class = db.Column(db.String(20), default='fiat')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    valid_until = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    __table_args__ = (db.Index('idx_pair_time','base_currency','quote_currency','timestamp'),)
