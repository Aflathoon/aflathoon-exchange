"""
Freight booking service.

Takes a quote (from the calculator) and commits it to a Shipment record.
Snapshots all costs at booking time — later rate changes don't affect
an already-booked shipment.

Optionally creates a linked Transaction row so the shipping margin flows
into the same ledger as FX trades (P&L, positions, AI Assistant).
"""
from datetime import datetime
from flask import current_app
from app import db
from app.models.shipment import Shipment, ShipmentStatus, next_shipment_reference
from app.models.shipping import Carrier
from app.models.transaction import (
    Transaction, TransactionStatus, TransactionType, next_reference,
)


def _pick_carrier(mode):
    """Return an active carrier that serves this mode (or None)."""
    return (Carrier.query
            .filter_by(mode=mode, is_active=True)
            .order_by(Carrier.name)
            .first())


def _calc_costs(quote, platform_margin=0.065):
    """
    Given a raw quote dict (base_freight, insurance, war_risk, etc),
    compute the platform margin and total.
    """
    base = float(quote.get('base_freight') or 0)
    ins = float(quote.get('insurance') or 0)
    war = float(quote.get('war_risk_premium') or 0)
    subtotal = base + ins + war
    margin = subtotal * platform_margin
    return {
        'base_freight': round(base, 8),
        'insurance': round(ins, 8),
        'war_risk_premium': round(war, 8),
        'margin_amount': round(margin, 8),
        'total_cost': round(subtotal + margin, 8),
    }


def book_shipment(user, quote, create_transaction=True):
    """
    Commit a quote to a Shipment record.

    quote = {
        origin_country, origin_city,
        destination_country, destination_city,
        mode, commodity_class, weight_kg, volume_m3, distance_km,
        base_freight, insurance, war_risk_premium,
        currency, notes
    }

    Returns (shipment, error_dict_or_None).
    """
    # ---- validate ----
    if not quote.get('origin_country') or not quote.get('destination_country'):
        return None, {'error': 'origin and destination are required'}
    if quote['origin_country'] == quote['destination_country']:
        return None, {'error': 'origin and destination must differ'}
    try:
        weight = float(quote.get('weight_kg') or 0)
        distance = float(quote.get('distance_km') or 0)
    except (TypeError, ValueError):
        return None, {'error': 'invalid weight or distance'}
    if weight <= 0 or distance <= 0:
        return None, {'error': 'weight and distance must be positive'}

    # ---- costs ----
    platform_margin = float(current_app.config.get('PLATFORM_MARGIN', 0.065))
    costs = _calc_costs(quote, platform_margin)

    # ---- carrier ----
    carrier = _pick_carrier(quote.get('mode') or 'sea')

    # ---- shipment record ----
    shipment = Shipment(
        reference=next_shipment_reference(),
        user_id=user.id,
        carrier_id=carrier.id if carrier else None,
        status=ShipmentStatus.BOOKED,
        origin_country=quote['origin_country'],
        origin_city=quote.get('origin_city') or None,
        destination_country=quote['destination_country'],
        destination_city=quote.get('destination_city') or None,
        mode=quote.get('mode') or 'sea',
        commodity_class=quote.get('commodity_class') or 'general',
        weight_kg=weight,
        volume_m3=quote.get('volume_m3') or None,
        distance_km=distance,
        currency=quote.get('currency') or 'USD',
        base_freight=costs['base_freight'],
        insurance=costs['insurance'],
        war_risk_premium=costs['war_risk_premium'],
        platform_margin=platform_margin,
        margin_amount=costs['margin_amount'],
        total_cost=costs['total_cost'],
        notes=quote.get('notes') or None,
        booked_at=datetime.utcnow(),
        waybill_number=f"WB-{datetime.utcnow().strftime('%y%m%d')}-{user.id:04d}",
    )
    db.session.add(shipment)
    db.session.flush()   # get shipment.id for transaction link

    # ---- ledger link (optional) ----
    if create_transaction:
        try:
            tx = Transaction(
                reference=next_reference(),
                user_id=user.id,
                transaction_type=TransactionType.SHIPPING,
                status=TransactionStatus.CONFIRMED,
                from_currency=shipment.currency,
                to_currency=shipment.currency,
                from_amount=shipment.total_cost,
                to_amount=shipment.total_cost,
                mid_rate=1,
                customer_rate=1,
                platform_margin=platform_margin,
                margin_amount=shipment.margin_amount,
                rate_source='n/a',
                shipping_cost=shipment.base_freight,
                insurance_cost=shipment.insurance,
                war_risk_premium=shipment.war_risk_premium,
                confirmed_at=datetime.utcnow(),
                compliance_notes=f"Freight booking {shipment.reference}",
            )
            db.session.add(tx)
            db.session.flush()
            shipment.transaction_id = tx.id
        except Exception:
            # Non-fatal — shipment is still booked
            pass

    db.session.commit()
    return shipment, None
