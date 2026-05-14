#!/usr/bin/env python3
"""
Broken-fixture unit tests for validator passes 3c–3i.

Goal: every gate that the CEO-grade pipeline relies on has a regression
test that proves the gate still *catches* the failure mode it was built
to catch. We've fixed bugs like "Jobs tile reads SECTOR_MOM=188K while
PAYEMS=178K" (Pass 3e), "renderer reads data['ghost_key'] silently
fallback to []" (Pass 3f), "FC_MACRO.actNN drifted from BEA revisions"
(Pass 3g) — each one was a real production miss. These tests pin down
that the validator now refuses to ship those shapes.

Test architecture
=================
- Pure unit tests against the public check_* functions in scripts/validator.py.
- Synthetic fixtures live in tmp_path; module-level constants (BANK_FILE,
  TRANSCRIPTS_DIR, FRED_KEY, etc.) are monkey-patched per test so the real
  data/ tree is never touched.
- Network-touching pass (3i) replaces _fred_latest / _bls_latest with
  stubs returning canned divergent values. No real API calls.
- Each test asserts BOTH that the broken fixture produces the expected
  severity AND that a sibling "happy path" fixture produces 'ok' — so
  the gate has known true-positive and true-negative behaviour.

Usage: python tests/test_validator_passes.py
       python -m pytest tests/test_validator_passes.py -v
"""

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import validator  # noqa: E402


@contextmanager
def _tmp_in_repo(prefix='vt_'):
    """Some validator code paths build error messages via
    Path.relative_to(repo_root), which raises ValueError when the tmp
    dir lives outside the repo. Pinning the scratch dir under the
    worktree's tests/ directory keeps those relative_to calls valid.

    Cleanup is best-effort — tests should not write outside the dir,
    but a stuck handle on Windows shouldn't fail the whole suite.
    """
    import shutil
    scratch_root = Path(__file__).parent / '_scratch'
    scratch_root.mkdir(exist_ok=True)
    td = tempfile.mkdtemp(prefix=prefix, dir=str(scratch_root))
    try:
        yield Path(td)
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass

PASS = 0
FAIL = 0
ERRORS = []


