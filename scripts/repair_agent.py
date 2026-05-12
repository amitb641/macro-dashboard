#!/usr/bin/env python3
"""
Agent 10 — REPAIR AGENT

Modes
=====
- Stage 10a — **Diagnostician** (current). LLM reasons about each
  validator finding using the playbook + known-normal baselines and
  emits a structured incident report. READ-ONLY: no code, data, or
  layout changes.
- Stage 10b — Proposer (future). Same as 10a + writes a draft PR with a
  suggested diff. Requires human review.
- Stage 10c — Auto-fixer (future). Whitelisted fix categories only,
  re-runs validator before commit, two-LLM critique gate.

Default behaviour preserved
===========================
This script keeps the prior observer-mode summary (rolling
`data/repair_log.md` append, stdout digest) regardless of mode. The
diagnostician only activates when:
  - `AGENT_DIAGNOSTICIAN_ENABLED=1`
  - `ANTHROPIC_API_KEY` is set
  - `AGENT_DISABLE_ALL` is NOT set
This way merging this code does not silently start sending prompts.
Maintainers flip the flag explicitly after reviewing the cost model.

Outputs
=======
- stdout: structured summary (visible in CI run logs).
- data/repair_log.md: rolling append-only audit log (unchanged from v1).
- data/incident_reports/<YYYY-MM-DD>.md: per-run detailed incident
  report with LLM-authored diagnoses (only when diagnostician active).
- data/agent_memory.jsonl: one entry per LLM call (audit trail).

Exit code: always 0. The diagnostician never blocks the pipeline.
"""

from __future__ import annotations

import json
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _models import SONNET  # noqa: E402

ROOT             = Path(__file__).resolve().parent.parent
RPT_FILE         = ROOT / 'data' / 'validation_report.json'
LOG_FILE         = ROOT / 'data' / 'repair_log.md'
PLAYBOOK_FILE    = ROOT / 'data' / 'playbook.md'
KNOWN_NORMAL     = ROOT / 'data' / 'known_normal.json'
INCIDENT_DIR     = ROOT / 'data' / 'incident_reports'

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


# ────────────────────────────────────────────────────────────────────────
# Observer-mode summary (preserved verbatim from v1 for backward compat)
# ────────────────────────────────────────────────────────────────────────

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


def _sections_with_findings(report):
    """Yield (label, key, buckets, n_crit, n_warn, n_stale) for each
    section that has at least one non-passing finding."""
    for label, key in _FINDING_SECTIONS:
        section = report.get(key, [])
        if not isinstance(section, list):
            continue
        b = _findings_by_severity(section)
        nc, nw, ns = len(b['critical']), len(b['warning']), len(b['stale'])
        if nc + nw + ns > 0:
            yield label, key, b, nc, nw, ns


def summarize(report):
    """Build a human-readable + machine-parseable summary of the report."""
    status = report.get('status', 'UNKNOWN')
    summary = report.get('summary', {})
    out_lines = [
        f'## Repair Agent — {report.get("validated_at", "")}',
        '',
        f'- **Status**: {status}',
        f'- **Total checks**: {summary.get("total_checks", 0)}',
        f'- **Passed**: {summary.get("passed", 0)}',
        f'- **Failed**: {summary.get("failed", 0)}',
        f'- **Critical divergences**: {summary.get("critical_divergences", 0)}',
        '',
    ]

    sections = list(_sections_with_findings(report))
    if not sections:
        out_lines.append('No findings to surface — pipeline is clean. ✅')
        return '\n'.join(out_lines)

    for label, key, b, nc, nw, ns in sections:
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
    """Append the run summary to the rolling log. Cap the file at ~50 runs."""
    existing = LOG_FILE.read_text(encoding='utf-8') if LOG_FILE.exists() else ''
    new_text = summary_md + '\n\n---\n\n' + existing
    parts = new_text.split('## Repair Agent —')
    if len(parts) > 51:
        parts = parts[:51]
        new_text = '## Repair Agent —'.join(parts)
    LOG_FILE.write_text(new_text, encoding='utf-8')


