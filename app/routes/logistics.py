from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from app.services.war_risk import compute_war_risk_premium

logistics_bp = Blueprint('logistics', __name__)

@logistics_bp.route('/')
@login_required
def index(): return render_template('logistics/quote.html')

@logistics_bp.route('/quote', methods=['POST'])
@login_required
def quote():
    d = request.get_json() or {}
    weight = float(d.get('weight_kg', 0))
    distance = float(d.get('distance_km', 0))
    mode = d.get('mode', 'sea')
    route = (d.get('origin',''), d.get('destination',''))
    rate = {'sea':0.05,'air':0.50,'road':0.08,'pipeline':0.02,'rail':0.06}.get(mode,0.05)
    base = weight * distance * rate
    insurance = base * 0.005
    # Dynamic war-risk (WARNING #3 fix)
    war_risk = compute_war_risk_premium(base, route)
    subtotal = base + insurance + war_risk
    margin = subtotal * 0.065
    return jsonify({
        'base_freight': round(base,2), 'insurance': round(insurance,2),
        'war_risk_premium': round(war_risk,2),
        'platform_margin_6_5': round(margin,2),
        'total': round(subtotal+margin,2),
    })
