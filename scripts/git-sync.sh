#!/usr/bin/env bash
# Automated git sync — run via cron or manually
set -euo pipefail

cd "$(dirname "$0")/.."

# Make sure we're in a git repo
if [ ! -d .git ]; then
  echo "Not a git repo — run: git init && git remote add origin <url>" >&2
  exit 1
fi

# Stage everything
git add -A

# Commit only if there are changes
if git diff --cached --quiet; then
  echo "[$(date '+%F %T')] no changes"
else
  git commit -m "auto-backup: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Push to whichever branch exists
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
git push origin "$BRANCH"
