#!/usr/bin/env python3
"""
History Archive — long-term lightweight record of every pipeline run.

Unlike snapshots/ (which keep full raw_data.json for rollback), the history
archive intentionally omits raw_data.json (~2 MB) to keep the repository lean.
Each run entry is ~162 KB; a full year of weekly runs adds ~8.4 MB to git.

Structure:
  data/history/
    YYYY-MM-DD/
      state.json             — Tier-1 chart payload  (~41 KB)
      signals.json           — analyzer scored signals (~5.5 KB)
      validation_report.json — validator verdict      (~108 KB)
      editorial_report.json  — editorial audit        (~5.6 KB, if present)
      ceo_grade_verdict.json — go/no-go gate verdict  (~1.3 KB, if present)
      meta.json              — run metadata           (~1 KB)

Usage:
  python scripts/history_archive.py           # archive current run
  python scripts/history_archive.py --list    # list archived runs
"""

import json, os, shutil, sys, datetime
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
HIST_DIR     = DATA_DIR / 'history'

# Source files — raw_data.json intentionally excluded (too large for git history)
_ARCHIVE_FILES = [
    DATA_DIR / 'state.json',
    DATA_DIR / 'signals.json',
    DATA_DIR / 'validation_report.json',
    DATA_DIR / 'editorial_report.json',
    DATA_DIR / 'ceo_grade_verdict.json',
]


def archive_run() -> bool:
    """Write today's pipeline artifacts to data/history/YYYY-MM-DD/."""
    HIST_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    entry_path = HIST_DIR / ts

    if entry_path.exists():
        print(f'[History] Entry already exists for {ts}, skipping')
        return True

    entry_path.mkdir()

    copied, missing, sizes = [], [], {}
    for src in _ARCHIVE_FILES:
        if src.exists():
            dest = entry_path / src.name
            shutil.copy2(src, dest)
            copied.append(src.name)
            sizes[src.name] = src.stat().st_size
        else:
            missing.append(src.name)

    if not copied:
        print(f'[History] No source files found — nothing archived')
        entry_path.rmdir()
        return False

    # Build meta.json — run provenance snapshot
    meta: dict = {
        'archive_date': ts,
        'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'files': copied,
        'sizes_bytes': sizes,
        'total_kb': round(sum(sizes.values()) / 1024, 1),
    }

    # Pull key summary values from state.json if available.
    # KPIS is a list of card dicts: [{lbl, val, metric, ...}, ...].
    state_path = entry_path / 'state.json'
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            kpis_list = state.get('KPIS', [])
            if isinstance(kpis_list, list) and kpis_list:
                # Use lbl as key (unique per card)
                meta['kpi_snapshot'] = {
                    card['lbl']: card['val']
                    for card in kpis_list
                    if 'lbl' in card and 'val' in card
                }
        except Exception:
            pass

    # Pull overall validation status
    val_path = entry_path / 'validation_report.json'
    if val_path.exists():
        try:
            val = json.loads(val_path.read_text(encoding='utf-8'))
            meta['validation_status'] = val.get('status', 'unknown')
        except Exception:
            pass

    # Pull CEO-grade gate verdict ('overall' key in ceo_grade_verdict.json)
    ceo_path = entry_path / 'ceo_grade_verdict.json'
    if ceo_path.exists():
        try:
            ceo = json.loads(ceo_path.read_text(encoding='utf-8'))
            # 'overall' is the primary verdict key; 'verdict' kept for back-compat
            meta['ceo_grade_verdict'] = ceo.get('overall', ceo.get('verdict', 'unknown'))
        except Exception:
            pass

    (entry_path / 'meta.json').write_text(json.dumps(meta, indent=2))

    total_kb = meta['total_kb']
    if missing:
        print(f'[History] Archived {ts}: {len(copied)} file(s), {total_kb:.0f} KB '
              f'(missing: {", ".join(missing)})')
    else:
        print(f'[History] Archived {ts}: {len(copied)} file(s), {total_kb:.0f} KB')

    # Count total entries for visibility
    all_entries = sorted([d.name for d in HIST_DIR.iterdir() if d.is_dir()])
    print(f'[History] {len(all_entries)} total run(s) archived '
          f'(oldest: {all_entries[0]}, newest: {all_entries[-1]})')
    return True


def list_runs() -> None:
    """Print a summary table of all archived runs."""
    if not HIST_DIR.exists():
        print('[History] No archive directory found — no runs archived yet')
        return

    entries = sorted([d for d in HIST_DIR.iterdir() if d.is_dir()], reverse=True)
    if not entries:
        print('[History] No archived runs found')
        return

    print(f'[History] {len(entries)} archived run(s):\n')
    print(f'  {"Date":<12}  {"KB":>6}  {"Validation":<12}  {"CEO Grade":<10}  Key KPIs')
    print(f'  {"-"*12}  {"-"*6}  {"-"*12}  {"-"*10}  {"-"*40}')

    for entry in entries:
        meta_path = entry / 'meta.json'
        if not meta_path.exists():
            print(f'  {entry.name:<12}  (no meta.json)')
            continue
        try:
            meta = json.loads(meta_path.read_text())
            kb = meta.get('total_kb', '?')
            val = meta.get('validation_status', '?')[:12]
            ceo = meta.get('ceo_grade_verdict', '?')[:10]
            kpis = meta.get('kpi_snapshot', {})
            kpi_str = ', '.join(
                f'{k}={v}' for k, v in list(kpis.items())[:3]
            ) if kpis else '—'
            print(f'  {entry.name:<12}  {kb:>6}  {val:<12}  {ceo:<10}  {kpi_str}')
        except Exception as e:
            print(f'  {entry.name:<12}  (error reading meta: {e})')


if __name__ == '__main__':
    if '--list' in sys.argv:
        list_runs()
    else:
        sys.exit(0 if archive_run() else 1)
