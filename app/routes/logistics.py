from flask import (Blueprint, render_template, request, jsonify,
                   redirect, url_for, flash, current_app, abort)
from flask_login import login_required, current_user
from app import db
from app.models.shipment import Shipment, ShipmentStatus
from app.models.shipping import Carrier
from app.services.war_risk import compute_war_risk_premium
from app.services.freight_booking import book_shipment
from app.services import audit
from app.services.rate_limit import limit


logistics_bp = Blueprint('logistics', __name__)


# =============================================================================
# Quote calculator (existing, kept)
# =============================================================================
@logistics_bp.route('/')
@login_required
def index():
    return render_template('logistics/quote.html')


@logistics_bp.route('/quote', methods=['POST'])
@login_required
def quote():
    d = request.get_json() or {}
    try:
        weight = float(d.get('weight_kg') or 0)
        distance = float(d.get('distance_km') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid weight or distance'}), 400

    mode = d.get('mode', 'sea')
    route = (d.get('origin', ''), d.get('destination', ''))
    display_cur = (d.get('currency') or 'USD').upper()

    # Base calc is always in USD internally
    rate = {'sea': 0.05, 'air': 0.50, 'road': 0.08,
            'pipeline': 0.02, 'rail': 0.06}.get(mode, 0.05)
    base_usd = weight * distance * rate
    insurance_usd = base_usd * 0.005
    war_risk_usd = compute_war_risk_premium(base_usd, route)
    subtotal_usd = base_usd + insurance_usd + war_risk_usd
    margin_usd = subtotal_usd * 0.065
    total_usd = subtotal_usd + margin_usd

    # Convert to display currency
    fx = 1.0
    if display_cur != 'USD':
        try:
            from app.services.rate_engine import get_engine
            eng = get_engine()
            # customer rate already includes 6.5% spread; for a *display* conversion
            # we want the mid-rate so the underlying USD figure stays consistent
            fx = eng.get_mid_rate('USD', display_cur)
        except Exception:
            fx = 1.0

    def c(v):  # convert
        return round(v * fx, 2)

    return jsonify({
        'currency': display_cur,
        'fx_rate': fx,
        'base_freight': c(base_usd),
        'insurance': c(insurance_usd),
        'war_risk_premium': c(war_risk_usd),
        'platform_margin_6_5': c(margin_usd),
        'total': c(total_usd),
        'base_freight_usd': round(base_usd, 2),
        'insurance_usd': round(insurance_usd, 2),
        'war_risk_premium_usd': round(war_risk_usd, 2),
        'platform_margin_usd': round(margin_usd, 2),
        'total_usd': round(total_usd, 2),
    })


# =============================================================================
# Booking
# =============================================================================
@logistics_bp.route('/book', methods=['POST'])
@login_required
@limit('freight_book', 30, 60, json_response=True)
def book():
    """Commit a quote to a Shipment record."""
    d = request.get_json() or {}
    shipment, err = book_shipment(current_user, d)
    if err:
        return jsonify(err), 400

    audit.log('shipment.book', entity=shipment,
              summary=f"Freight booking {shipment.reference} "
                      f"{shipment.route} — {shipment.total_cost} {shipment.currency}")

    return jsonify({
        'ok': True,
        'reference': shipment.reference,
        'waybill': shipment.waybill_number,
        'status': shipment.status.value,
        'total': float(shipment.total_cost),
        'currency': shipment.currency,
        'detail_url': url_for('logistics.booking_detail', sid=shipment.id),
    })


# =============================================================================
# User's bookings
# =============================================================================
@logistics_bp.route('/bookings')
@login_required
def bookings():
    status_filter = request.args.get('status', '').strip()
    q = Shipment.query.filter_by(user_id=current_user.id)
    if status_filter and status_filter != 'all':
        try:
            q = q.filter(Shipment.status == ShipmentStatus(status_filter))
        except ValueError:
            pass
    rows = q.order_by(Shipment.created_at.desc()).all()

    counts = {
        'open':      Shipment.query.filter(
            Shipment.user_id == current_user.id,
            Shipment.status.in_([ShipmentStatus.BOOKED, ShipmentStatus.PICKED_UP,
                                 ShipmentStatus.IN_TRANSIT, ShipmentStatus.CUSTOMS,
                                 ShipmentStatus.DELAYED]),
        ).count(),
        'delivered': Shipment.query.filter_by(
            user_id=current_user.id, status=ShipmentStatus.DELIVERED).count(),
        'cancelled': Shipment.query.filter_by(
            user_id=current_user.id, status=ShipmentStatus.CANCELLED).count(),
        'all':       Shipment.query.filter_by(user_id=current_user.id).count(),
    }
    return render_template('logistics/bookings.html',
                           rows=rows, status_filter=status_filter, counts=counts)


@logistics_bp.route('/bookings/<int:sid>')
@login_required
def booking_detail(sid):
    shipment = Shipment.query.get_or_404(sid)
    if shipment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return render_template('logistics/booking_detail.html', s=shipment)


@logistics_bp.route('/bookings/<int:sid>/cancel', methods=['POST'])
@login_required
def booking_cancel(sid):
    shipment = Shipment.query.get_or_404(sid)
    if shipment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    # Can only cancel before pickup
    if shipment.status not in (ShipmentStatus.BOOKED, ShipmentStatus.QUOTED):
        flash('Shipments can only be cancelled before pickup.')
        return redirect(url_for('logistics.booking_detail', sid=sid))

    from datetime import datetime
    shipment.status = ShipmentStatus.CANCELLED
    shipment.cancelled_at = datetime.utcnow()
    db.session.commit()
    audit.log('shipment.cancel', entity=shipment,
              summary=f"User cancelled {shipment.reference}")
    flash('Shipment cancelled.')
    return redirect(url_for('logistics.bookings'))
