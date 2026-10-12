#!/usr/bin/env python3
"""
Download + import the OpenSanctions default dataset.

Run from the project root (with venv active):
    FLASK_SKIP_ENGINES=1 python scripts/update_sanctions.py
    FLASK_SKIP_ENGINES=1 python scripts/update_sanctions.py --limit 1000

Flags:
    --limit N        only import first N records (for testing)
    --url URL        override the default dataset URL
    --quiet          suppress progress output
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('FLASK_SKIP_ENGINES', '1')

from app import create_app
from app.services import sanctions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None,
                    help='Only import the first N records (testing)')
    ap.add_argument('--url', default=None,
                    help='Override SANCTIONS_DATA_URL')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    if args.url:
        sanctions.DATA_URL = args.url

    print(f"[sanctions] URL: {sanctions.DATA_URL}")
    print(f"[sanctions] limit: {args.limit or 'unlimited'}")
    print(f"[sanctions] review threshold: {sanctions.THRESHOLD_REVIEW}")
    print(f"[sanctions] max hits per screen: {sanctions.MAX_HITS_PER_SCREEN}")
    print("")

    started = time.time()
    last_print = [0]

    def progress(n, done=False):
        if args.quiet:
            return
        now = time.time()
        if done or (now - last_print[0]) > 3:
            rate = n / max(1, now - started)
            print(f"[sanctions] imported {n:,} records "
                  f"({rate:,.0f}/s)", flush=True)
            last_print[0] = now

    try:
        total = sanctions.download_and_load(
            progress_cb=progress,
            limit=args.limit,
        )
    except Exception as e:
        print(f"[sanctions] FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    print("")
    print(f"[sanctions] DONE — {total:,} records in {elapsed:.1f}s")

    # Print summary stats
    app = create_app()
    with app.app_context():
        st = sanctions.stats()
        print(f"[sanctions] entities in DB: {st['entities']:,}")
        print(f"[sanctions] by type: {st['by_type']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
