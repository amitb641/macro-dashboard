"""
Agent Memory — append-only audit log for LLM-driven agent activity.

Every call to `_agent_guardrails.bounded_llm_call()` writes one JSONL
record here. The log is the system of record for: which agents called
which model, with what prompt, what they got back, what it cost, and
whether the call errored.

Why a separate module
=====================
- Other agents (briefing_agent.py, visual_review.py, earnings_agent.py)
  may opt into the same memory log later; centralising the schema and
  writer keeps the audit format stable.
- Replay/analysis tooling parses one file with one schema. Drift across
  agents would defeat the audit.

Schema (one JSON object per line)
=================================
    {
      "ts": "2026-05-12T19:30:00Z",   // UTC ISO-8601
      "agent": "repair",              // short agent name
      "purpose": "diagnose:staleness",// caller-supplied label
      "model": "claude-sonnet-4-6",
      "call_index": 1,                // 1-based within this run
      "elapsed_sec": 1.42,
      "usage": {"input_tokens": 800, "output_tokens": 240},
      "prompt_sha": "ab12...",        // sha256 of prompt (full text in prompt_truncated)
      "prompt_truncated": "...first 4KB of prompt...",
      "response": "...first 8KB of response..." | null,  // null on error
      "system_truncated": "...first 1KB of system prompt...",
      "error": "..." | absent          // present only on failure
    }

Truncation keeps file size bounded; full prompts/responses live only in
the CI run log when verbose mode is enabled.

Retention
=========
The file is append-only across runs but capped at MEMORY_LINE_CAP lines
(rolling FIFO trim on each write batch). Older entries are dropped.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT / 'data' / 'agent_memory.jsonl'

# Hard limits — keep file size bounded.
MEMORY_LINE_CAP   = 2000      # ~last 2K LLM calls retained
PROMPT_TRUNC      = 4096      # bytes of prompt kept inline
RESPONSE_TRUNC    = 8192      # bytes of response kept inline
SYSTEM_TRUNC      = 1024      # bytes of system prompt kept inline

# Default agent label — set per-run by `set_agent(name)`. Falls back to
# 'unknown' so accidental calls before set_agent are still attributed.
_AGENT_LABEL = {'name': 'unknown'}


def set_agent(name: str) -> None:
    """Tag subsequent log_llm_call() entries with this agent name.

    Call once at the top of each agent's main(): `set_agent('repair')`."""
    _AGENT_LABEL['name'] = name


def _truncate(s: Optional[str], limit: int) -> Optional[str]:
    if s is None:
        return None
    if len(s) <= limit:
        return s
    return s[:limit] + f'\n…[truncated, {len(s)-limit} more chars]'


def log_llm_call(
    *,
    purpose: str,
    model: str,
    prompt: str,
    system: str,
    response: Optional[str],
    usage: dict,
    elapsed_sec: float,
    call_index: int,
    error: Optional[str] = None,
) -> None:
    """Append one entry. Never raises — failure to log is itself logged
    via print (the agent should not crash because the audit file is
    unwritable). Auto-trims to MEMORY_LINE_CAP."""
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry: dict[str, Any] = {
            'ts': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'agent': _AGENT_LABEL['name'],
            'purpose': purpose,
            'model': model,
            'call_index': call_index,
            'elapsed_sec': elapsed_sec,
            'usage': usage or {},
            'prompt_sha': hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16],
            'prompt_truncated': _truncate(prompt, PROMPT_TRUNC),
            'response': _truncate(response, RESPONSE_TRUNC),
            'system_truncated': _truncate(system, SYSTEM_TRUNC),
        }
        if error:
            entry['error'] = error[:512]
        line = json.dumps(entry, ensure_ascii=False, separators=(',', ':'))

        existing: list[str] = []
        if MEMORY_FILE.exists():
            existing = MEMORY_FILE.read_text(encoding='utf-8').splitlines()
        existing.append(line)
        # Trim from the front (oldest) when over cap.
        if len(existing) > MEMORY_LINE_CAP:
            existing = existing[-MEMORY_LINE_CAP:]
        MEMORY_FILE.write_text('\n'.join(existing) + '\n', encoding='utf-8')
    except Exception as e:
        # Don't crash the calling agent on audit-log failure.
        print(f'[_agent_memory] WARN: failed to log call: {e!r}')


def recent_for_agent(agent: str, limit: int = 50) -> list[dict]:
    """Read the most recent `limit` entries for a given agent name.
    Used by replay/analysis tooling; not on the hot path."""
    if not MEMORY_FILE.exists():
        return []
    out: list[dict] = []
    for line in MEMORY_FILE.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get('agent') == agent:
            out.append(row)
    return out[-limit:]


def stats() -> dict:
    """Aggregate counters across the full memory file. Cheap — used in
    incident reports to show 'this agent has called Claude N times across
    the rolling window.'"""
    if not MEMORY_FILE.exists():
        return {'total': 0, 'by_agent': {}, 'errors': 0}
    by_agent: dict[str, int] = {}
    errors = 0
    total = 0
    for line in MEMORY_FILE.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        by_agent[row.get('agent', '?')] = by_agent.get(row.get('agent', '?'), 0) + 1
        if 'error' in row:
            errors += 1
    return {'total': total, 'by_agent': by_agent, 'errors': errors}
