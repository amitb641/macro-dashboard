#!/usr/bin/env python3
"""
Version Tracker — Records pipeline run metadata for audit trail.
Maintains data/pipeline_version.json with rolling history of the last 20 runs.
Each entry captures: timestamp, data freshness, validation status, git SHA, and key metrics.

Usage: python scripts/version_tracker.py
"""

import json, datetime, subprocess, sys, time
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
VERSION_FILE = DATA_DIR / 'pipeline_version.json'
METRICS_FILE = DATA_DIR / 'pipeline_metrics.json'  # structured metrics timeseries
RAW_FILE     = DATA_DIR / 'raw_data.json'
SIG_FILE     = DATA_DIR / 'signals.json'
VAL_FILE     = DATA_DIR / 'validation_report.json'
VQA_FILE     = DATA_DIR / 'visual_qa_report.json'
CEO_FILE     = DATA_DIR / 'ceo_grade_verdict.json'
HTML_FILE    = ROOT / 'index.html'

MAX_HISTORY  = 52  # Keep last 52 run records (one year of weekly runs)


def _git_sha():
    """Get current git SHA, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                capture_output=True, text=True, timeout=5, cwd=str(ROOT))
        return result.stdout.strip() if result.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def _git_branch():
    """Get current git branch name."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                capture_output=True, text=True, timeout=5, cwd=str(ROOT))
        return result.stdout.strip() if result.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def _extract_key_values(raw_data):
    """Extract key indicator values for the version record."""
    data = raw_data.get('data', {})
    values = {}

    # Unemployment
    unrate = data.get('unrate', [])
    if unrate:
        values['unemployment'] = {'date': unrate[0]['date'], 'value': unrate[0]['value']}

    # CPI
    cpi = data.get('cpi_all', [])
    if cpi:
        values['cpi_index'] = {'date': cpi[0]['date'], 'value': cpi[0]['value']}

    # Payrolls
    payems = data.get('payems', [])
    if payems:
        values['payrolls'] = {'date': payems[0]['date'], 'value': payems[0]['value']}

    # 10Y Treasury
    dgs10 = data.get('dgs10')
    if dgs10 and isinstance(dgs10, dict):
        values['treasury_10y'] = dgs10

    # Fed Funds
    ffr = data.get('ffr')
    if ffr and isinstance(ffr, dict):
        values['fed_funds'] = ffr

    return values


