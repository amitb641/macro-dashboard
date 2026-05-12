#!/usr/bin/env python3
"""
Tests for the CEO-grade layers shipped on top of the agentic foundation:

  - scripts/_editorial_review.py — deterministic linters + schema
  - scripts/ceo_grade_gate.py    — verdict aggregation
  - bounded_llm_call(validator=) — zero-fail-rate hook

No real LLM calls; tests use the validator hook to reject everything
or use the disabled-by-default code path.

Usage: python tests/test_ceo_grade.py
       python -m pytest tests/test_ceo_grade.py -v
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


class TestEditorialLinters(unittest.TestCase):
    """Deterministic linter passes — zero LLM, zero false positives."""

    def setUp(self):
        for mod in ('_agent_guardrails', '_editorial_review'):
            sys.modules.pop(mod, None)
        import _editorial_review as er
        self.er = er

    def test_sentence_count_strips_decimals(self):
        # "$3.5B" is one sentence, not three.
        self.assertEqual(self.er._sentence_count('Latest WTI is $109.8 today.'), 1)
        self.assertEqual(self.er._sentence_count('One. Two. Three.'), 3)
        self.assertEqual(self.er._sentence_count('Long sentence with no period'), 0)

    def test_lint_length_in_band(self):
        text = 'One sentence. Two sentence. Three sentence.'
        self.assertIsNone(self.er.lint_length(text))

    def test_lint_length_too_short(self):
        out = self.er.lint_length('Just one sentence here.')
        self.assertIsNotNone(out)
        self.assertEqual(out['severity'], 'warning')

    def test_lint_length_zero_sentences_is_critical(self):
        out = self.er.lint_length('no terminator')
        self.assertEqual(out['severity'], 'critical')

    def test_lint_length_too_long(self):
        text = 'A. B. C. D. E. F.'  # 6 sentences
        out = self.er.lint_length(text)
        self.assertIsNotNone(out)
        self.assertEqual(out['severity'], 'warning')

    def test_lint_forbidden_vocab_detects(self):
        text = 'In my opinion, perhaps things will change. We see a number of trends.'
        out = self.er.lint_forbidden_vocab(text)
        rules = {f['rule'] for f in out}
        # All four forbidden phrases tripped.
        self.assertTrue(any('forbidden' in r for r in rules))
        self.assertGreaterEqual(len(out), 3)

    def test_lint_hedging_filler_detects(self):
        text = 'This may potentially indicate stress. Inflation might possibly accelerate.'
        out = self.er.lint_forbidden_vocab(text)
        hedge_rules = [f for f in out if 'hedging' in f['rule']]
        self.assertGreaterEqual(len(hedge_rules), 2)

    def test_lint_no_fabricated_numerics_pass(self):
        raw = {'gasoline': [{'date': '2026-05-01', 'value': 4.5}]}
        vals = {'wti': 109.8}
        # Both numbers appear in raw/vals → no findings.
        text = 'WTI at $109.8 and gas at $4.50 today.'
        out = self.er.lint_no_fabricated_numerics(text, raw, vals)
        self.assertEqual(out, [])

    def test_lint_no_fabricated_numerics_flags_unsupported(self):
        raw = {'gasoline': [{'value': 4.5}]}
        vals = {'wti': 109.8}
        # 250 doesn't appear anywhere → suspicious.
        text = 'Inflation surged to 250% this month, breaking records.'
        out = self.er.lint_no_fabricated_numerics(text, raw, vals)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]['severity'], 'critical')

    def test_lint_no_fabricated_numerics_tolerates_rounding(self):
        raw = {'cpi': [{'value': 109.83}]}
        # Commentary says "$110" — raw is 109.83. Within tolerance.
        text = 'Print landed at 110 this morning.'
        out = self.er.lint_no_fabricated_numerics(text, raw, {})
        # 110 is within ~1% of 109.83, so tolerated.
        self.assertEqual(out, [])

    def test_audit_validator_accepts_well_formed(self):
        good = json.dumps({
            'tone_ok': True, 'factually_grounded': True,
            'issues': [], 'confidence': 'high',
        })
        self.assertTrue(self.er._audit_validator(good))

    def test_audit_validator_rejects_missing_keys(self):
        bad = json.dumps({'tone_ok': True})  # missing fields
        self.assertFalse(self.er._audit_validator(bad))

    def test_audit_validator_rejects_bad_json(self):
        self.assertFalse(self.er._audit_validator('not json'))
        self.assertFalse(self.er._audit_validator('{not json'))

    def test_audit_validator_rejects_bad_confidence(self):
        bad = json.dumps({
            'tone_ok': True, 'factually_grounded': True,
            'issues': [], 'confidence': 'super-high',
        })
        self.assertFalse(self.er._audit_validator(bad))


class TestBoundedLLMValidatorHook(unittest.TestCase):
    """bounded_llm_call validator-hook contract — when validator rejects,
    function returns None instead of raising. Caller-level zero-fail."""

    def setUp(self):
        for k in ('AGENT_DISABLE_ALL',):
            os.environ.pop(k, None)
        os.environ['ANTHROPIC_API_KEY'] = 'sk-test'
        for mod in ('_agent_guardrails', '_agent_memory'):
            sys.modules.pop(mod, None)

    def tearDown(self):
        os.environ.pop('ANTHROPIC_API_KEY', None)

    def test_validator_signature_present(self):
        """The function must accept a `validator` kwarg (the contract)."""
        import inspect
        import _agent_guardrails as g
        sig = inspect.signature(g.bounded_llm_call)
        self.assertIn('validator', sig.parameters)

    def test_returns_none_when_killed_regardless_of_validator(self):
        os.environ['AGENT_DISABLE_ALL'] = '1'
        for mod in ('_agent_guardrails',):
            sys.modules.pop(mod, None)
        import _agent_guardrails as g
        out = g.bounded_llm_call(
            'p', system='s', model='claude-sonnet-4-6',
            purpose='test', validator=lambda x: True,
        )
        self.assertIsNone(out)


class TestCEOGradeGateAggregation(unittest.TestCase):
    """Aggregation logic across layers — pure dict shuffling, no IO."""

    def setUp(self):
        for mod in ('ceo_grade_gate',):
            sys.modules.pop(mod, None)
        import ceo_grade_gate as g
        self.g = g

    def test_summarize_buckets_severities(self):
        findings = [
            {'severity': 'critical', 'pass': False},
            {'severity': 'warning',  'pass': False},
            {'severity': 'warning',  'pass': False},
            {'severity': 'ok',       'pass': True},
            {'severity': 'skipped'},
            {'severity': 'divergence', 'pass': False},  # treated as critical
        ]
        s = self.g._summarize_findings(findings)
        self.assertEqual(s['critical'], 2)
        self.assertEqual(s['warning'], 2)
        self.assertEqual(s['skipped'], 1)
        self.assertEqual(s['ok'], 1)
        self.assertEqual(s['total'], 6)

    def test_verdict_promotes_critical_to_fail(self):
        s = self.g._summarize_findings([
            {'severity': 'critical', 'pass': False},
            {'severity': 'warning',  'pass': False},
        ])
        v = self.g._verdict_from(s, layer='x')
        self.assertEqual(v['status'], 'FAIL')

    def test_verdict_warn_when_only_warnings(self):
        s = self.g._summarize_findings([
            {'severity': 'warning', 'pass': False},
        ])
        v = self.g._verdict_from(s, layer='x')
        self.assertEqual(v['status'], 'WARN')

    def test_verdict_pass_when_clean(self):
        s = self.g._summarize_findings([
            {'severity': 'ok', 'pass': True},
            {'severity': 'ok', 'pass': True},
        ])
        v = self.g._verdict_from(s, layer='x')
        self.assertEqual(v['status'], 'PASS')

    def test_build_verdict_handles_missing_layers(self):
        # When every assessor returns None (no artifacts exist), the
        # overall verdict is SKIP. Patch the assessors to all return None.
        original = self.g.LAYER_ASSESSORS
        try:
            self.g.LAYER_ASSESSORS = [
                (label, lambda: None) for label, _ in original
            ]
            v = self.g.build_verdict()
            self.assertEqual(v['overall'], 'SKIP')
            self.assertIn('missing', v)
            self.assertEqual(len(v['missing']), len(original))
        finally:
            self.g.LAYER_ASSESSORS = original

    def test_build_verdict_fail_dominates(self):
        original = self.g.LAYER_ASSESSORS
        try:
            self.g.LAYER_ASSESSORS = [
                ('a', lambda: {'layer': 'a', 'status': 'PASS', 'critical': 0, 'warning': 0, 'skipped': 0, 'total': 0}),
                ('b', lambda: {'layer': 'b', 'status': 'FAIL', 'critical': 1, 'warning': 0, 'skipped': 0, 'total': 1}),
                ('c', lambda: {'layer': 'c', 'status': 'WARN', 'critical': 0, 'warning': 3, 'skipped': 0, 'total': 3}),
            ]
            v = self.g.build_verdict()
            self.assertEqual(v['overall'], 'FAIL')
            self.assertEqual(v['totals']['critical'], 1)
            self.assertEqual(v['totals']['warning'], 3)
        finally:
            self.g.LAYER_ASSESSORS = original

    def test_strict_mode_promotes_warn_to_fail(self):
        original = self.g.LAYER_ASSESSORS
        try:
            self.g.LAYER_ASSESSORS = [
                ('a', lambda: {'layer': 'a', 'status': 'WARN', 'critical': 0, 'warning': 1, 'skipped': 0, 'total': 1}),
            ]
            v_lax    = self.g.build_verdict(strict=False)
            v_strict = self.g.build_verdict(strict=True)
            self.assertEqual(v_lax['overall'], 'WARN')
            self.assertEqual(v_strict['overall'], 'FAIL')
        finally:
            self.g.LAYER_ASSESSORS = original


class TestCEOGradeGateAssessors(unittest.TestCase):
    """Smoke-test each per-layer assessor with synthetic artifacts."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)
        for mod in ('ceo_grade_gate',):
            sys.modules.pop(mod, None)
        import ceo_grade_gate as g
        self.g = g
        self._saved = (g.VALIDATOR_REPORT, g.VISUAL_QA_REPORT,
                       g.VISION_REVIEW_REPORT, g.EDITORIAL_REPORT,
                       g.INCIDENT_DIR)

    def tearDown(self):
        (self.g.VALIDATOR_REPORT, self.g.VISUAL_QA_REPORT,
         self.g.VISION_REVIEW_REPORT, self.g.EDITORIAL_REPORT,
         self.g.INCIDENT_DIR) = self._saved

    def test_assess_validator_pass(self):
        path = self.tmpdir / 'v.json'
        path.write_text(json.dumps({
            'status': 'PASS',
            'summary': {'total_checks': 10, 'passed': 10, 'failed': 0,
                        'skipped': 0, 'critical_divergences': 0},
        }))
        self.g.VALIDATOR_REPORT = path
        v = self.g.assess_validator()
        self.assertEqual(v['status'], 'PASS')

    def test_assess_validator_fail_with_critical(self):
        path = self.tmpdir / 'v.json'
        path.write_text(json.dumps({
            'status': 'FAIL',
            'summary': {'total_checks': 10, 'passed': 7, 'failed': 3,
                        'skipped': 0, 'critical_divergences': 2},
        }))
        self.g.VALIDATOR_REPORT = path
        v = self.g.assess_validator()
        self.assertEqual(v['status'], 'FAIL')
        self.assertEqual(v['critical'], 2)

    def test_assess_editorial_aggregates_findings(self):
        path = self.tmpdir / 'e.json'
        path.write_text(json.dumps({
            'pieces_audited': 3,
            'pieces': [
                {'findings': [{'severity': 'warning'}]},
                {'findings': [{'severity': 'critical'}]},
                {'findings': []},
            ],
        }))
        self.g.EDITORIAL_REPORT = path
        v = self.g.assess_editorial()
        self.assertEqual(v['status'], 'FAIL')
        self.assertEqual(v['critical'], 1)
        self.assertEqual(v['warning'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