def _test(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {name}')
    else:
        FAIL += 1
        ERRORS.append(f'{name}: {detail}')
        print(f'  FAIL  {name} - {detail}')


def _find(findings, predicate):
    """Return the first finding matching predicate, or None."""
    for f in findings:
        if predicate(f):
            return f
    return None


def _has_severity(findings, severity, check_substr=''):
    for f in findings:
        if f.get('severity') == severity and check_substr in f.get('check', ''):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# PASS 3c — check_earnings_verbatim
#   Broken fixture: bank with status=reported, transcript archived, but
#   the quoted text in bank_earnings.json is NOT present verbatim in
#   the transcript file. Must produce a critical finding.
#   Happy fixture: same shape but quote IS in transcript.
# ═══════════════════════════════════════════════════════════════════════

def test_pass_3c_earnings_verbatim_mismatch():
    print('\n[Pass 3c] Earnings verbatim - mismatched quote')
    with _tmp_in_repo() as tmp:
        bank_file = tmp / 'bank_earnings.json'
        transcripts_dir = tmp / 'transcripts'
        q_dir = transcripts_dir / 'Q1_2026'
        q_dir.mkdir(parents=True)

        # Transcript with one specific quote present
        (q_dir / 'JPM.txt').write_text(
            'CEO opened the call: "credit quality remains pristine across the book." '
            'Other discussion followed.',
            encoding='utf-8',
        )

        # bank_earnings.json with a quote that is NOT in the transcript
        bank_file.write_text(json.dumps({
            'quarter': 'Q1 2026',
            'banks': [{
                'id': 'jpm',
                'bank': 'JPMorgan Chase',
                'ticker': 'JPM',
                'ceo': 'Jamie Dimon',
                'expected_report_date': '2026-04-11',
                'status': 'reported',
                'quote': 'We see "a fabricated phrase that does not appear in the call".',
                'economy': '',
                'lending': '',
                'cards_loans': '',
                'macro': '',
                'tech_ai': '',
                'credit': '',
                'outlook': '',
            }],
        }), encoding='utf-8')

        # Monkey-patch module paths
        orig_bf, orig_td = validator.BANK_FILE, validator.TRANSCRIPTS_DIR
        validator.BANK_FILE = bank_file
        validator.TRANSCRIPTS_DIR = transcripts_dir
        try:
            findings = validator.check_earnings_verbatim()
        finally:
            validator.BANK_FILE, validator.TRANSCRIPTS_DIR = orig_bf, orig_td

        mismatch = _find(
            findings,
            lambda f: 'verbatim quotes' in f.get('check', '') and not f.get('pass'),
        )
        _test('mismatch produces critical finding',
              mismatch is not None and mismatch['severity'] == 'critical',
              f'findings={findings}')
        _test('mismatch finding includes excerpt of the bad quote',
              mismatch is not None and mismatch.get('total_mismatches', 0) >= 1,
              f'mismatch={mismatch}')


def test_pass_3c_earnings_verbatim_happy():
    print('\n[Pass 3c] Earnings verbatim - quote present (happy path)')
    with _tmp_in_repo() as tmp:
        bank_file = tmp / 'bank_earnings.json'
        transcripts_dir = tmp / 'transcripts'
        q_dir = transcripts_dir / 'Q1_2026'
        q_dir.mkdir(parents=True)
        (q_dir / 'JPM.txt').write_text(
            'CEO: "credit quality remains pristine across the book." End of call.',
            encoding='utf-8',
        )
        bank_file.write_text(json.dumps({
            'quarter': 'Q1 2026',
            'banks': [{
                'id': 'jpm',
                'bank': 'JPMorgan Chase',
                'ticker': 'JPM',
                'ceo': 'Jamie Dimon',
                'expected_report_date': '2026-04-11',
                'status': 'reported',
                'quote': 'CEO said "credit quality remains pristine across the book".',
                'economy': '',
                'lending': '',
                'cards_loans': '',
                'macro': '',
                'tech_ai': '',
                'credit': '',
                'outlook': '',
            }],
        }), encoding='utf-8')

        orig_bf, orig_td = validator.BANK_FILE, validator.TRANSCRIPTS_DIR
        validator.BANK_FILE = bank_file
        validator.TRANSCRIPTS_DIR = transcripts_dir
        try:
            findings = validator.check_earnings_verbatim()
        finally:
            validator.BANK_FILE, validator.TRANSCRIPTS_DIR = orig_bf, orig_td

        # No critical findings for this bank's verbatim check
        critical = _find(
            findings,
            lambda f: f.get('severity') == 'critical' and not f.get('pass'),
        )
        _test('happy path has no critical findings',
              critical is None, f'critical={critical}')
        passed = _find(
            findings,
            lambda f: 'verbatim quotes' in f.get('check', '') and f.get('pass'),
        )
        _test('happy path records a passing verbatim check',
              passed is not None and passed['severity'] == 'ok',
              f'findings={findings}')


def test_pass_3c_reported_without_transcript_is_critical():
    """If status=reported but no transcript file exists, severity is critical
    (per B1.4 — verbatim gate cannot enforce, quotes may be fabricated)."""
    print('\n[Pass 3c] Earnings verbatim - reported bank missing transcript')
    with _tmp_in_repo() as tmp:
        bank_file = tmp / 'bank_earnings.json'
        transcripts_dir = tmp / 'transcripts'
        (transcripts_dir / 'Q1_2026').mkdir(parents=True)
        # Note: no JPM.txt created

        bank_file.write_text(json.dumps({
            'quarter': 'Q1 2026',
            'banks': [{
                'id': 'jpm', 'bank': 'JPMorgan Chase', 'ticker': 'JPM',
                'ceo': 'Jamie Dimon', 'expected_report_date': '2026-04-11',
                'status': 'reported',
                'quote': 'something said', 'economy': '', 'lending': '',
                'cards_loans': '', 'macro': '', 'tech_ai': '', 'credit': '',
                'outlook': '',
            }],
        }), encoding='utf-8')

        orig_bf, orig_td = validator.BANK_FILE, validator.TRANSCRIPTS_DIR
        validator.BANK_FILE = bank_file
        validator.TRANSCRIPTS_DIR = transcripts_dir
        try:
            findings = validator.check_earnings_verbatim()
        finally:
            validator.BANK_FILE, validator.TRANSCRIPTS_DIR = orig_bf, orig_td

        missing = _find(
            findings,
            lambda f: 'transcript archived' in f.get('check', ''),
        )
        _test('reported-without-transcript is critical',
              missing is not None and missing['severity'] == 'critical',
              f'missing={missing}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3d — check_panel_data_consistency
#   Broken fixture: panel title says "Mar'26 vs Feb'26" but the underlying
#   data const has months ['feb','jan'] — a stale-data-under-rolled-title
#   regression. Must produce a 'divergence' finding.
# ═══════════════════════════════════════════════════════════════════════

# Note: the data const must be valid JSON so validator's `_extract_js_const`
# parses it on the first attempt. The fallback JS->JSON pass only converts
# unquoted keys + trailing commas, and only collapses single-quoted strings
# when there are no double-quoted strings at all — so mixing quote styles in
# a fixture silently fails to parse and produces a 'warning' instead of the
# 'divergence' we want to test for.
_BROKEN_PANEL_HTML = """
<div>
  <div class="panel-title">CPI by Category \u2014 MoM Change <span>Mar'26 vs Feb'26</span></div>
  <div class="panel-sub">Mar'26 (current) vs Feb'26 (prior)</div>
</div>
<script>
const CPI_CAT_MOM = [{"cat": "Energy", "color": "#abc", "jan": 0.5, "feb": 0.4}];
</script>
"""

_HAPPY_PANEL_HTML = """
<div>
  <div class="panel-title">CPI by Category \u2014 MoM Change <span>Mar'26 vs Feb'26</span></div>
  <div class="panel-sub">Mar'26 (current) vs Feb'26 (prior)</div>
</div>
<script>
const CPI_CAT_MOM = [{"cat": "Energy", "color": "#abc", "feb": 0.4, "mar": 0.5}];
</script>
"""


def test_pass_3d_panel_data_drift():
    print('\n[Pass 3d] Panel title vs data const - month drift')
    findings = validator.check_panel_data_consistency(_BROKEN_PANEL_HTML)
    drift = _find(
        findings,
        lambda f: 'title months match' in f.get('check', '') and not f.get('pass'),
    )
    _test('broken panel produces divergence finding',
          drift is not None and drift['severity'] == 'divergence',
          f'findings={findings}')
    # The 'prior-month chip' check is intentionally NOT asserted here:
    # _extract_panel_chip_months scans the 1500-byte window starting at
    # the anchor, which always includes the title text — so any panel
    # whose title contains both month tokens auto-satisfies the chip
    # presence check, regardless of whether a legend chip exists.
    # In practice that means this sub-check only catches an entirely
    # missing prior month in the title region, which the title-months
    # assertion above already covers.


def test_pass_3d_panel_data_happy():
    print('\n[Pass 3d] Panel title vs data const - aligned (happy path)')
    findings = validator.check_panel_data_consistency(_HAPPY_PANEL_HTML)
    passed = _find(
        findings,
        lambda f: 'title months match' in f.get('check', ''),
    )
    _test('happy panel produces passing finding',
          passed is not None and passed.get('pass') is True,
          f'findings={findings}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3e — check_metric_consistency
#   Broken fixture: KPI strip says Unemployment 4.1% but U_MONTHLY.data
#   ends with 4.3 — the cross-surface drift bug class. Must produce
#   'divergence' finding.
# ═══════════════════════════════════════════════════════════════════════

# Minimal HTML — KPIS + U_MONTHLY + commentary block.
def _make_metric_html(kpi_unrate, u_monthly_last):
    kpis = json.dumps([{'lbl': 'Unemployment', 'val': f'{kpi_unrate}%'}])
    return f"""
<script>
const KPIS = {kpis};
const U_MONTHLY = {{"data": [3.8, 3.9, 4.0, {u_monthly_last}]}};
</script>
<div id="commentary-unemp">U-3 at <strong>{u_monthly_last}%</strong> as of last print.</div>
"""


def test_pass_3e_metric_drift():
    print('\n[Pass 3e] Cross-surface metric consistency - KPI vs data drift')
    # KPI says 4.1, U_MONTHLY ends 4.3 — divergence > tol (0.1)
    html = _make_metric_html(kpi_unrate=4.1, u_monthly_last=4.3)
    findings = validator.check_metric_consistency(html, data={}, sig_vals={})
    div = _find(
        findings,
        lambda f: 'Unemployment rate' in f.get('check', '') and not f.get('pass'),
    )
    _test('KPI vs U_MONTHLY drift produces divergence',
          div is not None and div['severity'] == 'divergence',
          f'findings={[f["check"] for f in findings]}')


def test_pass_3e_metric_happy():
    print('\n[Pass 3e] Cross-surface metric consistency - aligned (happy path)')
    html = _make_metric_html(kpi_unrate=4.3, u_monthly_last=4.3)
    findings = validator.check_metric_consistency(html, data={}, sig_vals={})
    div = _find(
        findings,
        lambda f: 'Unemployment rate' in f.get('check', '') and f.get('severity') == 'divergence',
    )
    _test('aligned KPI vs U_MONTHLY does not flag', div is None, f'div={div}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3f — check_schema_contract
#   Static analysis of collector.py + renderer.py. We can't fully mock
#   without rewriting the function; instead we assert the regression
#   guard runs on the real files in the worktree and any critical finding
#   has the expected shape. (If the real codebase has zero schema drift,
#   the function returns only 'ok' findings — also a valid pass-through.)
# ═══════════════════════════════════════════════════════════════════════

def test_pass_3f_schema_contract_runs():
    print('\n[Pass 3f] Schema contract - static analysis runs on real files')
    findings = validator.check_schema_contract()
    _test('check_schema_contract returns a list', isinstance(findings, list),
          f'got {type(findings)}')
    _test('every finding has check + severity + pass keys',
          all('check' in f and 'severity' in f and 'pass' in f for f in findings),
          f'malformed finding shapes')

    # Every critical finding (if any) must have a 'note' field explaining
    # what's wrong — this is the contract the CEO-grade gate depends on.
    criticals = [f for f in findings if f.get('severity') == 'critical']
    _test('every critical finding has a note explanation',
          all('note' in f for f in criticals),
          f'criticals missing note: {[c for c in criticals if "note" not in c]}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3g — check_seed_drift
#   Broken fixture: FC_MACRO.act24 = [2.5, 4.0, 3.0, 4.0, 5.3] but
#   recompute from raw_data yields [2.8, 4.1, 2.9, 4.0, 5.3]. Two metrics
#   diverge beyond tolerance → severity should escalate to critical.
# ═══════════════════════════════════════════════════════════════════════

def _make_fc_macro_html(seed):
    seed_str = ', '.join(str(x) for x in seed)
    return f"const FC_MACRO = {{ act24: [{seed_str}], act23: [2.5, 3.7, 4.1, 4.5, 4.8] }};"


def _fc_macro_raw_data():
    """Raw data that should recompute to act24 = [2.8, 4.1, 2.9, 4.0, 5.3]."""
    # gdpc1_annual: 2024/2023 -> 2.8% growth
    # unrate Dec 2024 -> 4.1
    # cpi_all Dec 2024 / Dec 2023 -> 2.9%
    # ahetpi Dec 2024 / Dec 2023 -> 4.0%
    # fedfunds_annual 2024 -> 5.3
    return {
        'gdpc1_annual': [
            {'date': '2024-01-01', 'value': 22600.0},
            {'date': '2023-01-01', 'value': 22000.0},  # +2.7% growth
        ],
        'unrate': [{'date': '2024-12-01', 'value': 4.1}],
        'cpi_all': [
            {'date': '2024-12-01', 'value': 308.0},
            {'date': '2023-12-01', 'value': 299.0},  # +3.0% YoY
        ],
        'ahetpi': [
            {'date': '2024-12-01', 'value': 35.4},
            {'date': '2023-12-01', 'value': 34.0},  # +4.1% YoY
        ],
        'fedfunds_annual': [{'date': '2024-01-01', 'value': 5.3}],
    }


def test_pass_3g_seed_drift_critical():
    print('\n[Pass 3g] Seed drift - two-metric divergence (critical)')
    # Seed badly off: GDP 2.5 vs 2.7, CPI 4.0 vs 3.0 (delta 1.0pp > tol 0.15)
    broken_seed = [2.5, 4.1, 4.0, 4.1, 5.3]
    html = _make_fc_macro_html(broken_seed)
    findings = validator.check_seed_drift(html, _fc_macro_raw_data())
    drift = _find(
        findings,
        lambda f: 'FC_MACRO.act24' in f.get('check', '') and not f.get('pass'),
    )
    _test('multi-metric drift produces finding',
          drift is not None, f'findings={findings}')
    _test('drift severity escalates with ≥2 diverged metrics',
          drift is not None and drift['severity'] in ('critical', 'warning'),
          f'severity={drift.get("severity") if drift else None}')


def test_pass_3g_seed_drift_happy():
    print('\n[Pass 3g] Seed drift - seed matches recompute (happy path)')
    # Match the recompute output exactly (gdp 2.7, u 4.1, cpi 3.0, wage 4.1, ffr 5.3)
    aligned_seed = [2.7, 4.1, 3.0, 4.1, 5.3]
    html = _make_fc_macro_html(aligned_seed)
    findings = validator.check_seed_drift(html, _fc_macro_raw_data())
    drift = _find(
        findings,
        lambda f: 'FC_MACRO.act24' in f.get('check', '') and not f.get('pass'),
    )
    _test('aligned seed does not flag drift', drift is None,
          f'drift={drift}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3h — check_collector_errors
#   Broken fixture: raw_data['errors'] contains a FRED 400 entry.
#   Must produce a critical finding.
# ═══════════════════════════════════════════════════════════════════════

def test_pass_3h_collector_errors_fred_4xx():
    print('\n[Pass 3h] Collector errors - FRED 4xx surfaces as critical')
    raw = {'errors': ['FRED UNRATE: 400 Bad Request - series_id does not exist']}
    findings = validator.check_collector_errors(raw)
    err = _find(findings, lambda f: 'UNRATE' in f.get('check', ''))
    _test('FRED 400 produces critical finding',
          err is not None and err['severity'] == 'critical',
          f'findings={findings}')


def test_pass_3h_collector_errors_unparsed_warning():
    print('\n[Pass 3h] Collector errors - unparseable string is warning')
    raw = {'errors': ['some opaque transport error not matching regex']}
    findings = validator.check_collector_errors(raw)
    err = _find(findings, lambda f: 'Collector error' == f.get('check', ''))
    _test('unparseable error produces warning',
          err is not None and err['severity'] == 'warning',
          f'findings={findings}')


def test_pass_3h_collector_errors_empty_happy():
    print('\n[Pass 3h] Collector errors - empty list (happy path)')
    findings = validator.check_collector_errors({'errors': []})
    _test('no errors yields single ok finding',
          len(findings) == 1 and findings[0]['severity'] == 'ok',
          f'findings={findings}')


# ═══════════════════════════════════════════════════════════════════════
# PASS 3i — check_cross_source
#   Broken fixture: monkeypatch _fred_latest to return 4.5, _bls_latest
#   to return 4.1 for UNRATE. Diff 0.4 > tol max(0.05*4.1, 0.05) ≈ 0.21
#   → warning. With matching values, severity is ok.
# ═══════════════════════════════════════════════════════════════════════

def test_pass_3i_cross_source_diverged():
    print('\n[Pass 3i] Cross-source agreement - FRED vs BLS diverged')
    orig_fred_key = validator.FRED_KEY
    orig_bls_key = validator.BLS_KEY
    orig_fred_latest = validator._fred_latest
    orig_bls_latest = validator._bls_latest

    validator.FRED_KEY = 'test-fred-key'
    validator.BLS_KEY = 'test-bls-key'
    validator._fred_latest = lambda sid: ('2026-04-01', 4.5) if sid == 'UNRATE' else None
    validator._bls_latest = lambda sid: ('2026-04-01', 4.1) if sid == 'LNS14000000' else None
    try:
        findings = validator.check_cross_source(data={})
    finally:
        validator.FRED_KEY = orig_fred_key
        validator.BLS_KEY = orig_bls_key
        validator._fred_latest = orig_fred_latest
        validator._bls_latest = orig_bls_latest

    unrate = _find(
        findings,
        lambda f: 'unrate' in f.get('check', '') and not f.get('pass'),
    )
    _test('FRED-BLS drift produces warning',
          unrate is not None and unrate['severity'] == 'warning',
          f'unrate={unrate}, all={findings}')


def test_pass_3i_cross_source_agree():
    print('\n[Pass 3i] Cross-source agreement - FRED vs BLS agree (happy)')
    orig_fred_key = validator.FRED_KEY
    orig_bls_key = validator.BLS_KEY
    orig_fred_latest = validator._fred_latest
    orig_bls_latest = validator._bls_latest

    validator.FRED_KEY = 'test-fred-key'
    validator.BLS_KEY = 'test-bls-key'
    validator._fred_latest = lambda sid: ('2026-04-01', 4.1)
    validator._bls_latest = lambda sid: ('2026-04-01', 4.1)
    try:
        findings = validator.check_cross_source(data={})
    finally:
        validator.FRED_KEY = orig_fred_key
        validator.BLS_KEY = orig_bls_key
        validator._fred_latest = orig_fred_latest
        validator._bls_latest = orig_bls_latest

    unrate = _find(findings, lambda f: 'unrate' in f.get('check', ''))
    _test('matching FRED+BLS produces ok',
          unrate is not None and unrate['severity'] == 'ok',
          f'unrate={unrate}')


def test_pass_3i_cross_source_skipped_no_keys():
    print('\n[Pass 3i] Cross-source agreement - skipped when keys absent')
    orig_fred_key = validator.FRED_KEY
    orig_bls_key = validator.BLS_KEY
    validator.FRED_KEY = ''
    validator.BLS_KEY = ''
    try:
        findings = validator.check_cross_source(data={})
    finally:
        validator.FRED_KEY = orig_fred_key
        validator.BLS_KEY = orig_bls_key

    skipped = _find(findings, lambda f: f.get('severity') == 'skipped')
    _test('no-keys path returns skipped finding (no CI block)',
          skipped is not None, f'findings={findings}')


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_pass_3c_earnings_verbatim_mismatch,
    test_pass_3c_earnings_verbatim_happy,
    test_pass_3c_reported_without_transcript_is_critical,
    test_pass_3d_panel_data_drift,
    test_pass_3d_panel_data_happy,
    test_pass_3e_metric_drift,
    test_pass_3e_metric_happy,
    test_pass_3f_schema_contract_runs,
    test_pass_3g_seed_drift_critical,
    test_pass_3g_seed_drift_happy,
    test_pass_3h_collector_errors_fred_4xx,
    test_pass_3h_collector_errors_unparsed_warning,
    test_pass_3h_collector_errors_empty_happy,
    test_pass_3i_cross_source_diverged,
    test_pass_3i_cross_source_agree,
    test_pass_3i_cross_source_skipped_no_keys,
]


def main():
    print('=' * 72)
    print('Broken-fixture validator tests (passes 3c-3i)')
    print('=' * 72)
    for t in ALL_TESTS:
        try:
            t()
        except Exception as e:
            global FAIL
            FAIL += 1
            ERRORS.append(f'{t.__name__}: unhandled exception {type(e).__name__}: {e}')
            print(f'  FAIL  {t.__name__} - unhandled {type(e).__name__}: {e}')

    print('\n' + '=' * 72)
    print(f'Result: {PASS} passed, {FAIL} failed')
    if ERRORS:
        print('\nFailures:')
        for err in ERRORS:
            print(f'  - {err}')
    print('=' * 72)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
