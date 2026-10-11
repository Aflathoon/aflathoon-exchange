import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache

# Load .env before ANY os.getenv() call below, so every env var
# (DATABASE_URL, WAR_RISK_*, API keys, etc.) is actually visible.
from dotenv import load_dotenv
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)
cache = Cache()


def _resolve_db_uri() -> str:
    """
    Always return an absolute SQLite URI under <project_root>/data/exchange.db
    unless DATABASE_URL is explicitly set to something non-sqlite (e.g. postgres).
    """
    env_url = os.environ.get('DATABASE_URL', '').strip()

    # If a Postgres URL is given, trust it as-is
    if env_url.startswith(('postgresql://', 'postgres://', 'postgresql+psycopg2://')):
        return env_url

    # Otherwise force an absolute SQLite path under the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    db_file = os.path.join(data_dir, 'exchange.db')
    # sqlite:///<abs_path>  -> sqlite:////home/... on Linux
    return f"sqlite:///{db_file}"


def create_app(config_name: str = None):
    app = Flask(__name__)

    # --- Core config ---
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-fallback-key-change-me')
    app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_db_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PLATFORM_MARGIN'] = float(os.getenv('PLATFORM_MARGIN_PCT', '0.065'))
    app.config['LIVE_TRADING_ENABLED'] = os.getenv('LIVE_TRADING_ENABLED', 'false').lower() == 'true'

    # --- Cache ---
    app.config['CACHE_TYPE'] = os.getenv('CACHE_TYPE', 'SimpleCache')
    app.config['CACHE_DEFAULT_TIMEOUT'] = int(os.getenv('CACHE_DEFAULT_TIMEOUT', '300'))

    # --- Session cookie config ---
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_NAME'] = 'aflathoon_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7

    # --- Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    limiter.init_app(app)
    cache.init_app(app)

    # --- User loader (Flask-Login) ---
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return db.session.get(User, int(user_id))

    # --- Blueprints ---
    from app.routes import main_bp, auth_bp, exchange_bp, admin_bp, logistics_bp, compliance_bp, kyc_bp, ticker_bp, alerts_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(exchange_bp, url_prefix='/exchange')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(logistics_bp, url_prefix='/logistics')
    app.register_blueprint(compliance_bp, url_prefix='/compliance')
    app.register_blueprint(kyc_bp, url_prefix='/kyc')
    app.register_blueprint(ticker_bp)
    app.register_blueprint(alerts_bp)

    # --- Enforce 2FA after login ---
    @app.before_request
    def enforce_2fa():
        from flask import request, redirect, url_for, session
        from flask_login import current_user

        # Whitelist: static files, auth routes, 2FA routes
        path = request.path or ''
        if path.startswith(('/static/', '/auth/2fa/', '/auth/logout',
                            '/auth/login', '/auth/register', '/health')):
            return None

        if not current_user.is_authenticated:
            return None
        if not getattr(current_user, 'two_factor_enabled', False):
            return None
        if session.get('two_factor_verified') is True:
            return None

        # Must verify 2FA
        return redirect(url_for('auth.two_factor_verify', next=path))

    # --- CSRF protection ---
    from app.services import csrf
    from app.services.csrf import validate as csrf_validate

    @app.before_request
    def csrf_inject():
        return csrf_validate()

    @app.context_processor
    def csrf_inject_context():
        from app.services.csrf import inject_template_helper
        return inject_template_helper()

    # --- Background engines ---
    # Only start when actually serving requests, not on CLI imports
    import os as _os
    _should_start_engines = (
        _os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or    # debug reloader child
        _os.environ.get('FLASK_SKIP_ENGINES') != '1'         # normal startup
    )
    if _os.environ.get('FLASK_SKIP_ENGINES') != '1' and        _os.environ.get('_AFL_ENGINES_STARTED') != '1':
        _os.environ['_AFL_ENGINES_STARTED'] = '1'
        try:
            from app.services import alert_engine
            alert_engine.start_engine()
        except Exception as _e:
            print(f"[app] alert_engine start failed: {_e}", flush=True)

        try:
            from app.services import price_alerts
            price_alerts.start_engine()
        except Exception as _e:
            print(f"[app] price_alerts start failed: {_e}", flush=True)

    # --- Create tables ---
    with app.app_context():
        # Import models so they register with SQLAlchemy metadata
        from app import models  # noqa: F401
        db.create_all()

    # --- Debug print so we always know which file we opened ---
    print(f"[app] DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

    return app
