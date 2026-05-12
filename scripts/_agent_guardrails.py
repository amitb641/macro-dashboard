"""
Agent Guardrails — runtime safety controls for LLM-driven agents.

Hard guardrails encoded in code (not prompts) for agents that take actions
based on LLM reasoning. Currently used by Agent 10 (Repair Diagnostician);
extensible to future agentic upgrades (Phase 2 Analyzer explainer, Phase 3
Orchestrator).

Principles
==========
1. **Layout/format is sacrosanct.** index.html structure and renderer.py
   regex patterns are never modifiable by agents — only by humans.
2. **Cost is bounded.** Every agentic run has a hard cap on LLM calls.
   Exceeding it halts the agent cleanly with a budget-exhausted incident.
3. **Kill switch is mandatory.** `AGENT_DISABLE_ALL=1` reverts the system
   to deterministic-only mode with zero code changes.
4. **Audit, always.** Every LLM call goes through `bounded_llm_call()` so
   the prompt, response, model, and token cost are logged to
   `data/agent_memory.jsonl` for review and replay.

Environment variables
=====================
- AGENT_DISABLE_ALL=1         Disable all agentic features; agents fall
                              back to deterministic-only behaviour.
- AGENT_DIAGNOSTICIAN_ENABLED=1  Opt-in for Agent 10 LLM diagnostician.
                                 Defaults off so CI is unchanged until
                                 the maintainer flips it.
- AGENT_MAX_LLM_CALLS=20      Per-run cap on LLM calls across all agents.
- ANTHROPIC_API_KEY           Required when any agentic mode is enabled.

Public API
==========
- `is_disabled()` → bool
- `is_diagnostician_enabled()` → bool
- `bounded_llm_call(prompt, *, system, model, max_tokens, purpose)`
        → str | None (None = skipped due to guardrails)
- `assert_path_allowlisted(path)` → raises ValueError if outside allowlist
- `critique(proposed_action, original_response, *, model, system)`
        → critique text (used by Stage 10b/10c, not 10a)

Out of scope (deferred to future stages)
========================================
- Tool-use loops with multi-turn reasoning. Stage 10a uses a single
  prompted call per finding; multi-turn is a Stage 10b concern.
- File-write enforcement. Stage 10a is read-only — no writes outside
  `data/incident_reports/` and `data/agent_memory.jsonl`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# Files/dirs an LLM agent may modify. Anything outside this list raises.
# Strict allowlist — additions require human review, never AI proposal.
LLM_WRITABLE_PATHS = frozenset({
    'data/agent_memory.jsonl',
    'data/incident_reports/',
    'data/repair_log.md',             # existing observer log
    'data/known_normal.json',         # learned baselines (Stage 10b+)
    'data/signal_rationales.json',    # Phase 2 signal-explainer output
})

# Files an LLM agent may READ. Broad — reasoning needs context. The risk
# control is on writes, not reads.
LLM_READABLE_PATHS = frozenset({
    'data/',
    'scripts/',
    'CLAUDE.md',
    'METHODOLOGY.md',
    'docs/',
    'tests/',
})


def is_disabled() -> bool:
    """Master kill switch. When True, every agentic feature falls back to
    deterministic behaviour without any code path that touches an LLM."""
    return os.environ.get('AGENT_DISABLE_ALL') == '1'


def is_diagnostician_enabled() -> bool:
    """Per-feature opt-in for the Agent 10 LLM diagnostician.

    Defaults OFF so that merging this code does not silently start sending
    prompts during the next CI run. The maintainer flips this on after
    reviewing the cost and behaviour."""
    if is_disabled():
        return False
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return False
    return os.environ.get('AGENT_DIAGNOSTICIAN_ENABLED') == '1'


def max_llm_calls() -> int:
    """Per-run cap on total LLM calls across all agents.

    A finding-by-finding diagnostician on a typical 5-issue report uses
    ~5 calls; cap of 20 leaves headroom for retries and the two-LLM
    critique pattern without runaway cost on a pathological run."""
    try:
        return int(os.environ.get('AGENT_MAX_LLM_CALLS', '20'))
    except ValueError:
        return 20


class BudgetExhausted(RuntimeError):
    """Raised when the per-run LLM call cap is hit. Agents catch this and
    surface it as an incident rather than crashing the pipeline."""


# In-process counter; reset per agent run by the entry point.
_CALL_COUNT = {'n': 0}


def reset_call_counter() -> None:
    """Reset the in-process LLM-call counter. Call once at the top of
    each agent's main() so multiple agents in one process share a budget."""
    _CALL_COUNT['n'] = 0


