#!/usr/bin/env python3
"""
Tests for the agentic foundation: _agent_guardrails, _agent_memory, and
the Repair Diagnostician's observer-mode preservation.

These tests never call the real Anthropic API. They verify:
  - Kill switch and opt-in semantics
  - Path allowlist enforcement
  - Cost cap → BudgetExhausted
  - Memory log schema + retention
  - Observer mode (default off) preserves prior v1 behaviour exactly

Usage: python tests/test_agentic.py
       python -m pytest tests/test_agentic.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))


# ──────────────────────────────────────────────────────────────────────
# Guardrails
# ──────────────────────────────────────────────────────────────────────

class TestGuardrails(unittest.TestCase):

    def setUp(self):
        # Snapshot env so tests don't leak.
        self._env_keys = [
            'AGENT_DISABLE_ALL', 'AGENT_DIAGNOSTICIAN_ENABLED',
            'AGENT_MAX_LLM_CALLS', 'ANTHROPIC_API_KEY',
        ]
        self._saved = {k: os.environ.get(k) for k in self._env_keys}
        for k in self._env_keys:
            os.environ.pop(k, None)
        # Force reimport so module-level state is fresh.
        for mod in ('_agent_guardrails', '_agent_memory'):
            sys.modules.pop(mod, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_kill_switch_disables_everything(self):
        os.environ['AGENT_DISABLE_ALL'] = '1'
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        os.environ['AGENT_DIAGNOSTICIAN_ENABLED'] = '1'
        import _agent_guardrails as g
        self.assertTrue(g.is_disabled())
        self.assertFalse(g.is_diagnostician_enabled())
        # bounded_llm_call must return None silently when disabled.
        out = g.bounded_llm_call(
            'hello', system='sys', model='claude-sonnet-4-6',
            purpose='test:kill',
        )
        self.assertIsNone(out)

    def test_diagnostician_default_off(self):
        # No env vars set — diagnostician must be off.
        import _agent_guardrails as g
        self.assertFalse(g.is_diagnostician_enabled())

    def test_diagnostician_needs_api_key(self):
        os.environ['AGENT_DIAGNOSTICIAN_ENABLED'] = '1'
        # No ANTHROPIC_API_KEY — must still be off.
        import _agent_guardrails as g
        self.assertFalse(g.is_diagnostician_enabled())

    def test_diagnostician_enabled_when_all_flags_set(self):
        os.environ['AGENT_DIAGNOSTICIAN_ENABLED'] = '1'
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        import _agent_guardrails as g
        self.assertTrue(g.is_diagnostician_enabled())

    def test_path_allowlist_accepts_known_paths(self):
        import _agent_guardrails as g
        # Exact match
        g.assert_path_allowlisted('data/agent_memory.jsonl')
        g.assert_path_allowlisted('data/repair_log.md')
        # Prefix match
        g.assert_path_allowlisted('data/incident_reports/2026-05-12.md')
        g.assert_path_allowlisted('data/incident_reports/anything-deep/file.md')

    def test_path_allowlist_rejects_renderer(self):
        import _agent_guardrails as g
        # The crown jewels: rendering and layout must NEVER be writable.
        with self.assertRaises(ValueError):
            g.assert_path_allowlisted('scripts/renderer.py')
        with self.assertRaises(ValueError):
            g.assert_path_allowlisted('index.html')
        with self.assertRaises(ValueError):
            g.assert_path_allowlisted('data/raw_data.json')

    def test_budget_cap_raises_when_exceeded(self):
        # No API key → bounded_llm_call returns None before checking budget.
        # To exercise the budget path, simulate prior calls + key present.
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        os.environ['AGENT_MAX_LLM_CALLS'] = '2'
        import _agent_guardrails as g
        g.reset_call_counter()
        # Manually bump the counter to the cap.
        g._CALL_COUNT['n'] = 2
        with self.assertRaises(g.BudgetExhausted):
            g.bounded_llm_call(
                'hello', system='sys', model='claude-sonnet-4-6',
                purpose='test:budget',
            )

    def test_max_llm_calls_parses_env(self):
        os.environ['AGENT_MAX_LLM_CALLS'] = '5'
        import _agent_guardrails as g
        self.assertEqual(g.max_llm_calls(), 5)

    def test_max_llm_calls_fallback_on_bad_value(self):
        os.environ['AGENT_MAX_LLM_CALLS'] = 'not-a-number'
        import _agent_guardrails as g
        self.assertEqual(g.max_llm_calls(), 20)


# ──────────────────────────────────────────────────────────────────────
# Memory
# ──────────────────────────────────────────────────────────────────────

class TestMemory(unittest.TestCase):

    def setUp(self):
        for mod in ('_agent_memory',):
            sys.modules.pop(mod, None)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Redirect MEMORY_FILE to a temp location.
        import _agent_memory as m
        self._saved_path = m.MEMORY_FILE
        m.MEMORY_FILE = Path(self._tmp.name) / 'agent_memory.jsonl'
        self.m = m

    def tearDown(self):
        self.m.MEMORY_FILE = self._saved_path

    def test_log_entry_schema(self):
        self.m.set_agent('repair')
        self.m.log_llm_call(
            purpose='test:schema', model='claude-sonnet-4-6',
            prompt='p', system='s', response='r',
            usage={'input_tokens': 10, 'output_tokens': 5},
            elapsed_sec=0.1, call_index=1,
        )
        lines = self.m.MEMORY_FILE.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        for k in ('ts', 'agent', 'purpose', 'model', 'call_index',
                  'elapsed_sec', 'usage', 'prompt_sha',
                  'prompt_truncated', 'response', 'system_truncated'):
            self.assertIn(k, row, f'missing field {k}')
        self.assertEqual(row['agent'], 'repair')
        self.assertEqual(row['purpose'], 'test:schema')
        self.assertNotIn('error', row)  # success path

    def test_error_field_present_on_failure(self):
        self.m.log_llm_call(
            purpose='test:err', model='m', prompt='p', system='s',
            response=None, usage={}, elapsed_sec=0.0, call_index=1,
            error='boom',
        )
        row = json.loads(self.m.MEMORY_FILE.read_text().splitlines()[0])
        self.assertEqual(row['error'], 'boom')
        self.assertIsNone(row['response'])

    def test_truncation_bounded(self):
        big_prompt = 'x' * 100_000
        self.m.log_llm_call(
            purpose='test:trunc', model='m', prompt=big_prompt,
            system='s', response='r', usage={}, elapsed_sec=0.0, call_index=1,
        )
        row = json.loads(self.m.MEMORY_FILE.read_text().splitlines()[0])
        self.assertLess(len(row['prompt_truncated']), len(big_prompt))
        self.assertIn('[truncated', row['prompt_truncated'])

    def test_retention_caps_lines(self):
        # Lower the cap so the test is fast.
        self.m.MEMORY_LINE_CAP = 5
        for i in range(10):
            self.m.log_llm_call(
                purpose=f't{i}', model='m', prompt='p', system='s',
                response='r', usage={}, elapsed_sec=0.0, call_index=i,
            )
        lines = [ln for ln in self.m.MEMORY_FILE.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 5)
        # Should keep the most recent 5.
        purposes = [json.loads(ln)['purpose'] for ln in lines]
        self.assertEqual(purposes, ['t5', 't6', 't7', 't8', 't9'])

    def test_recent_for_agent_filters(self):
        self.m.set_agent('A')
        self.m.log_llm_call(purpose='a1', model='m', prompt='p',
                            system='s', response='r', usage={},
                            elapsed_sec=0.0, call_index=1)
        self.m.set_agent('B')
        self.m.log_llm_call(purpose='b1', model='m', prompt='p',
                            system='s', response='r', usage={},
                            elapsed_sec=0.0, call_index=2)
        a_rows = self.m.recent_for_agent('A')
        b_rows = self.m.recent_for_agent('B')
        self.assertEqual(len(a_rows), 1)
        self.assertEqual(a_rows[0]['purpose'], 'a1')
        self.assertEqual(len(b_rows), 1)
        self.assertEqual(b_rows[0]['purpose'], 'b1')


# ──────────────────────────────────────────────────────────────────────
# Repair Agent — observer mode (default, no LLM)
# ──────────────────────────────────────────────────────────────────────

class TestRepairAgentObserverMode(unittest.TestCase):
    """Verify the diagnostician upgrade did not change observer-mode
    behaviour. With AGENT_DIAGNOSTICIAN_ENABLED unset, the agent must
    behave exactly as v1 — no LLM imports attempted, no incident report
    written, just the rolling summary log."""

    def setUp(self):
        for k in ('AGENT_DISABLE_ALL', 'AGENT_DIAGNOSTICIAN_ENABLED'):
            os.environ.pop(k, None)
        for mod in ('_agent_guardrails', '_agent_memory', 'repair_agent'):
            sys.modules.pop(mod, None)

    def test_summarize_clean_report(self):
        import repair_agent as ra
        report = {
            'status': 'CLEAN',
            'validated_at': '2026-05-12T19:00:00Z',
            'summary': {'total_checks': 100, 'passed': 100, 'failed': 0,
                        'critical_divergences': 0},
        }
        out = ra.summarize(report)
        self.assertIn('No findings', out)
        self.assertIn('CLEAN', out)

    def test_summarize_with_findings(self):
        import repair_agent as ra
        report = {
            'status': 'WARN',
            'validated_at': '2026-05-12T19:00:00Z',
            'summary': {'total_checks': 100, 'passed': 95, 'failed': 5,
                        'critical_divergences': 0},
            'staleness': [
                {'pass': False, 'severity': 'stale', 'check': 'pce.age',
                 'age_days': 95, 'max_lag_days': 60},
            ],
            'internal_consistency': [
                {'pass': False, 'severity': 'warning', 'check': 'kpi.cpi',
                 'note': 'small drift'},
            ],
        }
        out = ra.summarize(report)
        self.assertIn('Staleness', out)
        self.assertIn('Internal consistency', out)
        self.assertIn('pce.age', out)
        self.assertIn('95d old', out)

    def test_diagnose_findings_is_noop_when_disabled(self):
        # Diagnostician disabled by default.
        import repair_agent as ra
        report = {
            'status': 'WARN',
            'staleness': [{'pass': False, 'severity': 'stale',
                           'check': 'pce.age', 'age_days': 95,
                           'max_lag_days': 60}],
        }
        out = ra.diagnose_findings(report)
        self.assertEqual(out, '',
                         'diagnose_findings must return empty string when disabled')


# ──────────────────────────────────────────────────────────────────────
# Memory-aware diagnostician (recurrence detection)
# ──────────────────────────────────────────────────────────────────────

class TestRecurrenceHistory(unittest.TestCase):
    """Verify the recurrence helper reads observer log + prior incidents
    correctly. Pure file-IO; no LLM calls."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for mod in ('_agent_guardrails', '_agent_memory', 'repair_agent'):
            sys.modules.pop(mod, None)
        import repair_agent as ra
        self.ra = ra
        self._saved_log = ra.LOG_FILE
        self._saved_inc = ra.INCIDENT_DIR
        ra.LOG_FILE     = Path(self._tmp.name) / 'repair_log.md'
        ra.INCIDENT_DIR = Path(self._tmp.name) / 'incident_reports'
        ra.INCIDENT_DIR.mkdir()

    def tearDown(self):
        self.ra.LOG_FILE     = self._saved_log
        self.ra.INCIDENT_DIR = self._saved_inc

    def test_no_history_returns_zeros(self):
        h = self.ra._recurrence_history('pce.age')
        self.assertEqual(h['runs_seen_in'], 0)
        self.assertEqual(h['total_runs'], 0)
        self.assertIsNone(h['last_seen'])
        self.assertEqual(h['prior_recommendations'], [])

    def test_log_run_counting(self):
        self.ra.LOG_FILE.write_text(
            '## Repair Agent — 2026-05-12T10:00:00\n\n'
            'something pce.age 95d old\n\n'
            '---\n\n'
            '## Repair Agent — 2026-05-05T10:00:00\n\n'
            'something else pce.age 88d old\n\n'
            '---\n\n'
            '## Repair Agent — 2026-04-28T10:00:00\n\n'
            'unrelated\n\n',
            encoding='utf-8',
        )
        h = self.ra._recurrence_history('pce.age')
        self.assertEqual(h['total_runs'], 3)
        self.assertEqual(h['runs_seen_in'], 2)
        self.assertTrue(h['last_seen'].startswith('2026-05-12'))

    def test_prior_incidents_collected(self):
        (self.ra.INCIDENT_DIR / '2026-05-05.md').write_text(
            '# header\n\n### Finding: pce.age stale\n'
            '**Severity**: stale\n**Confidence**: medium\n'
            '**Root cause**: BEA publishes PCE with a long lag.\n'
            '**Playbook citation**: §2.2\n\n',
            encoding='utf-8',
        )
        h = self.ra._recurrence_history('pce.age')
        self.assertEqual(len(h['prior_recommendations']), 1)
        self.assertIn('§2.2', h['prior_recommendations'][0])

    def test_format_recurrence_first_time(self):
        h = {'runs_seen_in': 0, 'total_runs': 5, 'last_seen': None,
             'prior_recommendations': []}
        self.assertIn('First-time finding', self.ra._format_recurrence(h))

    def test_format_recurrence_recurring(self):
        h = {'runs_seen_in': 3, 'total_runs': 5, 'last_seen': '2026-05-12',
             'prior_recommendations': ['### Finding: X\n**Recommended**: foo']}
        s = self.ra._format_recurrence(h)
        self.assertIn('3 of last 5', s)
        self.assertIn('PRIOR DIAGNOSES', s)


