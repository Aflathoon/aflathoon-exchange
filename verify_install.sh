#!/usr/bin/env bash
# =============================================================================
# Aflathoon Exchange - install verification
# Checks that every expected file exists, the DB is reachable, and admin exists.
# =============================================================================
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}[ OK ]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAILED=1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
FAILED=0

echo "== Verifying Aflathoon Exchange install =="
echo

# --- Files ---
FILES=(
    "app.py"
    "run.sh"
    ".env"
    "requirements.txt"
    "app/__init__.py"
    "app/models/__init__.py"
    "app/models/user.py"
    "app/models/transaction.py"
    "app/models/rate.py"
    "app/models/shipping.py"
    "app/models/license.py"
    "app/routes/__init__.py"
    "app/routes/main.py"
    "app/routes/auth.py"
    "app/routes/exchange.py"
    "app/routes/admin.py"
    "app/routes/logistics.py"
    "app/routes/compliance.py"
    "app/services/rate_engine.py"
    "app/services/margin.py"
    "app/services/war_risk.py"
    "app/services/license_guard.py"
    "app/services/compliance.py"
    "app/services/crypto_custody.py"
    "app/templates/index.html"
    "app/templates/auth/login.html"
    "app/templates/auth/register.html"
    "app/templates/auth/change_password.html"
    "app/templates/exchange/dashboard.html"
    "app/templates/logistics/quote.html"
    "app/templates/admin/dashboard.html"
    "app/templates/compliance/overview.html"
    "scripts/find_free_port.py"
    "scripts/backup_db.sh"
    "verify_install.sh"
)

MISSING=0
for f in "${FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        fail "missing: $f"
        MISSING=$((MISSING + 1))
    fi
done
[[ $MISSING -eq 0 ]] && pass "all ${#FILES[@]} expected files present"

# --- Venv ---
if [[ -d venv && -x venv/bin/python3 ]]; then
    pass "venv present"
else
    fail "venv missing or broken"
fi

# --- .env sanity ---
if grep -q "^SECRET_KEY=REPLACE" .env 2>/dev/null; then
    warn ".env SECRET_KEY still set to placeholder - regenerate!"
else
    pass ".env SECRET_KEY customised"
fi

if grep -q "^DATABASE_URL=" .env 2>/dev/null; then
    pass ".env has DATABASE_URL"
else
    warn ".env missing DATABASE_URL (app will use absolute default)"
fi

# --- DB accessible via the app itself ---
if [[ -x venv/bin/python3 ]]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    RESULT=$(python3 - << 'PYEOF' 2>/dev/null
import sys, os
sys.path.insert(0, os.getcwd())
try:
    from app import create_app
    from app.models.user import User
    app = create_app()
    with app.app_context():
        uri = app.config['SQLALCHEMY_DATABASE_URI']
        u = User.query.filter_by(username='admin').first()
        print(f"{uri}|{'yes' if u else 'no'}")
except Exception as e:
    print(f"ERROR|{e}")
PYEOF
)
    if [[ "$RESULT" == ERROR* ]]; then
        fail "app failed to start: $RESULT"
    else
        URI="${RESULT%|*}"; ADMIN="${RESULT#*|}"
        pass "DB reachable: $URI"
        [[ "$ADMIN" == "yes" ]] && pass "admin user exists" || fail "admin user missing"
    fi
fi

# --- Port availability ---
PORT=$(grep '^FLASK_PORT=' .env 2>/dev/null | cut -d= -f2 || echo "0")
if [[ -n "$PORT" && "$PORT" != "0" ]]; then
    if (echo > "/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
        warn "port ${PORT} is currently in use (server may already be running)"
    else
        pass "port ${PORT} is free"
    fi
fi

echo
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}=== All checks passed ===${NC}"
    exit 0
else
    echo -e "${RED}=== Some checks failed - see above ===${NC}"
    exit 1
fi
