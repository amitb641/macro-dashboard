#!/usr/bin/env python3
"""
Rolling Data Snapshot — keeps the last 13 known-good data snapshots
(≈ one quarter of weekly runs).
Runs after validation passes, before publishing.
Each snapshot is a timestamped copy of raw_data.json +
validation_report.json + the rendered index.html (so rollback can
restore the published page without re-running the renderer when the
issue is a renderer regression rather than bad input data).
Enables instant rollback if a future pipeline run produces bad data
*or* a bad render.

Rollback semantics
==================
- `--rollback YYYY-MM-DD`               restore raw_data.json only
                                        (existing behaviour; default).
- `--rollback YYYY-MM-DD --include-html` also restore index.html from
                                        that snapshot. Useful when the
                                        renderer itself is the regression.

Retention rationale
===================
The macro pipeline runs weekly. 13 snapshots ≈ 1 quarter of history,
which lines up with the quarterly cadence of:
  * earnings-season refreshes (Agent 9, Jan/Apr/Jul/Oct)
  * playbook noise-floor recalibrations
  * NIPA-style backward revisions to GDP / PCE
A bad week's data can therefore be diff-investigated against any prior
weekly print in the same quarter, not just the last 3 weeks.

Usage: python scripts/snapshot.py [--rollback YYYY-MM-DD [--include-html]]
"""

import json, shutil, sys, datetime, argparse
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
SNAP_DIR     = DATA_DIR / 'snapshots'
RAW_FILE     = DATA_DIR / 'raw_data.json'
VAL_FILE     = DATA_DIR / 'validation_report.json'
HTML_FILE    = ROOT / 'index.html'
# Bumped 3 → 13 to keep a full quarter of weekly snapshots. Override via
# the env var SNAPSHOT_MAX if you need to trim disk usage in CI.
import os as _os
try:
    MAX_SNAPSHOTS = max(1, int(_os.environ.get('SNAPSHOT_MAX', '13')))
except ValueError:
    MAX_SNAPSHOTS = 13


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

    # Copy data files + the rendered HTML. Including index.html lets a
    # rollback restore the live page even when the renderer is the
    # regression (e.g. a regex pattern that silently fell through on a
    # particular shape of raw_data). Without this we'd need to re-render
    # from a possibly-newer renderer.py against rolled-back data.
    for src in [RAW_FILE, VAL_FILE, HTML_FILE]:
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


def rollback(target_date, include_html=False):
    """Restore raw_data.json from a previous snapshot.

    When `include_html=True`, also overwrites index.html from the same
    snapshot (only useful when the renderer is itself the regression —
    most rollbacks are data-only and rebuild HTML via renderer.py).
    """
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

    if include_html:
        snap_html = snap_path / 'index.html'
        if snap_html.exists():
            shutil.copy2(snap_html, HTML_FILE)
            print(f'[Snapshot] Restored index.html from {target_date}')
            print(f'  (skip renderer.py re-run — HTML restored to snapshot state)')
        else:
            print(f'[Snapshot] Snapshot {target_date} has no index.html '
                  f'(taken before B6.3 retention bump); falling back to re-render')
            print(f'  Re-run renderer.py to rebuild index.html from restored data')
    else:
        print(f'  Re-run renderer.py to rebuild index.html from restored data')
    return True


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rollback', metavar='YYYY-MM-DD',
                   help='Restore raw_data.json from this snapshot date.')
    p.add_argument('--include-html', action='store_true',
                   help='With --rollback, also restore index.html '
                        '(use when the renderer is the regression).')
    args = p.parse_args()

    if args.rollback:
        sys.exit(0 if rollback(args.rollback, include_html=args.include_html) else 1)
    else:
        take_snapshot()