def calls_used() -> int:
    return _CALL_COUNT['n']


def assert_path_allowlisted(rel_path: str) -> None:
    """Raises ValueError if `rel_path` (relative to repo root) is not in
    the LLM-writable allowlist. Call this immediately before any LLM-
    proposed file write. Prefixes (entries ending /) match by prefix."""
    rel = rel_path.lstrip('./')
    for allowed in LLM_WRITABLE_PATHS:
        if allowed.endswith('/') and rel.startswith(allowed):
            return
        if rel == allowed:
            return
    raise ValueError(
        f'agent_guardrails: refusing to let an LLM-driven agent write to '
        f'{rel!r} — path not in LLM_WRITABLE_PATHS allowlist. Add it to '
        f'scripts/_agent_guardrails.py with human review if intentional.'
    )


def bounded_llm_call(
    prompt: str,
    *,
    system: str,
    model: str,
    max_tokens: int = 1024,
    purpose: str,
    temperature: float = 0.2,
) -> Optional[str]:
    """The ONLY way agentic code should call Claude. Wraps:
      - Budget check (raises BudgetExhausted if over cap)
      - HTTP call with retries (matches briefing_agent.py pattern)
      - Audit logging to agent_memory.jsonl

    Returns the response text, or None if guardrails disabled the call.

    `purpose` is a short label (e.g. 'diagnose:staleness') logged with
    the memory entry. It's how humans grep the audit log later.
    """
    if is_disabled():
        return None

    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return None

    if _CALL_COUNT['n'] >= max_llm_calls():
        raise BudgetExhausted(
            f'LLM call budget exhausted ({_CALL_COUNT["n"]}/{max_llm_calls()}). '
            f'Raise AGENT_MAX_LLM_CALLS or reduce per-finding scope.'
        )

    # Import locally so this module is importable in environments without
    # `requests` (e.g. lightweight test runners).
    import requests

    # Lazy import to avoid circular dependency with _agent_memory.
    from _agent_memory import log_llm_call

    _CALL_COUNT['n'] += 1
    started = time.time()
    last_err = None

    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            r = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': model,
                    'max_tokens': max_tokens,
                    'system': system,
                    'temperature': temperature,
                    'messages': [{'role': 'user', 'content': prompt}],
                },
                timeout=90,
            )
            r.raise_for_status()
            body = r.json()
            text = body['content'][0]['text'].strip()
            usage = body.get('usage', {})
            log_llm_call(
                purpose=purpose, model=model, prompt=prompt,
                system=system, response=text, usage=usage,
                elapsed_sec=round(time.time() - started, 2),
                call_index=_CALL_COUNT['n'],
            )
            return text
        except Exception as e:
            last_err = e
            continue

    # All retries failed — log the failure and surface it.
    log_llm_call(
        purpose=purpose, model=model, prompt=prompt,
        system=system, response=None, usage={},
        elapsed_sec=round(time.time() - started, 2),
        call_index=_CALL_COUNT['n'],
        error=repr(last_err),
    )
    raise RuntimeError(f'bounded_llm_call({purpose}) failed after retries: {last_err}')


def critique(
    proposed_action: str,
    original_response: str,
    *,
    model: str,
    system: str = (
        'You are a code reviewer. You will be shown a fellow agent\'s '
        'proposed action and the reasoning behind it. Your job is to '
        'flag any case where the action is unsafe, out of scope, or '
        'based on faulty reasoning. Reply with exactly one of: '
        '"APPROVE" (with one-sentence reason) or '
        '"REJECT" (with one-sentence reason). No other output.'
    ),
) -> str:
    """Two-LLM critique pattern. Stages 10b and 10c will use this to gate
    code-modifying actions; included now so it's exercised by tests.

    Not used by Stage 10a (which only produces reports, takes no action)."""
    prompt = (
        f'PROPOSED ACTION:\n{proposed_action}\n\n'
        f'AGENT REASONING:\n{original_response}\n\n'
        f'Verdict?'
    )
    out = bounded_llm_call(
        prompt, system=system, model=model, max_tokens=256,
        purpose='critique',
    )
    return out or 'REJECT — critique disabled (kill switch active).'


def status_dict() -> dict:
    """Snapshot of current guardrail state — for inclusion in incident
    reports so reviewers can see what was/wasn't active during a run."""
    return {
        'disabled': is_disabled(),
        'diagnostician_enabled': is_diagnostician_enabled(),
        'max_llm_calls': max_llm_calls(),
        'calls_used': calls_used(),
        'anthropic_key_set': bool(os.environ.get('ANTHROPIC_API_KEY')),
    }
