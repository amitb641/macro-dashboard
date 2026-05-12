#!/usr/bin/env python3
"""
Editorial Review — auto-pilot commentary auditor for CEO-grade output.

Reads each per-tab commentary in `index.html` (the `<div class="fc-note"
id="commentary-<tab>">` elements) and the briefing output in
`data/signals.json` (`commentary` fields, headlines), then audits each
piece against the contracts in:

  - `data/style_guide.md` §2 — commentary copy rules (2-4 sentences,
    declarative tone, no hedging filler, no forbidden vocabulary).
  - `data/playbook.md` — factual grounding ("numerics match raw data").
  - `data/raw_data.json` — ground-truth numerics.

Output: `data/editorial_report.json` — per-piece findings with
severity, citation, and a "fixable" hint (NEVER an auto-fix).

Zero-fail-rate design
=====================
- Every LLM call uses `bounded_llm_call(validator=...)`. Responses
  that fail schema validation are logged-and-skipped, never returned.
- Output is read-only — the auditor never edits commentary, only
  emits findings.
- Deterministic lint passes (length, forbidden vocab) run FIRST and
  catch the highest-confidence issues without any LLM call. The LLM
  layer only weighs in for tone/factuality which can't be machine-
  checked.
- Two-pass critique: when the LLM marks an issue as "critical", a
  second LLM call critiques the first's reasoning before the finding
  is promoted to critical severity.

Activation
==========
Default OFF. Set both env vars to opt in:
    AGENT_EDITORIAL_REVIEW_ENABLED=1
    ANTHROPIC_API_KEY=...
`AGENT_DISABLE_ALL=1` overrides every opt-in (kill switch).

Same guardrails apply as Agent 10 and the Signal Explainer:
- All LLM calls go through `bounded_llm_call()` (cost cap + audit log).
- Output path `data/editorial_report.json` is on the
  `LLM_WRITABLE_PATHS` allowlist.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from _models import SONNET, OPUS  # noqa: E402

HTML_FILE         = ROOT / 'index.html'
RAW_FILE          = ROOT / 'data' / 'raw_data.json'
SIGNALS_FILE      = ROOT / 'data' / 'signals.json'
STYLE_GUIDE       = ROOT / 'data' / 'style_guide.md'
PLAYBOOK          = ROOT / 'data' / 'playbook.md'
OUT_FILE          = ROOT / 'data' / 'editorial_report.json'

# Per style_guide §2.
FORBIDDEN_VOCAB = (
    'in my opinion',
    'perhaps',
    'a number of',
    'various ',
    'things',
)

# Lower-cased hedging phrases that betray weak conviction.
HEDGING_PATTERNS = (
    'may potentially',
    'might possibly',
    'could potentially',
    'it is possible',
    'arguably',
)

MIN_SENTENCES = 2
MAX_SENTENCES = 4


def _is_enabled() -> bool:
    """Opt-in gate. Kill switch wins."""
    from _agent_guardrails import is_disabled
    if is_disabled():
        return False
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return False
    return os.environ.get('AGENT_EDITORIAL_REVIEW_ENABLED') == '1'


# ────────────────────────────────────────────────────────────────────
# Deterministic lint passes (zero LLM cost, zero false-positives by
# design — they only flag what is provably wrong).
# ────────────────────────────────────────────────────────────────────

def _strip_decimals(text: str) -> str:
    """Remove decimal points inside numbers so '$3.5B' isn't a sentence."""
    return re.sub(r'(?<=\d)\.(?=\d)', '', text)


def _sentence_count(text: str) -> int:
    return sum(_strip_decimals(text).count(c) for c in '.!?')


def lint_length(text: str) -> Optional[dict]:
    n = _sentence_count(text)
    if MIN_SENTENCES <= n <= MAX_SENTENCES:
        return None
    return {
        'rule':     'style_guide §2 — commentary 2–4 sentences',
        'severity': 'critical' if n == 0 else 'warning',
        'detail':   f'sentence_count={n} (band [{MIN_SENTENCES},{MAX_SENTENCES}])',
        'fixable':  'rewrite to {MIN}-{MAX} declarative sentences'.format(
                       MIN=MIN_SENTENCES, MAX=MAX_SENTENCES),
    }


