#!/usr/bin/env python3
"""
Signal Rationales — Phase 2 of the agentic upgrade.

Read-only narrative augmentation. For each signal that the deterministic
analyzer flagged (`flagged=true` or `alert` non-null), generate a short
Claude-authored rationale grounded in the playbook + recent raw-data
context. Writes to `data/signal_rationales.json` — a NEW artifact, never
mutates `signals.json` so renderer behaviour is unchanged.

Why a separate module
=====================
- analyzer.py is deterministic and forms a tight contract with renderer.
  Adding LLM calls there would mix concerns.
- This script can be invoked AFTER analyzer (or omitted entirely without
  affecting the deterministic pipeline).
- The diagnostician (Agent 10) can OPTIONALLY read signal_rationales.json
  to enrich its reasoning about findings.

Guardrails (encoded, mirrors Agent 10)
======================================
- Opt-in via `AGENT_EXPLAINER_ENABLED=1` (default OFF — no LLM calls
  unless explicitly enabled).
- Kill switch (`AGENT_DISABLE_ALL=1`) overrides the opt-in.
- All calls through `bounded_llm_call()` → cost-capped + audit-logged.
- Hard cap of 10 signals dispatched per run (in addition to the global
  AGENT_MAX_LLM_CALLS budget).
- Output file is on the LLM_WRITABLE_PATHS allowlist (signal_rationales
  added below). Renderer + index.html remain forbidden.

Output schema (data/signal_rationales.json)
============================================
    {
      "generated_at": "2026-05-12T20:30:00Z",
      "based_on_signals_at": "2026-05-12T19:08:03Z",
      "model": "claude-sonnet-4-6",
      "rationales": {
        "<metric>": {
          "value": 3.64,
          "direction": "stable",
          "rationale": "...Markdown text with playbook citation...",
          "playbook_cite": "§2.3"
        },
        ...
      }
    }

Exit code: always 0. Same posture as repair_agent — never blocks the
pipeline.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from _models import SONNET  # noqa: E402

SIGNALS_FILE   = ROOT / 'data' / 'signals.json'
RAW_FILE       = ROOT / 'data' / 'raw_data.json'
PLAYBOOK_FILE  = ROOT / 'data' / 'playbook.md'
KNOWN_NORMAL   = ROOT / 'data' / 'known_normal.json'
OUT_FILE       = ROOT / 'data' / 'signal_rationales.json'

# Hard cap on signals dispatched per run (below or equal to the global
# AGENT_MAX_LLM_CALLS — we leave headroom for the diagnostician).
MAX_SIGNALS_PER_RUN = 10

_SYSTEM_PROMPT = """You are the Signal Rationale Explainer for a macro-economics data pipeline.

Your job: write a 2-4 sentence rationale for ONE flagged signal. Ground
every claim in either the playbook (cite §X.Y) or a number from the
provided raw-data context.

Hard rules:
  1. Cite a playbook section by tag (e.g. "§4.2") in the body of the
     rationale, or end with "no playbook coverage — flagged for human
     review" if no section applies.
  2. Never fabricate numbers. If you don't see a number in the data
     blob, don't put one in your output.
  3. Never recommend a code, layout, or data change. You are a narrator,
     not an actor. Use phrasing like "the data shows…" / "this matches
     the playbook's…" — NOT "recommend bumping limit=24" or similar.
  4. Compare against the noise floor in the playbook §2.3 / known-normal
     before declaring a move "significant." A within-noise move is
     reported as "tracking baseline" not "alert."
  5. If the signal direction is opposite to what the playbook would
     predict for the current regime, say so — don't paper over it.

Output: produce EXACTLY one short Markdown paragraph (no headings, no
list items, no JSON). Between 2 and 4 sentences. Plain prose.
"""


def _is_enabled() -> bool:
    """Same opt-in semantics as the Agent 10 diagnostician."""
    from _agent_guardrails import is_disabled
    if is_disabled():
        return False
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return False
    return os.environ.get('AGENT_EXPLAINER_ENABLED') == '1'


def _flagged_signals(signals: dict) -> list[tuple[str, dict]]:
    """Return (metric_name, signal_dict) pairs that the analyzer flagged.
    Order: alerts first (most informative), then plain flagged."""
    alerts: list[tuple[str, dict]] = []
    flagged: list[tuple[str, dict]] = []
    for name, sig in signals.items():
        if not isinstance(sig, dict):
            continue
        if sig.get('alert'):
            alerts.append((name, sig))
        elif sig.get('flagged'):
            flagged.append((name, sig))
    return alerts + flagged


def _raw_context_for(metric: str, raw: dict, max_obs: int = 6) -> str:
    """Pull a short slice of recent observations for the metric. Falls
    back to '(no raw data found)' so the LLM can't pretend a series
    exists when it doesn't."""
    series = raw.get(metric)
    if not series:
        return f'(no raw_data series for {metric!r})'
    if isinstance(series, dict) and 'value' in series:
        return f'{metric}: latest scalar = {series.get("value")} ({series.get("date","?")})'
    if isinstance(series, list):
        head = series[:max_obs]
        return f'{metric} (most recent {len(head)}): ' + json.dumps(head, ensure_ascii=False)
    return f'(unrecognised shape for {metric}: {type(series).__name__})'


