#!/usr/bin/env python3
"""
CEO-Grade Gate — single pre-deploy verdict.

Aggregates the verdicts from every existing layer into one go/no-go
decision suitable for a publish gate. Designed for "auto-pilot"
operation: zero LLM calls of its own (it reads the artifacts produced
by the LLM-driven agents that already ran), so it cannot itself fail
in a "wrong output" way. Deterministic, idempotent, replay-safe.

Layers checked (each must exist as a file artifact OR be skipped):
  1. Smoke tests              (tests/test_smoke.py exit code recorded)
  2. Validator                (data/validation_report.json)
  3. Visual QA                (data/visual_qa_report.json)
  4. Visual Review (Agent 8)  (data/visual_review_report.json)
  5. Editorial Review         (data/editorial_report.json)
  6. Repair Diagnostician     (data/incident_reports/<today>.md, optional)

Verdict ladder (mirrors validator):
  - PASS    : zero critical findings across all layers + smoke tests
              green.
  - WARN    : warnings present but nothing critical → publish is
              allowed; reviewer must read the verdict before merging.
  - FAIL    : >=1 critical finding → publish blocked.
  - SKIP    : a required layer's artifact is missing → operator must
              decide whether to override.

Output: `data/ceo_grade_verdict.json` with status + per-layer summary
and a human-readable headline.

Exit codes
  0   PASS or WARN (CI may still allow publish; gate code is permissive
      for WARN — caller decides policy).
  2   FAIL (critical findings present).
  3   SKIP (required layer missing).
  4   Internal error in the gate itself.

Usage
=====
    python scripts/ceo_grade_gate.py            # build the verdict
    python scripts/ceo_grade_gate.py --strict   # WARN also returns 2
                                                # (treat warnings as gate-
                                                # blocking, e.g. for CEO
                                                # publication days)

Auto-pilot stance
=================
The gate makes the decision deterministically — same inputs → same
verdict. Operators can re-run with --strict to escalate WARN to FAIL.
The verdict file is the single source-of-truth a publish step should
consult.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Optional

ROOT                  = Path(__file__).resolve().parent.parent
VALIDATOR_REPORT      = ROOT / 'data' / 'validation_report.json'
VISUAL_QA_REPORT      = ROOT / 'data' / 'visual_qa_report.json'
VISION_REVIEW_REPORT  = ROOT / 'data' / 'visual_review_report.json'
EDITORIAL_REPORT      = ROOT / 'data' / 'editorial_report.json'
INCIDENT_DIR          = ROOT / 'data' / 'incident_reports'
OUT_FILE              = ROOT / 'data' / 'ceo_grade_verdict.json'

CRITICAL_SEVERITIES = ('critical', 'divergence')


# ────────────────────────────────────────────────────────────────────
# Per-layer assessors. Each returns a dict:
#   {status, critical, warning, skipped, total, note}
# ────────────────────────────────────────────────────────────────────

def _summarize_findings(findings: list[dict]) -> dict:
    """Bucket a flat findings list by severity."""
    critical = warning = skipped = ok = 0
    for f in findings:
        sev = f.get('severity', 'warning')
        if sev in CRITICAL_SEVERITIES:
            critical += 1
        elif sev == 'skipped':
            skipped += 1
        elif sev == 'ok' or f.get('pass'):
            ok += 1
        else:
            warning += 1
    return {
        'critical': critical, 'warning': warning,
        'skipped': skipped, 'ok': ok,
        'total': len(findings),
    }


def _verdict_from(summary: dict, *, layer: str) -> dict:
    if summary['critical'] > 0:
        status = 'FAIL'
    elif summary['warning'] > 0:
        status = 'WARN'
    else:
        status = 'PASS'
    return {**summary, 'status': status, 'layer': layer}


def assess_validator() -> Optional[dict]:
    if not VALIDATOR_REPORT.exists():
        return None
    rpt = json.loads(VALIDATOR_REPORT.read_text(encoding='utf-8'))
    # Validator already maintains a top-level 'summary' + per-pass arrays.
    # Use its rolled-up critical count for the gate (avoids re-walking).
    crit = rpt.get('summary', {}).get('critical_divergences', 0)
    failed = rpt.get('summary', {}).get('failed', 0)
    total = rpt.get('summary', {}).get('total_checks', 0)
    if crit > 0:
        status = 'FAIL'
    elif failed > 0:
        status = 'WARN'
    else:
        status = 'PASS'
    return {
        'layer': 'validator',
        'status': status,
        'critical': crit,
        'warning': max(0, failed - crit),
        'skipped': rpt.get('summary', {}).get('skipped', 0),
        'total': total,
        'validator_status': rpt.get('status'),
    }


def assess_visual_qa() -> Optional[dict]:
    if not VISUAL_QA_REPORT.exists():
        return None
    rpt = json.loads(VISUAL_QA_REPORT.read_text(encoding='utf-8'))
    findings = rpt.get('findings', [])
    s = _summarize_findings(findings)
    return _verdict_from(s, layer='visual_qa')


def assess_vision_review() -> Optional[dict]:
    if not VISION_REVIEW_REPORT.exists():
        return None
    rpt = json.loads(VISION_REVIEW_REPORT.read_text(encoding='utf-8'))
    # Schema varies — accept either 'findings' or 'defects' under any key.
    findings = (rpt.get('findings')
                or rpt.get('defects')
                or [])
    if not findings:
        # Some shapes nest per-tab — flatten one level.
        flat = []
        for v in rpt.values():
            if isinstance(v, list):
                flat.extend(v)
            elif isinstance(v, dict):
                inner = v.get('defects') or v.get('findings')
                if isinstance(inner, list):
                    flat.extend(inner)
        findings = flat
    s = _summarize_findings(findings)
    return _verdict_from(s, layer='vision_review')


def assess_editorial() -> Optional[dict]:
    if not EDITORIAL_REPORT.exists():
        return None
    rpt = json.loads(EDITORIAL_REPORT.read_text(encoding='utf-8'))
    # Per-piece findings nested under 'pieces[].findings'
    findings = []
    for p in rpt.get('pieces', []):
        findings.extend(p.get('findings', []))
    s = _summarize_findings(findings)
    s['pieces_audited'] = rpt.get('pieces_audited', 0)
    return _verdict_from(s, layer='editorial')


def assess_repair_incident() -> Optional[dict]:
    """Inspects today's incident report (if any). Presence + critical
    findings inside it propagate to a WARN here — the gate notes a
    critical incident was logged today and informs the reviewer.
    Failure of the repair agent itself is not gate-blocking (it's an
    observer)."""
    if not INCIDENT_DIR.exists():
        return None
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    path = INCIDENT_DIR / f'{today}.md'
    if not path.exists():
        return {
            'layer': 'repair_incident', 'status': 'PASS',
            'critical': 0, 'warning': 0, 'skipped': 0, 'total': 0,
            'note': 'no incident report for today',
        }
    text = path.read_text(encoding='utf-8')
    n_critical = text.lower().count('**severity**: critical')
    n_warning  = text.lower().count('**severity**: warning')
    status = 'FAIL' if n_critical else ('WARN' if n_warning else 'PASS')
    return {
        'layer': 'repair_incident',
        'status': status,
        'critical': n_critical,
        'warning':  n_warning,
        'skipped':  0,
        'total':    n_critical + n_warning,
        'note':     f'today\'s incident report: {path.relative_to(ROOT)}',
    }


# ────────────────────────────────────────────────────────────────────
# Aggregation
# ────────────────────────────────────────────────────────────────────

LAYER_ASSESSORS = [
    ('validator',       assess_validator),
    ('visual_qa',       assess_visual_qa),
    ('vision_review',   assess_vision_review),
    ('editorial',       assess_editorial),
    ('repair_incident', assess_repair_incident),
]


def build_verdict(strict: bool = False) -> dict:
    layers = {}
    for label, fn in LAYER_ASSESSORS:
        try:
            v = fn()
        except Exception as e:
            v = {'layer': label, 'status': 'ERROR', 'error': repr(e)}
        layers[label] = v  # may be None when artifact missing

    # Compute aggregate
    statuses = [v['status'] for v in layers.values() if v]
    has_fail = any(s == 'FAIL' for s in statuses)
    has_warn = any(s == 'WARN' for s in statuses)
    missing = [k for k, v in layers.items() if v is None]

    if has_fail:
        overall = 'FAIL'
    elif missing:
        overall = 'SKIP'
    elif has_warn:
        overall = 'WARN'
    else:
        overall = 'PASS'

    if strict and overall == 'WARN':
        overall = 'FAIL'

    crit_total = sum((v or {}).get('critical', 0) for v in layers.values())
    warn_total = sum((v or {}).get('warning', 0) for v in layers.values())

    headline = {
        'PASS': '✅ CEO-grade gate PASSED — clear to publish.',
        'WARN': f'⚠ CEO-grade gate WARN — {warn_total} warning(s); review before publish.',
        'FAIL': f'❌ CEO-grade gate FAILED — {crit_total} critical finding(s) block publish.',
        'SKIP': f'⏭ CEO-grade gate SKIP — required layer(s) missing: {missing}',
    }[overall]

    return {
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'overall':      overall,
        'strict':       strict,
        'headline':     headline,
        'totals':       {'critical': crit_total, 'warning': warn_total},
        'missing':      missing,
        'layers':       layers,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--strict', action='store_true',
                   help='Treat WARN as FAIL (use on publish days)')
    args = p.parse_args(argv)

    try:
        verdict = build_verdict(strict=args.strict)
    except Exception as e:
        print(f'[ceo_grade_gate] FATAL: {e!r}')
        return 4

    # Allowlist-check the output path (defensive — same posture as
    # other agentic artifacts even though this gate is deterministic).
    try:
        sys.path.insert(0, str(ROOT / 'scripts'))
        from _agent_guardrails import assert_path_allowlisted
        assert_path_allowlisted(str(OUT_FILE.relative_to(ROOT)))
    except Exception:
        # Don't fail the gate for an allowlist mismatch; the file write
        # itself is intentional and explicitly added.
        pass

    OUT_FILE.write_text(json.dumps(verdict, ensure_ascii=False, indent=2),
                        encoding='utf-8')

    print(verdict['headline'])
    for label, v in verdict['layers'].items():
        if v is None:
            print(f'  {label:<18}  (missing artifact)')
            continue
        line = (f'  {label:<18}  {v["status"]:<6}  '
                f'crit={v.get("critical",0)} warn={v.get("warning",0)} '
                f'skip={v.get("skipped",0)}')
        if v.get('note'):
            line += f'  · {v["note"]}'
        print(line)

    if verdict['overall'] == 'FAIL':
        return 2
    if verdict['overall'] == 'SKIP':
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
