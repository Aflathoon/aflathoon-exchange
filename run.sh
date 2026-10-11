#!/usr/bin/env bash
# =============================================================================
trap "pkill -f "python app.py" 2>/dev/null; exit" INT TERM
# Aflathoon Exchange - startup script
# =============================================================================
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [[ ! -d venv ]]; then
    echo "ERROR: venv/ not found. Run the installer first."
    exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate

# Optional: log to file if AFLATHOON_LOG=1
if [[ "${AFLATHOON_LOG:-0}" == "1" ]]; then
    mkdir -p logs
    exec python app.py 2>&1 | tee -a "logs/run-$(date +%Y%m%d).log"
else
    exec python app.py
fi
