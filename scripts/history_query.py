#!/usr/bin/env python3
"""
History Query — answers "how did the dashboard look N weeks ago?"

Reads from data/history/ (lightweight, no raw_data.json) for narrative queries
and from data/snapshots/ (full, includes raw_data.json) for rollback guidance.

Usage:
  python scripts/history_query.py --list
  python scripts/history_query.py --date 2026-04-17
  python scripts/history_query.py --weeks 4
  python scripts/history_query.py --weeks 4 --diff

Options:
  --list            Print a table of all archived runs with key KPIs
  --date YYYY-MM-DD Show full state for a specific run date
  --weeks N         Show full state for the run closest to N weeks ago
  --diff            (with --weeks or --date) Compare that run vs. today
  --kpis-only       Suppress non-KPI sections (signals, validation)
  --json            Output raw JSON instead of formatted text
"""

import json, sys, datetime, textwrap
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / 'data'
HIST_DIR = DATA_DIR / 'history'
SNAP_DIR = DATA_DIR / 'snapshots'


# ── Helpers ─────────────────────────────────────────────────────────────────

def _all_entries() -> list[Path]:
    if not HIST_DIR.exists():
        return []
    return sorted([d for d in HIST_DIR.iterdir() if d.is_dir()], reverse=True)


def _nearest(target_date: datetime.date) -> Path | None:
    entries = _all_entries()
    if not entries:
        return None
    return min(
        entries,
        key=lambda e: abs((datetime.date.fromisoformat(e.name) - target_date).days)
    )


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'  [warn] Failed to read {path.name}: {e}', file=sys.stderr)
        return None


def _fmt_kpis(kpis: dict, indent: str = '  ') -> str:
    """Format a kpi_snapshot dict: keys are card lbl strings, values are val strings."""
    if not kpis:
        return f'{indent}(no KPIs available)'
    lines = []
    for lbl, val in kpis.items():
        lines.append(f'{indent}{lbl:<30} {val}')
    return '\n'.join(lines)


def _fmt_signals(signals: list | dict | None, indent: str = '  ') -> str:
    if not signals:
        return f'{indent}(no signals data)'
    if isinstance(signals, dict):
        signals = signals.get('signals', [])
    if not signals:
        return f'{indent}(no flagged signals)'
    lines = []
    for s in signals[:15]:  # cap to 15 most recent/significant
        name  = s.get('name', s.get('series', '?'))
        score = s.get('score', s.get('signal', '?'))
        label = s.get('label', s.get('direction', ''))
        lines.append(f'{indent}{name:<35} score={score}  {label}')
    if len(signals) > 15:
        lines.append(f'{indent}... and {len(signals) - 15} more')
    return '\n'.join(lines)


