#!/usr/bin/env bash
# =============================================================================
# Backup the Aflathoon Exchange SQLite database
# Retains last 30 daily backups. Safe to run while the server is running
# (uses sqlite3's .backup command, not cp, to get a consistent snapshot).
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_FILE="${PROJECT_DIR}/data/exchange.db"
BACKUP_DIR="${PROJECT_DIR}/data/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_FILE" ]]; then
    echo "ERROR: DB not found at $DB_FILE"
    exit 1
fi

OUT="${BACKUP_DIR}/exchange-${STAMP}.db"

# Prefer sqlite3 .backup for a consistent snapshot
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_FILE" ".backup '${OUT}'"
else
    # Fallback: plain copy (fine if the app is idle)
    cp "$DB_FILE" "$OUT"
fi

# Verify the copy is readable
if ! sqlite3 "$OUT" "PRAGMA integrity_check;" 2>/dev/null | grep -q "^ok$"; then
    echo "WARN: integrity check failed on $OUT"
fi

# Rotate: keep last 30
ls -1t "${BACKUP_DIR}"/exchange-*.db 2>/dev/null | tail -n +31 | xargs -r rm -f

echo "Backup: $OUT"
echo "Total backups: $(ls -1 "${BACKUP_DIR}"/exchange-*.db 2>/dev/null | wc -l)"
