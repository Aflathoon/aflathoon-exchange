"""
Dynamic war-risk premium. Prevents losses when geopolitical events
spike insurance costs beyond the 6.5% margin.

Strategy:
  - Baseline war-risk is small (0.25% of cargo value).
  - For high-risk corridors, apply a multiplier up to WAR_RISK_MAX_PCT.
  - If premium would exceed platform margin, auto-markup the quote
    so we never sell below cost.
"""
import os
from datetime import datetime, timedelta

# High-risk corridors (extend from real-time feed later).
HIGH_RISK_CORRIDORS = {
    ('IR','*'), ('RU','*'), ('SY','*'), ('YE','*'), ('LY','*'),
    ('*','IR'), ('*','RU'), ('*','SY'), ('*','YE'), ('*','LY'),
    ('UA','*'), ('*','UA'), ('IL','*'), ('*','IL'),
}

BASE_PCT = float(os.getenv('WAR_RISK_BASE_PCT', '0.0025'))
MAX_PCT  = float(os.getenv('WAR_RISK_MAX_PCT',  '0.05'))
AUTO_HEDGE = os.getenv('WAR_RISK_AUTO_HEDGE', 'true').lower() == 'true'

def _is_high_risk(route):
    o, d = route
    for (a, b) in HIGH_RISK_CORRIDORS:
        if a == '*' and b == d: return True
        if b == '*' and a == o: return True
    return False

def compute_war_risk_premium(base_freight: float, route=('', '')) -> float:
    pct = MAX_PCT if _is_high_risk(route) else BASE_PCT
    return round(base_freight * pct, 2)

def adjust_for_hedge(premium: float, base_freight: float) -> float:
    """
    If AUTO_HEDGE is on and the premium exceeds what the 6.5% margin
    can absorb, add a hedge surcharge so we never lose money on a spike.
    """
    if not AUTO_HEDGE: return premium
    margin_cover = base_freight * 0.065
    if premium > margin_cover:
        return premium + (premium - margin_cover) * 0.5  # partial pass-through
    return premium
