from datetime import datetime
from app import db

class Carrier(db.Model):
    __tablename__ = 'carriers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mode = db.Column(db.String(20))
    commodity_classes = db.Column(db.String(200))
    base_rate_per_km = db.Column(db.Numeric(20, 8))
    base_rate_per_kg = db.Column(db.Numeric(20, 8))
    insurance_pct = db.Column(db.Numeric(8, 6), default=0.005)
    war_risk_multiplier = db.Column(db.Numeric(8, 4), default=1.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ShippingQuote(db.Model):
    __tablename__ = 'shipping_quotes'
    id = db.Column(db.Integer, primary_key=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)
    origin_country = db.Column(db.String(3))
    destination_country = db.Column(db.String(3))
    commodity_class = db.Column(db.String(50))
    weight_kg = db.Column(db.Numeric(20, 4))
    volume_m3 = db.Column(db.Numeric(20, 4))
    distance_km = db.Column(db.Numeric(20, 2))
    base_freight = db.Column(db.Numeric(20, 8))
    insurance_cost = db.Column(db.Numeric(20, 8))
    war_risk_premium = db.Column(db.Numeric(20, 8), default=0)
    platform_margin = db.Column(db.Numeric(20, 8), default=0.065)
    total_cost = db.Column(db.Numeric(20, 8))
    valid_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