def _kpi_diff(old_kpis: dict, new_kpis: dict, indent: str = '  ') -> str:
    """Diff two kpi_snapshot dicts (both keyed by lbl strings)."""
    if not old_kpis or not new_kpis:
        return f'{indent}(cannot diff — KPI data missing for one or both dates)'
    all_keys = sorted(set(old_kpis) | set(new_kpis))
    lines = []
    for k in all_keys:
        old_v = old_kpis.get(k, 'n/a')
        new_v = new_kpis.get(k, 'n/a')
        marker = '' if old_v == new_v else '  ← changed'
        lines.append(f'{indent}{k:<30}  then={old_v}  now={new_v}{marker}')
    return '\n'.join(lines)


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_list(as_json: bool = False) -> None:
    entries = _all_entries()
    if not entries:
        print('No archived runs found. Run history_archive.py to create the first entry.')
        return

    if as_json:
        rows = []
        for e in entries:
            meta = _load_json(e / 'meta.json') or {}
            rows.append({
                'date': e.name,
                'total_kb': meta.get('total_kb'),
                'validation_status': meta.get('validation_status'),
                'ceo_grade_verdict': meta.get('ceo_grade_verdict'),
                'kpi_snapshot': meta.get('kpi_snapshot', {}),
            })
        print(json.dumps(rows, indent=2))
        return

    print(f'\nMacro Dashboard — History Archive ({len(entries)} runs)\n')
    print(f'  {"Date":<12}  {"KB":>6}  {"Validation":<12}  {"CEO":<8}  Key KPIs')
    print(f'  {"-"*12}  {"-"*6}  {"-"*12}  {"-"*8}  {"-"*45}')
    for e in entries:
        meta = _load_json(e / 'meta.json') or {}
        kb   = f"{meta.get('total_kb', '?')}"
        val  = meta.get('validation_status', '?')[:12]
        ceo  = meta.get('ceo_grade_verdict', '?')[:8]
        kpis = meta.get('kpi_snapshot', {})
        # Keys are lbl strings (e.g. "Jobs Apr'26") — truncate for table display
        kpi_str = '  '.join(
            f"{k.split(' ')[0]}={v}"  # use first word of lbl for brevity
            for k, v in list(kpis.items())[:3]
        ) if kpis else '—'
        print(f'  {e.name:<12}  {kb:>6}  {val:<12}  {ceo:<8}  {kpi_str}')

    print(f'\n  Snapshots with raw_data.json for full rollback: data/snapshots/')
    snaps = sorted([d.name for d in SNAP_DIR.iterdir() if d.is_dir()]) if SNAP_DIR.exists() else []
    if snaps:
        print(f'  ({len(snaps)} rollback snapshots: {snaps[0]} -> {snaps[-1]})')


def cmd_show(entry_path: Path, as_json: bool = False, kpis_only: bool = False) -> None:
    meta    = _load_json(entry_path / 'meta.json') or {}
    state   = _load_json(entry_path / 'state.json') or {}
    signals = _load_json(entry_path / 'signals.json')
    val     = _load_json(entry_path / 'validation_report.json') or {}
    ceo     = _load_json(entry_path / 'ceo_grade_verdict.json') or {}

    if as_json:
        raw_kpis = state.get('KPIS')
        kpis_out = (
            {card['lbl']: card['val'] for card in raw_kpis
             if 'lbl' in card and 'val' in card}
            if isinstance(raw_kpis, list) else meta.get('kpi_snapshot', {})
        )
        print(json.dumps({
            'date': entry_path.name,
            'meta': meta,
            'kpis': kpis_out,
            'validation': {'status': val.get('status'), 'summary': val.get('summary')},
            'ceo_grade': ceo.get('overall', ceo.get('verdict')),
        }, indent=2))
        return

    date_str = entry_path.name
    val_status = val.get('status', meta.get('validation_status', '?'))
    ceo_verdict = ceo.get('overall', ceo.get('verdict', meta.get('ceo_grade_verdict', '?')))

    print(f'\n{"=" * 60}')
    print(f'  Macro Dashboard Snapshot — {date_str}')
    print(f'  Validation: {val_status}   CEO grade: {ceo_verdict}')
    print(f'{"=" * 60}\n')

    # KPIs — KPIS in state.json is a list; meta kpi_snapshot is lbl->val dict
    raw_kpis = state.get('KPIS')
    if isinstance(raw_kpis, list) and raw_kpis:
        kpis = {card['lbl']: card['val'] for card in raw_kpis
                if 'lbl' in card and 'val' in card}
    else:
        kpis = meta.get('kpi_snapshot', {})
    print('  KEY ECONOMIC INDICATORS')
    print('  ' + '-' * 40)
    print(_fmt_kpis(kpis))
    print()

    if kpis_only:
        return

    # Signals
    print('  SCORED SIGNALS')
    print('  ' + '-' * 40)
    print(_fmt_signals(signals))
    print()

    # Validation summary
    val_summary = val.get('summary', {})
    if val_summary:
        print('  VALIDATION SUMMARY')
        print('  ' + '-' * 40)
        for k, v in val_summary.items():
            print(f'  {k:<30} {v}')
        print()

    # Commentary (AI briefing if present)
    macro_state = state.get('MACRO_STATE', {})
    commentary = macro_state.get('commentary', '') if isinstance(macro_state, dict) else ''
    if commentary:
        print('  AI BRIEFING COMMENTARY (excerpt)')
        print('  ' + '-' * 40)
        wrapped = textwrap.fill(commentary[:800], width=72,
                                initial_indent='  ', subsequent_indent='  ')
        print(wrapped)
        if len(commentary) > 800:
            print('  ... [truncated]')
        print()