# ──────────────────────────────────────────────────────────────────────
# Signal Rationales explainer (Phase 2)
# ──────────────────────────────────────────────────────────────────────

class TestSignalRationales(unittest.TestCase):

    def setUp(self):
        for k in ('AGENT_DISABLE_ALL', 'AGENT_EXPLAINER_ENABLED',
                  'ANTHROPIC_API_KEY'):
            os.environ.pop(k, None)
        for mod in ('_agent_guardrails', '_signal_rationales'):
            sys.modules.pop(mod, None)

    def test_disabled_by_default(self):
        import _signal_rationales as sr
        self.assertFalse(sr._is_enabled())

    def test_enabled_when_flags_set(self):
        os.environ['AGENT_EXPLAINER_ENABLED'] = '1'
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        import _signal_rationales as sr
        self.assertTrue(sr._is_enabled())

    def test_kill_switch_overrides_opt_in(self):
        os.environ['AGENT_DISABLE_ALL'] = '1'
        os.environ['AGENT_EXPLAINER_ENABLED'] = '1'
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        import _signal_rationales as sr
        self.assertFalse(sr._is_enabled())

    def test_flagged_signal_filter(self):
        import _signal_rationales as sr
        signals = {
            'ffr':       {'value': 3.64, 'flagged': False, 'alert': None},
            'unrate':    {'value': 4.5,  'flagged': True,  'alert': None},
            'cpi_yoy':   {'value': 3.5,  'flagged': False, 'alert': 'warning'},
            'noise':     'not-a-dict',
        }
        out = sr._flagged_signals(signals)
        names = [name for name, _ in out]
        self.assertIn('unrate', names)
        self.assertIn('cpi_yoy', names)
        self.assertNotIn('ffr', names)
        self.assertNotIn('noise', names)
        self.assertEqual(names[0], 'cpi_yoy')

    def test_raw_context_handles_missing_series(self):
        import _signal_rationales as sr
        s = sr._raw_context_for('nonexistent', {})
        self.assertIn('no raw_data', s)

    def test_raw_context_scalar_shape(self):
        import _signal_rationales as sr
        s = sr._raw_context_for('ffr', {'ffr': {'date': '2026-05-01', 'value': 3.64}})
        self.assertIn('3.64', s)
        self.assertIn('2026-05-01', s)

    def test_raw_context_list_shape(self):
        import _signal_rationales as sr
        series = [{'date': f'2026-0{i}-01', 'value': i} for i in range(1, 8)]
        s = sr._raw_context_for('series', {'series': series})
        self.assertIn('most recent 6', s)

    def test_extract_cite_finds_section(self):
        import _signal_rationales as sr
        self.assertEqual(sr._extract_cite('see §4.2 for details'), '§4.2')
        self.assertEqual(sr._extract_cite('matches §3 baseline'), '§3')
        self.assertEqual(sr._extract_cite('no citation here'), '')

    def test_output_path_on_allowlist(self):
        import _agent_guardrails as g
        g.assert_path_allowlisted('data/signal_rationales.json')