def lint_forbidden_vocab(text: str) -> list[dict]:
    low = text.lower()
    out = []
    for phrase in FORBIDDEN_VOCAB:
        if phrase in low:
            out.append({
                'rule':     'style_guide §2 — forbidden vocabulary',
                'severity': 'warning',
                'detail':   f'phrase {phrase!r} present',
                'fixable':  f'remove or replace {phrase!r}',
            })
    for phrase in HEDGING_PATTERNS:
        if phrase in low:
            out.append({
                'rule':     'style_guide §2 — hedging filler',
                'severity': 'warning',
                'detail':   f'phrase {phrase!r} present',
                'fixable':  f'replace with a declarative statement '
                            f'or drop the sentence',
            })
    return out


# Numeric mentioned in commentary must match the corresponding raw datum.
# We pull the most-common patterns (currency, percentage, with-suffix).
NUM_PATTERN = re.compile(
    r'(?:(?:\$)?\d{1,4}(?:,\d{3})*(?:\.\d+)?%?)'
    r'(?:[BMK]|bp|bps|/gal|/bbl|pp)?'
)


def _normalize_num(s: str) -> Optional[float]:
    """Best-effort numeric extraction from a textual mention. Returns
    None when ambiguous so the check defers rather than false-positives."""
    raw = s.strip().rstrip('%').lstrip('$').replace(',', '')
    # Strip a known unit suffix
    for suffix in ('bps', 'bp', '/gal', '/bbl', 'pp', 'B', 'M', 'K'):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
            break
    try:
        return float(raw)
    except ValueError:
        return None


def lint_no_fabricated_numerics(text: str, raw: dict, vals: dict) -> list[dict]:
    """Flag suspiciously precise numbers in commentary that don't appear
    anywhere in raw_data.json or signals.values. Bias toward false-
    negatives — we'd rather miss a fabrication than wrongly accuse.

    Returns at most ONE finding per piece (the first suspicious number)
    so downstream noise stays low."""
    mentions = NUM_PATTERN.findall(text)
    if not mentions:
        return []

    # Build a set of plausible values from raw data + signals values.
    plausible: set[float] = set()
    def _harvest(obj):
        if isinstance(obj, (int, float)):
            try:
                plausible.add(float(obj))
            except Exception:
                pass
        elif isinstance(obj, dict):
            for v in obj.values():
                _harvest(v)
        elif isinstance(obj, list):
            for v in obj:
                _harvest(v)
    _harvest(raw)
    _harvest(vals)

    findings = []
    for m in mentions:
        v = _normalize_num(m)
        if v is None:
            continue
        # Allow approximate matches (within 1%) to avoid floating-point
        # drift causing false positives. Also tolerate whole-number
        # variants (e.g. commentary "$110" vs raw_data 109.8).
        nearby = any(abs(v - p) < max(0.5, abs(p) * 0.01) for p in plausible)
        if not nearby:
            findings.append({
                'rule':     'style_guide §2 — every numeric must match raw data',
                'severity': 'critical',
                'detail':   f'commentary mentions {m!r} (~{v}) but no '
                            f'matching value found in raw_data or signals',
                'fixable':  'verify against the source series, edit or remove',
            })
            break  # one per piece keeps signal-to-noise high
    return findings


# ────────────────────────────────────────────────────────────────────
# LLM tone / factuality auditor — opt-in only
# ────────────────────────────────────────────────────────────────────

_AUDIT_SYSTEM = """You are the Editorial Auditor for a macroeconomics dashboard
shown to a CEO-level audience. You audit ONE piece of commentary at a
time against the rules in style_guide §2 and the macro framing in
playbook.

Your output MUST be a valid JSON object with this exact schema:

{
  "tone_ok":           true | false,
  "factually_grounded": true | false,
  "issues": [
    {
      "rule":     "<style_guide §X.Y or playbook §X.Y>",
      "severity": "critical" | "warning" | "minor",
      "detail":   "<concise description>",
      "fixable":  "<one-line suggested edit, or '' if not auto-fixable>"
    }
  ],
  "confidence": "high" | "medium" | "low"
}

Rules:
  - Reply with NOTHING but the JSON object. No markdown fence, no prose.
  - "tone_ok": false if commentary uses hedging filler or forbidden
    vocabulary (style_guide §2).
  - "factually_grounded": false if you suspect any numeric or
    forward-looking claim that the data doesn't support.
  - "confidence": "low" if you are uncertain — caller will skip findings
    from low-confidence audits.
  - Empty issues array means clean.
"""