def _build_prompt(metric: str, signal: dict, raw: dict,
                  playbook: str, normals: str) -> str:
    return (
        f'PLAYBOOK (truncated):\n{playbook}\n\n'
        f'KNOWN NORMAL BASELINES (JSON):\n{normals}\n\n'
        f'SIGNAL UNDER REVIEW (JSON):\n'
        f'{json.dumps({"metric": metric, **signal}, ensure_ascii=False)}\n\n'
        f'RAW-DATA SLICE:\n{_raw_context_for(metric, raw)}\n\n'
        f'Write the rationale per the system-prompt rules. One paragraph.'
    )


def _extract_cite(text: str) -> str:
    """Pull a '§X.Y' tag from the rationale if present. Returns '' if
    the LLM didn't cite anything — caller flags those for human review."""
    import re
    m = re.search(r'§\d+(?:\.\d+)?', text)
    return m.group(0) if m else ''


def explain_signals() -> dict | None:
    """Generate rationales. Returns the full output dict, or None when
    explainer is disabled (caller writes nothing)."""
    if not _is_enabled():
        return None

    from _agent_guardrails import (
        bounded_llm_call, BudgetExhausted, reset_call_counter, status_dict,
    )
    from _agent_memory import set_agent

    set_agent('explainer')
    reset_call_counter()

    if not SIGNALS_FILE.exists():
        print(f'[explainer] No signals.json at {SIGNALS_FILE} — nothing to explain.')
        return None

    signals_doc = json.loads(SIGNALS_FILE.read_text(encoding='utf-8'))
    signals = signals_doc.get('signals', {})
    raw = json.loads(RAW_FILE.read_text(encoding='utf-8')) if RAW_FILE.exists() else {}

    playbook = PLAYBOOK_FILE.read_text(encoding='utf-8')[:16000] if PLAYBOOK_FILE.exists() else ''
    normals  = KNOWN_NORMAL.read_text(encoding='utf-8')[:8000] if KNOWN_NORMAL.exists() else ''

    candidates = _flagged_signals(signals)[:MAX_SIGNALS_PER_RUN]

    rationales: dict[str, dict] = {}
    budget_hit = False

    for metric, signal in candidates:
        prompt = _build_prompt(metric, signal, raw, playbook, normals)
        try:
            response = bounded_llm_call(
                prompt,
                system=_SYSTEM_PROMPT,
                model=SONNET,
                max_tokens=300,
                purpose=f'explain:{metric}',
            )
        except BudgetExhausted:
            budget_hit = True
            break
        except Exception as e:
            rationales[metric] = {
                'value':     signal.get('value'),
                'direction': signal.get('direction'),
                'rationale': f'(rationale failed: {e!r})',
                'playbook_cite': '',
            }
            continue

        if response:
            rationales[metric] = {
                'value':     signal.get('value'),
                'direction': signal.get('direction'),
                'rationale': response.strip(),
                'playbook_cite': _extract_cite(response),
            }

    return {
        'generated_at':        datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'based_on_signals_at': signals_doc.get('analyzed_at'),
        'model':               SONNET,
        'budget_hit':          budget_hit,
        'guardrails':          status_dict(),
        'rationales':          rationales,
    }


def write_output(payload: dict) -> Path:
    """Persist the rationales bundle. Asserts the path against the
    LLM_WRITABLE_PATHS allowlist (need to add an entry — see below)."""
    from _agent_guardrails import assert_path_allowlisted
    rel = str(OUT_FILE.relative_to(ROOT))
    assert_path_allowlisted(rel)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return OUT_FILE


def main():
    print('[Signal Explainer] Starting...')
    payload = explain_signals()
    if payload is None:
        print('[Signal Explainer] Disabled (default). '
              'Set AGENT_EXPLAINER_ENABLED=1 + ANTHROPIC_API_KEY to opt in.')
        return 0
    if not payload.get('rationales'):
        print('[Signal Explainer] No flagged signals or no LLM responses — nothing written.')
        return 0
    path = write_output(payload)
    print(f'[Signal Explainer] Wrote {len(payload["rationales"])} '
          f'rationale(s) to {path.relative_to(ROOT)}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