def record_run():
    """Record the current pipeline run in version history."""
    now = datetime.datetime.utcnow().isoformat() + 'Z'

    entry = {
        'run_at': now,
        'git_sha': _git_sha(),
        'git_branch': _git_branch(),
    }

    # Raw data metadata
    if RAW_FILE.exists():
        raw = json.loads(RAW_FILE.read_text())
        entry['collected_at'] = raw.get('collected_at', 'unknown')
        entry['series_count'] = raw.get('series_count', 0)
        entry['collector_errors'] = raw.get('error_count', 0)
        entry['key_values'] = _extract_key_values(raw)
    else:
        entry['collected_at'] = 'missing'

    # Signals metadata
    if SIG_FILE.exists():
        sig = json.loads(SIG_FILE.read_text())
        entry['risk_level'] = sig.get('risk_level', 'unknown')
        entry['alert_count'] = sig.get('alert_count', 0)

    # Validation metadata
    if VAL_FILE.exists():
        val = json.loads(VAL_FILE.read_text(encoding='utf-8'))
        entry['validation_status'] = val.get('status', 'unknown')
        entry['validation_summary'] = val.get('summary', {})
        # Count critical divergences for trending
        entry['validation_critical'] = sum(
            1 for p in val.get('passes', []) if p.get('severity') == 'critical'
        )
        entry['validation_warnings'] = sum(
            1 for p in val.get('passes', []) if p.get('severity') == 'warning'
        )
    else:
        entry['validation_status'] = 'not_run'
        entry['validation_critical'] = 0
        entry['validation_warnings'] = 0

    # Visual QA metrics
    if VQA_FILE.exists():
        try:
            vqa = json.loads(VQA_FILE.read_text(encoding='utf-8'))
            summary = vqa.get('summary', {})
            entry['visual_qa_passed']   = summary.get('passed', 0)
            entry['visual_qa_failed']   = summary.get('failed', 0)
            entry['visual_qa_critical'] = summary.get('critical', 0)
        except Exception:
            pass

    # CEO-grade verdict
    if CEO_FILE.exists():
        try:
            ceo = json.loads(CEO_FILE.read_text(encoding='utf-8'))
            entry['ceo_grade'] = ceo.get('overall', ceo.get('verdict', 'unknown'))
        except Exception:
            pass

    # HTML metadata
    if HTML_FILE.exists():
        entry['html_size'] = HTML_FILE.stat().st_size

    # Load existing history
    history = []
    if VERSION_FILE.exists():
        try:
            existing = json.loads(VERSION_FILE.read_text())
            history = existing.get('runs', [])
        except Exception:
            pass

    # Append and trim
    history.append(entry)
    history = history[-MAX_HISTORY:]

    # Compute delta from previous run
    if len(history) >= 2:
        prev = history[-2]
        curr = history[-1]

        changes = []
        prev_vals = prev.get('key_values', {})
        curr_vals = curr.get('key_values', {})

        for key in curr_vals:
            if key in prev_vals:
                old_v = prev_vals[key].get('value')
                new_v = curr_vals[key].get('value')
                if old_v is not None and new_v is not None and old_v != new_v:
                    changes.append({
                        'indicator': key,
                        'old': old_v,
                        'new': new_v,
                        'delta': round(new_v - old_v, 4) if isinstance(new_v, (int, float)) else None,
                    })

        if changes:
            entry['data_changes'] = changes

    # Write version file (full audit trail)
    output = {
        'schema_version': 2,
        'last_updated': now,
        'total_runs': len(history),
        'runs': history,
    }
    VERSION_FILE.write_text(json.dumps(output, indent=2), encoding='utf-8')

    # Write pipeline_metrics.json: lightweight timeseries for trending.
    # One row per run with validation/visual-QA counts, CEO grade, html size.
    metrics_entry = {
        'run_at':              now,
        'git_sha':             entry.get('git_sha', 'unknown'),
        'validation_status':   entry.get('validation_status', 'unknown'),
        'validation_critical': entry.get('validation_critical', 0),
        'validation_warnings': entry.get('validation_warnings', 0),
        'visual_qa_passed':    entry.get('visual_qa_passed', 0),
        'visual_qa_failed':    entry.get('visual_qa_failed', 0),
        'visual_qa_critical':  entry.get('visual_qa_critical', 0),
        'ceo_grade':           entry.get('ceo_grade', 'unknown'),
        'html_size':           entry.get('html_size', 0),
        'collector_errors':    entry.get('collector_errors', 0),
        'risk_level':          entry.get('risk_level', 'unknown'),
    }
    metrics_history = []
    if METRICS_FILE.exists():
        try:
            metrics_history = json.loads(METRICS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    metrics_history.append(metrics_entry)
    metrics_history = metrics_history[-MAX_HISTORY:]
    METRICS_FILE.write_text(json.dumps(metrics_history, indent=2), encoding='utf-8')

    print(f'[Version Tracker] Run #{len(history)} recorded at {now}')
    print(f'  Git: {entry["git_sha"]} ({entry["git_branch"]})')
    print(f'  Validation: {entry.get("validation_status", "n/a")} '
          f'({entry.get("validation_critical", 0)} critical, '
          f'{entry.get("validation_warnings", 0)} warnings)')
    print(f'  CEO grade: {entry.get("ceo_grade", "n/a")}')
    print(f'  Visual QA: {entry.get("visual_qa_passed", "?")}/{entry.get("visual_qa_failed", "?")}/{entry.get("visual_qa_critical", "?")} passed/failed/critical')
    if entry.get('data_changes'):
        print(f'  Data changes from last run:')
        for c in entry['data_changes']:
            print(f'    {c["indicator"]}: {c["old"]} -> {c["new"]} (delta={c["delta"]})')
    else:
        print(f'  No data value changes from last run')


if __name__ == '__main__':
    record_run()
