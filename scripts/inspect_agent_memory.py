#!/usr/bin/env python3
"""
Agent Memory Inspector — CLI for reviewing the audit log.

Reads `data/agent_memory.jsonl` and prints filtered, human-readable
summaries of past agentic LLM calls. Useful when triaging incidents,
auditing cost spikes, or replaying what the diagnostician said about a
particular finding.

Usage
=====
    # Aggregate stats across the full file
    python scripts/inspect_agent_memory.py

    # Last 20 entries (newest last)
    python scripts/inspect_agent_memory.py --tail 20

    # Filter by agent name
    python scripts/inspect_agent_memory.py --agent repair --tail 10

    # Filter by purpose substring (e.g. all 'diagnose:Staleness' calls)
    python scripts/inspect_agent_memory.py --purpose Staleness --full

    # Show prompts and full responses (verbose). Otherwise prints summary.
    python scripts/inspect_agent_memory.py --tail 5 --full

This tool is READ-ONLY by design — it never modifies the log. The 2000-
entry rolling cap is enforced by `_agent_memory.log_llm_call()` itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _models import cost_usd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT / 'data' / 'agent_memory.jsonl'


def load_entries() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    out: list[dict] = []
    for line in MEMORY_FILE.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def aggregate(entries: list[dict]) -> dict:
    total = len(entries)
    by_agent: dict[str, int] = {}
    by_model: dict[str, int] = {}
    by_purpose: dict[str, int] = {}
    errors = 0
    in_tokens = 0
    out_tokens = 0
    for e in entries:
        by_agent[e.get('agent', '?')]   = by_agent.get(e.get('agent', '?'), 0) + 1
        by_model[e.get('model', '?')]   = by_model.get(e.get('model', '?'), 0) + 1
        # Purpose prefix (before first colon) — gives a useful bucket.
        purpose = (e.get('purpose') or '?').split(':', 1)[0]
        by_purpose[purpose] = by_purpose.get(purpose, 0) + 1
        if 'error' in e:
            errors += 1
        usage = e.get('usage') or {}
        in_tokens  += usage.get('input_tokens', 0) or 0
        out_tokens += usage.get('output_tokens', 0) or 0
    return {
        'total':       total,
        'by_agent':    by_agent,
        'by_model':    by_model,
        'by_purpose':  by_purpose,
        'errors':      errors,
        'input_tokens':  in_tokens,
        'output_tokens': out_tokens,
    }


def cost_breakdown(entries: list[dict]) -> dict:
    """Per-call cost rollup for optimization. Splits by model / agent /
    purpose-prefix and tracks the wasted-call signal (failed calls cost
    little but burn the per-run budget and indicate a broken agent)."""
    out = {
        'total_usd': 0.0, 'calls': len(entries), 'ok': 0, 'errors': 0,
        'in_tokens': 0, 'out_tokens': 0, 'cache_read': 0, 'cache_write': 0,
        'by_model': {}, 'by_agent': {}, 'by_purpose': {},
        'first_ts': None, 'last_ts': None,
    }
    for e in entries:
        ts = e.get('ts')
        if ts:
            out['first_ts'] = ts if out['first_ts'] is None else min(out['first_ts'], ts)
            out['last_ts']  = ts if out['last_ts']  is None else max(out['last_ts'], ts)
        is_err = 'error' in e
        out['errors' if is_err else 'ok'] += 1
        usage = e.get('usage') or {}
        model = e.get('model', '?')
        c = cost_usd(model, usage)
        out['total_usd'] += c
        out['in_tokens']   += usage.get('input_tokens', 0) or 0
        out['out_tokens']  += usage.get('output_tokens', 0) or 0
        out['cache_read']  += usage.get('cache_read_input_tokens', 0) or 0
        out['cache_write'] += usage.get('cache_creation_input_tokens', 0) or 0
        for dim, key in (('by_model', model),
                         ('by_agent', e.get('agent', '?')),
                         ('by_purpose', (e.get('purpose') or '?').split(':', 1)[0])):
            d = out[dim].setdefault(key, {'usd': 0.0, 'calls': 0, 'errors': 0})
            d['usd'] += c
            d['calls'] += 1
            d['errors'] += 1 if is_err else 0
    return out


def print_cost_report(entries: list[dict]) -> None:
    cb = cost_breakdown(entries)
    fail_pct = (cb['errors'] / cb['calls'] * 100) if cb['calls'] else 0.0
    print('LLM COST REPORT — ' + str(MEMORY_FILE.relative_to(ROOT)))
    print(f'  window:       {cb["first_ts"]} → {cb["last_ts"]}')
    print(f'  total cost:   ${cb["total_usd"]:.4f}  ({cb["calls"]} calls)')
    print(f'  calls:        {cb["ok"]} ok · {cb["errors"]} failed ({fail_pct:.0f}% fail)')
    print(f'  tokens:       {cb["in_tokens"]:,} in · {cb["out_tokens"]:,} out · '
          f'{cb["cache_read"]:,} cache-read · {cb["cache_write"]:,} cache-write')
    if fail_pct >= 25:
        print(f'  ⚠ HIGH FAILURE RATE ({fail_pct:.0f}%) — failed calls waste the '
              f'per-run budget and usually mean a broken request (bad model id, '
              f'oversized prompt, schema). Fix before optimizing spend.')
    for label, dim in (('By model', 'by_model'),
                       ('By agent', 'by_agent'),
                       ('By purpose', 'by_purpose')):
        print(f'  {label}:')
        for k, d in sorted(cb[dim].items(), key=lambda kv: -kv[1]['usd']):
            efail = (d['errors'] / d['calls'] * 100) if d['calls'] else 0
            print(f'    ${d["usd"]:.4f}  {d["calls"]:>4} calls  {efail:>3.0f}% fail  {k}')


def fmt_entry(e: dict, full: bool) -> str:
    head = (
        f'[{e.get("ts","?")}] {e.get("agent","?")}/{e.get("purpose","?")} '
        f'· {e.get("model","?")} · {e.get("elapsed_sec","?")}s'
    )
    usage = e.get('usage') or {}
    if usage:
        head += f' · in={usage.get("input_tokens","?")} out={usage.get("output_tokens","?")}'
    if 'error' in e:
        head += f' · ERROR: {e["error"][:120]}'
        return head
    if not full:
        # Compact one-liner — show first line of response.
        resp = (e.get('response') or '').strip().split('\n', 1)[0]
        return head + (f'\n    → {resp[:140]}' if resp else '')
    # Full mode — prompt + response
    body = [
        head,
        '  ─── system ───',
        '  ' + (e.get('system_truncated') or '(none)').replace('\n', '\n  '),
        '  ─── prompt ───',
        '  ' + (e.get('prompt_truncated') or '(none)').replace('\n', '\n  '),
        '  ─── response ───',
        '  ' + (e.get('response') or '(none)').replace('\n', '\n  '),
    ]
    return '\n'.join(body)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--agent',   help='Filter by agent name (e.g. repair, explainer)')
    p.add_argument('--purpose', help='Filter by purpose substring (e.g. Staleness)')
    p.add_argument('--tail',    type=int, default=0,
                   help='Show last N entries instead of aggregate stats')
    p.add_argument('--full',    action='store_true',
                   help='Show full prompts and responses (otherwise summary lines)')
    p.add_argument('--cost',    action='store_true',
                   help='Show USD cost rollup (by model/agent/purpose) + failure rate')
    p.add_argument('--since',   help='Only entries with ts >= this ISO prefix '
                                     '(e.g. 2026-05-28 for today, or a run timestamp)')
    args = p.parse_args(argv)

    entries = load_entries()
    if args.agent:
        entries = [e for e in entries if e.get('agent') == args.agent]
    if args.purpose:
        needle = args.purpose.lower()
        entries = [e for e in entries if needle in (e.get('purpose') or '').lower()]
    if args.since:
        entries = [e for e in entries if (e.get('ts') or '') >= args.since]

    if args.cost:
        print_cost_report(entries)
        return 0

    if args.tail:
        for e in entries[-args.tail:]:
            print(fmt_entry(e, args.full))
            print()
        return 0

    # Default: aggregate stats
    agg = aggregate(entries)
    print(f'Agent Memory — {MEMORY_FILE.relative_to(ROOT)}')
    print(f'Total entries: {agg["total"]}')
    print(f'Errors:        {agg["errors"]}')
    print(f'Tokens:        {agg["input_tokens"]:,} in · {agg["output_tokens"]:,} out')
    print()
    for label, m in [('By agent', agg['by_agent']),
                     ('By model', agg['by_model']),
                     ('By purpose-prefix', agg['by_purpose'])]:
        print(f'{label}:')
        for k, v in sorted(m.items(), key=lambda kv: -kv[1]):
            print(f'  {v:>6}  {k}')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