def cmd_diff(then_path: Path, as_json: bool = False) -> None:
    """Compare then_path run against the most recent entry."""
    entries = _all_entries()
    if not entries or entries[0].name == then_path.name:
        print('Nothing to diff — only one entry or requested date is the latest.')
        return

    now_path = entries[0]  # most recent run

    then_meta  = _load_json(then_path / 'meta.json') or {}
    now_meta   = _load_json(now_path / 'meta.json') or {}
    then_state = _load_json(then_path / 'state.json') or {}
    now_state  = _load_json(now_path / 'state.json') or {}

    def _extract_kpis(state: dict, meta: dict) -> dict:
        raw = state.get('KPIS')
        if isinstance(raw, list) and raw:
            return {card['lbl']: card['val'] for card in raw
                    if 'lbl' in card and 'val' in card}
        return meta.get('kpi_snapshot', {})

    then_kpis = _extract_kpis(then_state, then_meta)
    now_kpis  = _extract_kpis(now_state, now_meta)

    if as_json:
        print(json.dumps({
            'then': then_path.name, 'now': now_path.name,
            'then_kpis': then_kpis, 'now_kpis': now_kpis,
        }, indent=2))
        return

    print(f'\n{"=" * 60}')
    print(f'  Macro Dashboard — KPI Diff')
    print(f'  Then: {then_path.name}   ->   Now: {now_path.name}')
    print(f'{"=" * 60}\n')
    print(_kpi_diff(then_kpis, now_kpis))
    print()


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]
    as_json   = '--json'      in args
    kpis_only = '--kpis-only' in args
    do_diff   = '--diff'      in args
    args = [a for a in args if a not in ('--json', '--kpis-only', '--diff')]

    if not args or '--list' in args:
        cmd_list(as_json=as_json)
        return 0

    target_path: Path | None = None

    if '--date' in args:
        idx = args.index('--date')
        if idx + 1 >= len(args):
            print('Error: --date requires a YYYY-MM-DD argument')
            return 1
        date_str = args[idx + 1]
        target_path = HIST_DIR / date_str
        if not target_path.exists():
            nearest = _nearest(datetime.date.fromisoformat(date_str))
            if nearest:
                print(f'No entry for {date_str} — showing nearest: {nearest.name}')
                target_path = nearest
            else:
                print(f'No archived runs found for {date_str} (archive is empty).')
                return 1

    elif '--weeks' in args:
        idx = args.index('--weeks')
        if idx + 1 >= len(args):
            print('Error: --weeks requires a number')
            return 1
        try:
            n_weeks = int(args[idx + 1])
        except ValueError:
            print('Error: --weeks argument must be an integer')
            return 1
        target_date = datetime.date.today() - datetime.timedelta(weeks=n_weeks)
        target_path = _nearest(target_date)
        if target_path is None:
            print('No archived runs found.')
            return 1
        actual_days = abs((datetime.date.fromisoformat(target_path.name) - target_date).days)
        print(f'Requested {n_weeks} weeks ago ({target_date})'
              f' → nearest entry: {target_path.name} ({actual_days}d off)')

    else:
        print(__doc__)
        return 0

    if do_diff:
        cmd_diff(target_path, as_json=as_json)
    else:
        cmd_show(target_path, as_json=as_json, kpis_only=kpis_only)

    return 0


if __name__ == '__main__':
    sys.exit(main())
