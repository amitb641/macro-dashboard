#!/usr/bin/env python3
"""
Rolling Data Snapshot — keeps the last 52 known-good data snapshots
(≈ one year of weekly runs). Runs after validation passes, before publishing.

Each snapshot is a timestamped directory containing:
  raw_data.json          — full API pull (~2 MB) — enables complete re-render
  state.json             — Tier-1 chart payload  (~41 KB)
  signals.json           — analyzer output        (~5.5 KB)
  validation_report.json — validator verdict      (~108 KB)
  index.html             — rendered dashboard     (~670 KB)
  manifest.json          — run metadata (sizes, validation status, sha256)

Override retention: SNAPSHOT_MAX env var (e.g. SNAPSHOT_MAX=13 for a quarter).
Rollback: python scripts/snapshot.py --rollback YYYY-MM-DD [--include-html]
"""

import hashlib, json, shutil, sys, datetime, argparse
from pathlib import Path
import os as _os

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
SNAP_DIR     = DATA_DIR / 'snapshots'
RAW_FILE     = DATA_DIR / 'raw_data.json'
STATE_FILE   = DATA_DIR / 'state.json'
SIGNALS_FILE = DATA_DIR / 'signals.json'
VAL_FILE     = DATA_DIR / 'validation_report.json'
HTML_FILE    = ROOT / 'index.html'

_DEFAULT_MAX = 52  # one year of weekly runs
try:
    MAX_SNAPSHOTS = max(1, int(_os.environ.get('SNAPSHOT_MAX', str(_DEFAULT_MAX))))
except ValueError:
    MAX_SNAPSHOTS = _DEFAULT_MAX


def _sha256(path: Path) -> str:
    """Return hex SHA-256 of a file, or '' if the file is missing."""
    if not path.exists():
        return ''
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


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

    # Files to capture for rollback completeness
    snapshot_files = [RAW_FILE, STATE_FILE, SIGNALS_FILE, VAL_FILE, HTML_FILE]
    copied, sizes = [], {}
    for src in snapshot_files:
        if src.exists():
            dest = snap_path / src.name
            shutil.copy2(src, dest)
            copied.append(src.name)
            sizes[src.name] = src.stat().st_size

    # Save a manifest with sizes + checksums for integrity verification
    manifest = {
        'snapshot_date': ts,
        'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'files': copied,
        'sizes': sizes,
        'sha256': {
            'raw_data.json':          _sha256(RAW_FILE),
            'state.json':             _sha256(STATE_FILE),
            'signals.json':           _sha256(SIGNALS_FILE),
            'validation_report.json': _sha256(VAL_FILE),
            'index.html':             _sha256(HTML_FILE),
        },
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

    total_kb = sum(sizes.values()) / 1024
    print(f'[Snapshot] Saved snapshot: {ts} ({total_kb:.0f} KB across {len(copied)} file(s))')

    # Prune old snapshots — keep only the most recent MAX_SNAPSHOTS
    existing = sorted([d for d in SNAP_DIR.iterdir() if d.is_dir()], reverse=True)
    for old in existing[MAX_SNAPSHOTS:]:
        shutil.rmtree(old)
        print(f'[Snapshot] Pruned old snapshot: {old.name}')

    retained = min(len(existing), MAX_SNAPSHOTS)
    print(f'[Snapshot] {retained} snapshot(s) retained (max {MAX_SNAPSHOTS})')


def rollback(target_date: str, include_html: bool = False) -> bool:
    """Restore data files from a previous snapshot.

    Always restores: raw_data.json, state.json, signals.json.
    With --include-html: also restores index.html (skips renderer re-run).
    """
    snap_path = SNAP_DIR / target_date
    if not snap_path.exists():
        available = sorted([d.name for d in SNAP_DIR.iterdir() if d.is_dir()])
        print(f'[Snapshot] No snapshot for {target_date}')
        print(f'  Available: {", ".join(available) if available else "none"}')
        return False

    snap_raw = snap_path / 'raw_data.json'
    if not snap_raw.exists():
        print(f'[Snapshot] Snapshot {target_date} has no raw_data.json — cannot rollback')
        return False

    restored = []
    for src_name, dest in [
        ('raw_data.json', RAW_FILE),
        ('state.json',    STATE_FILE),
        ('signals.json',  SIGNALS_FILE),
    ]:
        src = snap_path / src_name
        if src.exists():
            shutil.copy2(src, dest)
            restored.append(src_name)

    if include_html:
        snap_html = snap_path / 'index.html'
        if snap_html.exists():
            shutil.copy2(snap_html, HTML_FILE)
            restored.append('index.html')
            print(f'[Snapshot] Restored {", ".join(restored)} from {target_date}')
            print(f'  index.html restored directly — no renderer re-run needed')
        else:
            print(f'[Snapshot] Restored {", ".join(restored)} from {target_date}')
            print(f'  --include-html requested but index.html not in snapshot; re-run renderer.py')
    else:
        print(f'[Snapshot] Restored {", ".join(restored)} from {target_date}')
        print(f'  Re-run renderer.py to rebuild index.html from restored data')

    return True


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rollback', metavar='YYYY-MM-DD',
                   help='Restore data files from this snapshot date.')
    p.add_argument('--include-html', action='store_true',
                   help='With --rollback, also restore index.html '
                        '(use when the renderer is the regression).')
    args = p.parse_args()

    if args.rollback:
        sys.exit(0 if rollback(args.rollback, include_html=args.include_html) else 1)
    else:
        take_snapshot()
