#!/usr/bin/env python3
"""
Rolling Data Snapshot — keeps the last 3 known-good data snapshots.
Runs after validation passes, before publishing.
Each snapshot is a timestamped copy of raw_data.json + validation_report.json.
Enables instant rollback if a future pipeline run produces bad data.

Usage: python scripts/snapshot.py [--rollback YYYY-MM-DD]
"""

import json, shutil, sys, datetime
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
SNAP_DIR     = DATA_DIR / 'snapshots'
RAW_FILE     = DATA_DIR / 'raw_data.json'
VAL_FILE     = DATA_DIR / 'validation_report.json'
HTML_FILE    = ROOT / 'index.html'
MAX_SNAPSHOTS = 3


def take_snapshot():
    """Save current data as a timestamped snapshot. Prune oldest beyond MAX_SNAPSHOTS."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    snap_path = SNAP_DIR / ts

    # Don't overwrite an existing snapshot from today
    if snap_path.exists():
        print(f'[Snapshot] Already exists for {ts}, skipping')
        return

    snap_path.mkdir()

    # Copy data files
    for src in [RAW_FILE, VAL_FILE]:
        if src.exists():
            shutil.copy2(src, snap_path / src.name)

    # Save a lightweight manifest
    manifest = {
        'snapshot_date': ts,
        'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'files': [f.name for f in snap_path.iterdir()],
        'html_size': HTML_FILE.stat().st_size if HTML_FILE.exists() else 0,
    }

    # Include validation status if available
    if VAL_FILE.exists():
        try:
            val = json.loads(VAL_FILE.read_text())
            manifest['validation_status'] = val.get('status', 'unknown')
            manifest['validation_summary'] = val.get('summary', {})
        except Exception:
            pass

    (snap_path / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    print(f'[Snapshot] Saved snapshot: {ts}')

    # Prune old snapshots — keep only the most recent MAX_SNAPSHOTS
    existing = sorted([d for d in SNAP_DIR.iterdir() if d.is_dir()], reverse=True)
    for old in existing[MAX_SNAPSHOTS:]:
        shutil.rmtree(old)
        print(f'[Snapshot] Pruned old snapshot: {old.name}')

    print(f'[Snapshot] {min(len(existing), MAX_SNAPSHOTS)} snapshot(s) retained')


def rollback(target_date):
    """Restore raw_data.json from a previous snapshot."""
    snap_path = SNAP_DIR / target_date
    if not snap_path.exists():
        available = sorted([d.name for d in SNAP_DIR.iterdir() if d.is_dir()])
        print(f'[Snapshot] No snapshot for {target_date}')
        print(f'  Available: {", ".join(available) if available else "none"}')
        return False

    snap_raw = snap_path / 'raw_data.json'
    if not snap_raw.exists():
        print(f'[Snapshot] Snapshot {target_date} has no raw_data.json')
        return False

    shutil.copy2(snap_raw, RAW_FILE)
    print(f'[Snapshot] Restored raw_data.json from {target_date}')
    print(f'  Re-run renderer.py to rebuild index.html from restored data')
    return True


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--rollback':
        sys.exit(0 if rollback(sys.argv[2]) else 1)
    else:
        take_snapshot()
