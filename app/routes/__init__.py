from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.exchange import exchange_bp
from app.routes.admin import admin_bp
from app.routes.logistics import logistics_bp
from app.routes.compliance import compliance_bp
from app.routes.kyc import kyc_bp
from app.routes.ticker import ticker_bp
from app.routes.alerts import alerts_bp
__all__ = ['main_bp','auth_bp','exchange_bp','admin_bp','logistics_bp','compliance_bp','kyc_bp','ticker_bp','alerts_bp']
