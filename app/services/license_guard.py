"""
Refuses live trading if required licenses are missing or expired.
This protects the platform from operating illegally (and incurring fines).
"""
import os
from datetime import date
from flask import abort, current_app

REQUIRED = [x.strip() for x in os.getenv('LICENSE_REQUIRED_TYPES','msb').split(',') if x.strip()]
JURISDICTION = os.getenv('LICENSE_JURISDICTION','UK')
ENFORCEMENT  = os.getenv('LICENSE_ENFORCEMENT','strict')
LIVE_ENABLED = os.getenv('LIVE_TRADING_ENABLED','false').lower() == 'true'

def _active_licenses():
    from app.models.license import License
    return License.query.filter_by(status='active').all()

def missing_licenses():
    active = {l.license_type for l in _active_licenses() if l.is_valid}
    return [r for r in REQUIRED if r not in active]

def assert_live_trading_allowed():
    """Call at top of any endpoint that would move real money."""
    if ENFORCEMENT != 'strict':
        return  # dev mode only
    if not LIVE_ENABLED:
        abort(503, description='Live trading disabled (LIVE_TRADING_ENABLED=false).')
    missing = missing_licenses()
    if missing:
        abort(451, description=f'Missing or expired licenses for {JURISDICTION}: {missing}')
