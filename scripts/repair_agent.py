#!/usr/bin/env python3
"""
Agent 10 — REPAIR AGENT (observer mode v1)

Sibling agent following the Agent 9 (earnings) pattern: runs off the
critical path, validator-gated, writes structured artifacts. Watches
validation_report.json after each pipeline run and surfaces findings
into a rolling log so accumulated drift can't sit unread for months.

CURRENT MODE: passive observer — reads, summarizes, logs. NO automated
fixes. By design. Per docs/SELF_VERIFICATION.md, this agent must run in
observer mode for ≥3 weeks before any fix-writing logic is added.

Outputs:
  - stdout: structured summary (visible in CI run logs)
  - data/repair_log.md: rolling append-only audit log of every run

Future iterations (gated on observation phase):
  - v2: post GitHub issue / commit comment with summary
  - v3: dispatch failure type → Claude API for fix proposal → draft PR
  - v4: auto-merge low-risk fix classes after re-fetch verification

Exit code: always 0 (observer mode never blocks the pipeline).
"""

import json, datetime, sys
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
RPT_FILE   = ROOT / 'data' / 'validation_report.json'
LOG_FILE   = ROOT / 'data' / 'repair_log.md'

# Sections of the validation report that contain findings lists.
_FINDING_SECTIONS = [
    ('Schema contract',      'schema_contract'),
    ('Collector errors',     'collector_errors'),
    ('Seed drift',           'seed_drift'),
    ('Internal consistency', 'internal_consistency'),
    ('Source verification',  'source_verification'),
    ('Staleness',            'staleness'),
    ('Shock tracker',        'shock_tracker'),
    ('Panel data',           'panel_data_consistency'),
    ('Metric consistency',   'metric_consistency'),
    ('Earnings verbatim',    'earnings_verbatim'),
    ('Visual QA',            'visual_qa'),
    ('Visual review',        'visual_review'),
]


def _findings_by_severity(findings):
    """Bucket a flat findings list into critical / warning / stale / skipped."""
    buckets = {'critical': [], 'warning': [], 'stale': [], 'skipped': []}
    for f in findings:
        if f.get('pass'):
            continue
        sev = f.get('severity', 'warning')
        if sev == 'divergence':
            sev = 'critical'
        if sev in buckets:
            buckets[sev].append(f)
        else:
            buckets['warning'].append(f)
    return buckets


def summarize(report):
    """Build a human-readable + machine-parseable summary of the report."""
    status = report.get('status', 'UNKNOWN')
    summary = report.get('summary', {})
    out_lines = []
    sections_summary = []

    for label, key in _FINDING_SECTIONS:
        section = report.get(key, [])
        if not isinstance(section, list):
            continue
        b = _findings_by_severity(section)
        n_crit = len(b['critical'])
        n_warn = len(b['warning'])
        n_stale = len(b['stale'])
        if n_crit + n_warn + n_stale == 0:
            continue  # All clean — skip in summary
        sections_summary.append((label, key, b, n_crit, n_warn, n_stale))

    out_lines.append(f'## Repair Agent — {report.get("validated_at", "")}')
    out_lines.append('')
    out_lines.append(f'- **Status**: {status}')
    out_lines.append(f'- **Total checks**: {summary.get("total_checks", 0)}')
    out_lines.append(f'- **Passed**: {summary.get("passed", 0)}')
    out_lines.append(f'- **Failed**: {summary.get("failed", 0)}')
    out_lines.append(f'- **Critical divergences**: {summary.get("critical_divergences", 0)}')
    out_lines.append('')

    if not sections_summary:
        out_lines.append('No findings to surface — pipeline is clean. ✅')
        return '\n'.join(out_lines)

    for label, key, b, nc, nw, ns in sections_summary:
        out_lines.append(f'### {label}')
        out_lines.append(f'_{nc} critical · {nw} warning · {ns} stale_')
        out_lines.append('')
        for f in b['critical'][:10]:
            out_lines.append(f'- 🔴 **{f.get("check", "?")}** — {f.get("note") or f.get("reason") or ""}')
        for f in b['warning'][:10]:
            out_lines.append(f'- ⚠️ **{f.get("check", "?")}** — {f.get("note") or f.get("reason") or ""}')
        for f in b['stale'][:5]:
            age = f.get('age_days', '?')
            limit = f.get('max_lag_days', '?')
            out_lines.append(f'- ⏰ **{f.get("check", "?")}** — {age}d old (limit {limit}d)')
        more = (nc + nw + ns) - min(nc, 10) - min(nw, 10) - min(ns, 5)
        if more > 0:
            out_lines.append(f'- _… and {more} more_')
        out_lines.append('')
    return '\n'.join(out_lines)


def append_log(summary_md):
    """Append the run summary to the rolling log. Cap the file at the most
    recent ~50 runs so it doesn't grow unbounded."""
    existing = LOG_FILE.read_text(encoding='utf-8') if LOG_FILE.exists() else ''
    new_text = summary_md + '\n\n---\n\n' + existing
    # Trim to ~50 entries by counting `## Repair Agent` headers
    parts = new_text.split('## Repair Agent —')
    if len(parts) > 51:  # 1 prefix + 50 entries
        parts = parts[:51]
        new_text = '## Repair Agent —'.join(parts)
    LOG_FILE.write_text(new_text, encoding='utf-8')


def main():
    print('[Agent 10 — Repair Agent (observer)] Starting...')

    if not RPT_FILE.exists():
        print(f'[Agent 10] No validation_report.json at {RPT_FILE} — '
              f'validator may not have run. Skipping.')
        return 0

    report = json.loads(RPT_FILE.read_text(encoding='utf-8'))
    summary_md = summarize(report)

    # Print to stdout — visible in CI run log
    print()
    print(summary_md)
    print()

    # Persist to rolling log
    append_log(summary_md)
    print(f'[Agent 10] Summary appended to {LOG_FILE.relative_to(ROOT)}')

    # Observer mode — never blocks pipeline.
    return 0


if __name__ == '__main__':
    sys.exit(main())
