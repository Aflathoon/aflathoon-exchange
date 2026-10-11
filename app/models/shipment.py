"""
Freight booking record.

Flow:
    quoted  -- user sees a price, wants to commit
    booked  -- user confirmed; carrier assigned; awaiting pickup
    picked_up -- cargo in carrier hands
    in_transit -- moving
    customs   -- at border/customs clearance
    delivered -- arrived
    delayed   -- temporary hold (customs, weather, war-risk zone)
    cancelled -- user or admin cancelled before pickup

Costs snapshot at booking time (like the FX margin snapshot):
    base_freight, insurance, war_risk, platform_margin
"""
import enum
from datetime import datetime
from app import db


class ShipmentStatus(enum.Enum):
    QUOTED     = 'quoted'
    BOOKED     = 'booked'
    PICKED_UP  = 'picked_up'
    IN_TRANSIT = 'in_transit'
    CUSTOMS    = 'customs'
    DELIVERED  = 'delivered'
    DELAYED    = 'delayed'
    CANCELLED  = 'cancelled'


class Shipment(db.Model):
    __tablename__ = 'shipments'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)   # SHP-YYYY-NNNNNN
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'))         # ledger link

    status = db.Column(db.Enum(ShipmentStatus), default=ShipmentStatus.QUOTED, index=True)

    # Route + cargo
    origin_country = db.Column(db.String(3))
    origin_city = db.Column(db.String(100))
    destination_country = db.Column(db.String(3))
    destination_city = db.Column(db.String(100))
    mode = db.Column(db.String(20))              # sea, air, road, rail, pipeline
    commodity_class = db.Column(db.String(50))   # general, heavy_oils, LNG, etc.
    weight_kg = db.Column(db.Numeric(20, 4))
    volume_m3 = db.Column(db.Numeric(20, 4))
    distance_km = db.Column(db.Numeric(20, 2))

    # Costs (snapshot at booking time)
    currency = db.Column(db.String(8), default='USD')
    base_freight = db.Column(db.Numeric(20, 8))
    insurance = db.Column(db.Numeric(20, 8))
    war_risk_premium = db.Column(db.Numeric(20, 8), default=0)
    platform_margin = db.Column(db.Numeric(20, 8), default=0.065)
    margin_amount = db.Column(db.Numeric(20, 8))
    total_cost = db.Column(db.Numeric(20, 8))

    # Waybill
    waybill_number = db.Column(db.String(60), index=True)
    tracking_url = db.Column(db.String(400))
    notes = db.Column(db.Text)

    # Timestamps
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    booked_at     = db.Column(db.DateTime)
    picked_up_at  = db.Column(db.DateTime)
    in_transit_at = db.Column(db.DateTime)
    customs_at    = db.Column(db.DateTime)
    delivered_at  = db.Column(db.DateTime)
    delayed_at    = db.Column(db.DateTime)
    cancelled_at  = db.Column(db.DateTime)

    # Relationships
    user = db.relationship('User', backref='shipments', foreign_keys=[user_id])
    carrier = db.relationship('Carrier')
    transaction = db.relationship('Transaction', foreign_keys=[transaction_id])

    @property
    def is_open(self):
        return self.status in (ShipmentStatus.QUOTED, ShipmentStatus.BOOKED,
                               ShipmentStatus.PICKED_UP, ShipmentStatus.IN_TRANSIT,
                               ShipmentStatus.CUSTOMS, ShipmentStatus.DELAYED)

    @property
    def route(self):
        o = self.origin_country or '—'
        d = self.destination_country or '—'
        return f"{o} → {d}"

    def status_badge_class(self):
        """Return an afl-status variant name for the current status."""
        return {
            'quoted':     'staged',
            'booked':     'staged',
            'picked_up':  'staged',
            'in_transit': 'staged',
            'customs':    'staged',
            'delivered':  'confirmed',
            'delayed':    'failed',
            'cancelled':  'cancelled',
        }.get(self.status.value if self.status else '', '')

    def __repr__(self):
        return f'<Shipment {self.reference} {self.status.value if self.status else "?"}>'


def next_shipment_reference() -> str:
    """Generate SHP-YYYY-NNNNNN reference, sequential per year."""
    year = datetime.utcnow().year
    prefix = f"SHP-{year}-"
    last = (Shipment.query
            .filter(Shipment.reference.like(f"{prefix}%"))
            .order_by(Shipment.reference.desc())
            .first())
    if last:
        try:
            seq = int(last.reference.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:06d}"