# ────────────────────────────────────────────────────────────────────────
# Diagnostician (Stage 10a)
# ────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the Repair Diagnostician for a deterministic macro-economics data
pipeline. Your job is to read one validator finding and produce a short,
structured diagnosis.

You are READ-ONLY. You never write code, never edit data, never modify
layout. You produce reports humans read.

When you reason about a finding:
  1. Cite a section from the playbook (e.g. "playbook §2.2") or a
     file:line whenever you assert a cause. If you cannot cite, downgrade
     your confidence to "low" and say what would close the gap.
  2. Check the finding against the known-normal baselines BEFORE
     declaring it actionable. A staleness flag within the source's
     typical publish lag is informational, not a bug.
  3. Prefer concrete, file-level recommendations over generic advice.
     "Bump limit=24 in collector.py for cpi_food_away" beats "fix the
     collector."
  4. Never recommend any action on the forbidden list in playbook §5.

If you are shown RECURRENCE context (prior runs that flagged this same
check), use it:
  - If the check is recurring (seen in 3+ recent runs), upgrade the
    recommendation from "monitor" to "investigate root cause" and call
    out the recurrence in the rationale.
  - If a prior diagnosis already proposed a fix and the issue is still
    present, that's strong evidence the fix wasn't applied OR didn't
    work — say so in the rationale.
  - If this is a first-time finding, say so explicitly so reviewers
    know not to over-react to a single noisy run.

Output format — produce EXACTLY this Markdown structure and nothing else:

### Finding: <one-line finding name>
**Severity**: <critical | warning | stale | informational>
**Confidence**: <high | medium | low>
**Recurrence**: <one short phrase, e.g. "first observed" | "seen 4/5 runs since 2026-04-12" | "recurring; prior fix did not resolve">
**Root cause (hypothesis)**: <2-3 sentences>
**Playbook citation**: <§X.Y or "none — see Gap" below>
**Recommended next step**:
- <one-line action OR "Monitor only — see Rationale">