def _audit_validator(text: str) -> bool:
    """bounded_llm_call validator — accept only JSON conforming to the
    expected schema. Anything malformed gets retried/skipped, never
    returned to the caller."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(obj, dict):
        return False
    for key in ('tone_ok', 'factually_grounded', 'issues', 'confidence'):
        if key not in obj:
            return False
    if not isinstance(obj['issues'], list):
        return False
    if obj['confidence'] not in ('high', 'medium', 'low'):
        return False
    return True


def llm_audit(text: str, style_guide: str, playbook: str) -> Optional[dict]:
    """Run one LLM audit pass on a piece of commentary. Returns None when
    disabled, when budget is exhausted, or when the response fails
    schema validation across retries (zero-fail-rate contract)."""
    from _agent_guardrails import bounded_llm_call, BudgetExhausted
    prompt = (
        f'STYLE_GUIDE §2 (commentary copy rules):\n{style_guide}\n\n'
        f'PLAYBOOK (macro framing):\n{playbook}\n\n'
        f'COMMENTARY UNDER REVIEW:\n"""\n{text}\n"""\n\n'
        f'Audit per the schema in the system prompt.'
    )
    try:
        return None if (resp := bounded_llm_call(
            prompt, system=_AUDIT_SYSTEM, model=SONNET,
            max_tokens=600, purpose='editorial:audit',
            validator=_audit_validator,
        )) is None else json.loads(resp)
    except BudgetExhausted:
        return None


def llm_critique_critical(audit: dict, text: str) -> bool:
    """Two-LLM critique: when the first LLM marked an issue as 'critical',
    a second LLM (different family) confirms before we promote it.
    Returns True to keep 'critical' severity, False to downgrade."""
    from _agent_guardrails import bounded_llm_call, BudgetExhausted

    critical_issues = [i for i in audit.get('issues', [])
                       if i.get('severity') == 'critical']
    if not critical_issues:
        return False
    sys_msg = (
        'You critique a fellow auditor\'s "critical" verdict on dashboard '
        'commentary. Be conservative: only confirm "critical" if the issue '
        'would clearly embarrass the team in a board deck. Reply with '
        'exactly one of: "CONFIRM" or "DOWNGRADE" — no other output.'
    )
    prompt = (
        f'COMMENTARY:\n"""\n{text}\n"""\n\n'
        f'AUDITOR FINDING(S):\n{json.dumps(critical_issues, indent=2)}\n\n'
        f'CONFIRM or DOWNGRADE?'
    )
    try:
        out = bounded_llm_call(
            prompt, system=sys_msg, model=OPUS,
            max_tokens=80, purpose='editorial:critique',
            validator=lambda r: r.strip().upper().startswith(
                ('CONFIRM', 'DOWNGRADE')),
        )
    except BudgetExhausted:
        return False
    if out is None:
        return False
    return out.strip().upper().startswith('CONFIRM')


# ────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────

_COMMENTARY_RE = re.compile(
    r'<div class="fc-note" id="commentary-(\w+)"[^>]*>(.*?)</div>',
    re.DOTALL,
)


def gather_commentaries() -> list[tuple[str, str]]:
    """Return list of (label, text) pairs from index.html + signals.json
    commentary fields. Strips trivial HTML before passing to auditors."""
    out: list[tuple[str, str]] = []
    if HTML_FILE.exists():
        html = HTML_FILE.read_text(encoding='utf-8')
        for m in _COMMENTARY_RE.finditer(html):
            tab = m.group(1)
            body = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if body:
                out.append((f'html:commentary-{tab}', body))
    if SIGNALS_FILE.exists():
        try:
            sj = json.loads(SIGNALS_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            sj = {}
        for k in ('commentary', 'outlook_body', 'risk_rationale'):
            v = sj.get(k)
            if isinstance(v, str) and v.strip():
                out.append((f'signals:{k}', v.strip()))
        for k in ('tabs',):
            v = sj.get(k) or {}
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if isinstance(sub_v, str) and sub_v.strip():
                        out.append((f'signals:tabs.{sub_k}', sub_v.strip()))
    return out


def audit_one(label: str, text: str, raw: dict, vals: dict,
              style_guide: str, playbook: str) -> dict:
    """Audit a single piece of commentary. Always returns a dict (never
    raises) so the orchestrator can roll the results into a single
    report even when LLM calls fail."""
    findings: list[dict] = []
    # Deterministic linters
    if (f := lint_length(text)):
        findings.append(f)
    findings.extend(lint_forbidden_vocab(text))
    findings.extend(lint_no_fabricated_numerics(text, raw, vals))

    # LLM auditor (opt-in)
    llm_result = None
    critique_confirms_critical: Optional[bool] = None
    if _is_enabled():
        try:
            llm_result = llm_audit(text, style_guide, playbook)
        except Exception as e:
            llm_result = {'error': repr(e)}
        if isinstance(llm_result, dict) and llm_result.get('issues'):
            if llm_result.get('confidence') != 'low':
                for issue in llm_result['issues']:
                    findings.append({**issue, 'origin': 'llm_audit'})
                # Two-LLM critique gate for critical promotion
                if any(i.get('severity') == 'critical'
                       for i in llm_result['issues']):
                    critique_confirms_critical = llm_critique_critical(
                        llm_result, text)
                    # If critique downgrades, mark all our 'critical'
                    # llm_audit findings as 'warning' instead.
                    if critique_confirms_critical is False:
                        for f in findings:
                            if (f.get('origin') == 'llm_audit'
                                    and f.get('severity') == 'critical'):
                                f['severity'] = 'warning'
                                f['detail'] = (
                                    f.get('detail', '') +
                                    ' [critic downgraded]')

    return {
        'label':                       label,
        'text_preview':                text[:200],
        'sentence_count':              _sentence_count(text),
        'findings':                    findings,
        'llm_confidence':              (llm_result or {}).get('confidence'),
        'critique_confirms_critical':  critique_confirms_critical,
    }


def run() -> dict:
    """Build the editorial report. Always returns a dict; never raises."""
    raw = {}
    vals = {}
    if RAW_FILE.exists():
        try:
            raw = json.loads(RAW_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            raw = {}
    if SIGNALS_FILE.exists():
        try:
            vals = (json.loads(SIGNALS_FILE.read_text(encoding='utf-8'))
                    .get('values', {}) or {})
        except json.JSONDecodeError:
            vals = {}
    style_guide = STYLE_GUIDE.read_text(encoding='utf-8')[:14000] if STYLE_GUIDE.exists() else ''
    playbook = PLAYBOOK.read_text(encoding='utf-8')[:14000] if PLAYBOOK.exists() else ''

    from _agent_memory import set_agent
    from _agent_guardrails import reset_call_counter, status_dict, calls_used
    set_agent('editorial')
    reset_call_counter()

    pieces = gather_commentaries()
    reports = [audit_one(label, text, raw, vals, style_guide, playbook)
               for label, text in pieces]

    # Roll-up severity
    severities = {'critical': 0, 'warning': 0, 'minor': 0}
    for r in reports:
        for f in r['findings']:
            sev = f.get('severity', 'warning')
            if sev in severities:
                severities[sev] += 1

    return {
        'generated_at':   datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'pieces_audited': len(reports),
        'llm_enabled':    _is_enabled(),
        'llm_calls_used': calls_used(),
        'guardrails':     status_dict(),
        'severity_counts': severities,
        'pieces':         reports,
    }


def main():
    print('[Editorial Review] Starting...')
    payload = run()
    from _agent_guardrails import assert_path_allowlisted
    rel = str(OUT_FILE.relative_to(ROOT))
    assert_path_allowlisted(rel)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'[Editorial Review] Audited {payload["pieces_audited"]} pieces. '
          f'Severities: {payload["severity_counts"]}. '
          f'LLM enabled: {payload["llm_enabled"]}. '
          f'Report at {OUT_FILE.relative_to(ROOT)}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