# ──────────────────────────────────────────────────────────────────────
# Memory inspector CLI
# ──────────────────────────────────────────────────────────────────────

class TestMemoryInspector(unittest.TestCase):

    def setUp(self):
        for mod in ('inspect_agent_memory',):
            sys.modules.pop(mod, None)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        import inspect_agent_memory as ins
        self._saved = ins.MEMORY_FILE
        ins.MEMORY_FILE = Path(self._tmp.name) / 'agent_memory.jsonl'
        self.ins = ins

    def tearDown(self):
        self.ins.MEMORY_FILE = self._saved

    def test_load_empty(self):
        self.assertEqual(self.ins.load_entries(), [])

    def test_aggregate_counts(self):
        rows = [
            {'agent': 'repair', 'purpose': 'diagnose:Staleness',
             'model': 'claude-sonnet-4-6',
             'usage': {'input_tokens': 100, 'output_tokens': 50}},
            {'agent': 'repair', 'purpose': 'diagnose:Schema',
             'model': 'claude-sonnet-4-6',
             'usage': {'input_tokens': 80, 'output_tokens': 40},
             'error': 'boom'},
            {'agent': 'explainer', 'purpose': 'explain:cpi',
             'model': 'claude-sonnet-4-6',
             'usage': {'input_tokens': 60, 'output_tokens': 30}},
        ]
        self.ins.MEMORY_FILE.write_text(
            '\n'.join(json.dumps(r) for r in rows) + '\n',
            encoding='utf-8',
        )
        entries = self.ins.load_entries()
        self.assertEqual(len(entries), 3)
        agg = self.ins.aggregate(entries)
        self.assertEqual(agg['total'], 3)
        self.assertEqual(agg['errors'], 1)
        self.assertEqual(agg['input_tokens'], 240)
        self.assertEqual(agg['output_tokens'], 120)
        self.assertEqual(agg['by_agent']['repair'], 2)
        self.assertEqual(agg['by_agent']['explainer'], 1)
        self.assertEqual(agg['by_purpose']['diagnose'], 2)
        self.assertEqual(agg['by_purpose']['explain'], 1)

    def test_fmt_entry_summary_vs_full(self):
        e = {'ts': 't', 'agent': 'a', 'purpose': 'p', 'model': 'm',
             'elapsed_sec': 0.1, 'usage': {'input_tokens': 5, 'output_tokens': 2},
             'system_truncated': 'SYS', 'prompt_truncated': 'PROMPT',
             'response': 'RESP'}
        short = self.ins.fmt_entry(e, full=False)
        self.assertIn('RESP', short)
        self.assertNotIn('SYS', short)
        full = self.ins.fmt_entry(e, full=True)
        self.assertIn('SYS', full)
        self.assertIn('PROMPT', full)
        self.assertIn('RESP', full)


if __name__ == '__main__':
    unittest.main(verbosity=2)