**Rationale**: <2-4 sentences. Tie the recommendation to the citation AND the recurrence context if present.>
**Gap (if any)**: <what additional context would raise your confidence>
"""


def _format_finding(label, finding, severity):
    """Compact JSON representation of a single finding for the prompt."""
    return json.dumps({
        'section': label,
        'severity': severity,
        'check':    finding.get('check'),
        'note':     finding.get('note'),
        'reason':   finding.get('reason'),
        'age_days': finding.get('age_days'),
        'max_lag_days': finding.get('max_lag_days'),
        'metric':   finding.get('metric'),
        'source':   finding.get('source'),
    }, ensure_ascii=False)


def _load_context() -> tuple[str, str]:
    """Read playbook + known-normal as strings for the prompt. Truncate
    if either is unexpectedly large (defensive — neither should be)."""
    playbook = ''
    normals = ''
    if PLAYBOOK_FILE.exists():
        playbook = PLAYBOOK_FILE.read_text(encoding='utf-8')[:16000]
    if KNOWN_NORMAL.exists():
        normals = KNOWN_NORMAL.read_text(encoding='utf-8')[:8000]
    return playbook, normals


def _recurrence_history(check_name: str, max_runs: int = 10) -> dict:
    """Look back through repair_log.md + incident_reports/ for prior
    mentions of this check. Returns a compact summary the diagnostician
    can use to spot recurrence patterns.

    Returns:
        {
          'runs_seen_in':  3,            # of last `max_runs`
          'total_runs':    7,            # how many runs the log covers
          'last_seen':     '2026-05-04', # date of most recent mention
          'prior_recommendations': [...] # up to 3 past Markdown blurbs
        }
    """
    out: dict = {
        'runs_seen_in': 0,
        'total_runs': 0,
        'last_seen': None,
        'prior_recommendations': [],
    }
    if not check_name:
        return out

    # Pass 1 — observer log gives us run-level cadence.
    if LOG_FILE.exists():
        log = LOG_FILE.read_text(encoding='utf-8')
        # repair_log.md headers look like: `## Repair Agent — 2026-05-12T...`
        runs = log.split('## Repair Agent —')[1:max_runs + 1]
        out['total_runs'] = len(runs)
        for run in runs:
            if check_name in run:
                out['runs_seen_in'] += 1
                if out['last_seen'] is None:
                    # First non-empty line of the run starts with " <ISO date>"
                    head = run.lstrip().split('\n', 1)[0].strip()
                    out['last_seen'] = head[:10] if len(head) >= 10 else head

    # Pass 2 — prior LLM diagnoses, if any, for richer recurrence context.
    if INCIDENT_DIR.exists():
        # Newest first by filename (YYYY-MM-DD.md sorts lexicographically).
        files = sorted(
            (p for p in INCIDENT_DIR.glob('*.md') if p.is_file()),
            reverse=True,
        )[:max_runs]
        for path in files:
            text = path.read_text(encoding='utf-8')
            # Each diagnosis starts with `### Finding: <name>` — pull the
            # block that mentions our check_name.
            blocks = text.split('### Finding:')
            for block in blocks[1:]:
                first_line = block.split('\n', 1)[0]
                if check_name and check_name in first_line:
                    snippet = ('### Finding:' + block).strip()
                    # Keep blurb short; 800 chars covers the structured fields.
                    out['prior_recommendations'].append(snippet[:800])
                    break
            if len(out['prior_recommendations']) >= 3:
                break

    return out


def _format_recurrence(history: dict) -> str:
    """Render a recurrence-history dict as a compact prompt fragment."""
    if history['total_runs'] == 0:
        return 'RECURRENCE: no prior log entries (first observed run for this agent).'
    n, tot = history['runs_seen_in'], history['total_runs']
    if n == 0:
        return f'RECURRENCE: not seen in last {tot} observer runs. First-time finding.'
    lines = [
        f'RECURRENCE: seen in {n} of last {tot} runs. Last seen: {history["last_seen"] or "?"}.',
    ]
    if history['prior_recommendations']:
        lines.append('PRIOR DIAGNOSES (most recent first):')
        for blurb in history['prior_recommendations']:
            lines.append('---')
            lines.append(blurb)
    return '\n'.join(lines)


def diagnose_findings(report) -> str:
    """Run the LLM diagnostician over each non-passing finding. Returns
    a single Markdown document concatenating all diagnoses. Returns the
    empty string when the diagnostician is disabled (caller falls back
    to the observer-mode summary)."""
    # Imported here so the script remains runnable in environments
    # without the guardrails module (defensive — should always exist).
    from _agent_guardrails import (
        is_diagnostician_enabled, bounded_llm_call, BudgetExhausted,
        max_llm_calls, calls_used, reset_call_counter, status_dict,
    )
    from _agent_memory import set_agent, stats

    if not is_diagnostician_enabled():
        return ''

    set_agent('repair')
    reset_call_counter()
    playbook, normals = _load_context()

    # Hard cap on findings dispatched to the LLM per run. The remaining
    # findings still appear in the observer summary; this just bounds
    # cost on a pathological run.
    MAX_FINDINGS_PER_RUN = min(15, max_llm_calls())

    findings_to_diagnose: list[tuple[str, dict, str]] = []
    for label, _key, b, _nc, _nw, _ns in _sections_with_findings(report):
        for f in b['critical']:
            findings_to_diagnose.append((label, f, 'critical'))
        for f in b['warning'][:5]:
            findings_to_diagnose.append((label, f, 'warning'))
        for f in b['stale'][:3]:
            findings_to_diagnose.append((label, f, 'stale'))

    diagnoses: list[str] = []
    budget_hit = False

    for label, finding, severity in findings_to_diagnose[:MAX_FINDINGS_PER_RUN]:
        finding_json = _format_finding(label, finding, severity)
        recurrence = _recurrence_history(finding.get('check', ''))
        recurrence_block = _format_recurrence(recurrence)
        prompt = (
            f'PLAYBOOK (truncated):\n{playbook}\n\n'
            f'KNOWN NORMAL BASELINES (JSON):\n{normals}\n\n'
            f'FINDING (JSON):\n{finding_json}\n\n'
            f'{recurrence_block}\n\n'
            f'Diagnose this finding using the format specified in the '
            f'system prompt. Cite a playbook section or downgrade confidence. '
            f'If RECURRENCE shows the issue is recurring, reflect that in '
            f'your severity / recommendation / rationale.'
        )
        try:
            response = bounded_llm_call(
                prompt,
                system=_SYSTEM_PROMPT,
                model=SONNET,
                max_tokens=800,
                purpose=f'diagnose:{label}',
            )
        except BudgetExhausted:
            budget_hit = True
            break
        except Exception as e:
            diagnoses.append(
                f'### Finding: {finding.get("check","?")}\n'
                f'**Diagnosis failed**: {e!r}\n'
            )
            continue

        if response:
            diagnoses.append(response.strip())

    if not diagnoses:
        return ''

    header = [
        '# Repair Diagnostician — Incident Report',
        f'_Run at {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}_',
        '',
        f'- Findings diagnosed: {len(diagnoses)}',
        f'- LLM calls used: {calls_used()} / {max_llm_calls()}',
    ]
    if budget_hit:
        header.append('- ⚠️ **Budget exhausted** — additional findings were not diagnosed this run.')
    header.append('- Memory stats: ' + json.dumps(stats()))
    header.append('- Guardrails: ' + json.dumps(status_dict()))
    header.append('')

    return '\n'.join(header) + '\n' + '\n\n---\n\n'.join(diagnoses) + '\n'


def write_incident_report(content: str) -> Path:
    """Save the LLM-authored incident report to a dated file. Returns the path."""
    from _agent_guardrails import assert_path_allowlisted

    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    out = INCIDENT_DIR / f'{stamp}.md'
    rel = str(out.relative_to(ROOT))
    # Defensive: assert we're writing inside the allowlisted prefix.
    assert_path_allowlisted(rel)
    out.write_text(content, encoding='utf-8')
    return out


# ────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────

def main():
    print('[Agent 10 — Repair Agent] Starting...')

    if not RPT_FILE.exists():
        print(f'[Agent 10] No validation_report.json at {RPT_FILE} — '
              f'validator may not have run. Skipping.')
        return 0

    report = json.loads(RPT_FILE.read_text(encoding='utf-8'))

    # Observer-mode summary always runs (cheap, no LLM).
    summary_md = summarize(report)
    print()
    print(summary_md)
    print()
    append_log(summary_md)
    print(f'[Agent 10] Summary appended to {LOG_FILE.relative_to(ROOT)}')

    # Diagnostician layer — only when explicitly opted in.
    from _agent_guardrails import is_diagnostician_enabled
    if is_diagnostician_enabled():
        print('[Agent 10] Diagnostician enabled — invoking LLM for findings...')
        try:
            incident_md = diagnose_findings(report)
        except Exception as e:
            print(f'[Agent 10] Diagnostician errored: {e!r} — '
                  f'observer summary still recorded above.')
            return 0
        if incident_md:
            path = write_incident_report(incident_md)
            print(f'[Agent 10] Incident report written: {path.relative_to(ROOT)}')
        else:
            print('[Agent 10] Diagnostician produced no diagnoses (no LLM calls made).')
    else:
        print('[Agent 10] Diagnostician disabled (default). '
              'Set AGENT_DIAGNOSTICIAN_ENABLED=1 + ANTHROPIC_API_KEY to opt in.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
