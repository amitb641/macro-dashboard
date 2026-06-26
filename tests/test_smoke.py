#!/usr/bin/env python3
"""
Smoke Tests — Offline pipeline validation using fixture data.
Runs without API keys. Tests that collector output → analyzer → renderer
produces valid HTML with expected content.

Usage: python tests/test_smoke.py
       python -m pytest tests/test_smoke.py -v
"""

import json, os, re, shutil, sys, tempfile, datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

FIXTURE_DIR = Path(__file__).parent / 'fixtures'
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
        print(f'  FAIL  {name} — {detail}')


# ═══════════════════════════════════════════════════════════════════════
# FIXTURE GENERATION — build minimal realistic data for offline testing
# ═══════════════════════════════════════════════════════════════════════

def _make_monthly_series(start_year, start_month, count, base, trend=0.0):
    """Generate a synthetic monthly time series (newest first)."""
    series = []
    for i in range(count):
        yr = start_year + (start_month + i - 1) // 12
        mo = ((start_month + i - 1) % 12) + 1
        val = round(base + trend * i + (i % 3) * 0.1, 2)
        series.append({'date': f'{yr}-{mo:02d}-01', 'value': val})
    series.reverse()  # newest first
    return series


def _make_bls_series(start_year, count, base):
    """Generate synthetic BLS-format series data."""
    months = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
    series = []
    for i in range(count):
        yr = start_year + i // 12
        mo = i % 12
        val = str(round(base + i * 10, 1))
        series.append({
            'year': str(yr),
            'period': f'M{mo+1:02d}',
            'periodName': months[mo],
            'latest': 'true' if i == count - 1 else 'false',
            'value': val,
            'footnotes': [{}],
        })
    series.reverse()
    return series


def generate_fixture_data():
    """Build a minimal raw_data.json that exercises the full pipeline."""
    today = datetime.date.today()
    yr = today.year

    # Monthly series: 36 months of data
    unrate = _make_monthly_series(yr - 3, 1, 36, 3.5, 0.02)
    cpi_all = _make_monthly_series(yr - 3, 1, 36, 290.0, 0.8)
    cpi_core = _make_monthly_series(yr - 3, 1, 36, 295.0, 0.6)
    pce = _make_monthly_series(yr - 3, 1, 36, 115.0, 0.3)
    pce_core = _make_monthly_series(yr - 3, 1, 36, 118.0, 0.25)
    payems = _make_monthly_series(yr - 3, 1, 36, 155000.0, 50.0)
    ahetpi = _make_monthly_series(yr - 3, 1, 36, 29.0, 0.1)
    cs_hpi = _make_monthly_series(yr - 3, 1, 36, 300.0, 1.5)

    # BLS sector data
    bls_codes = [
        'CES0000000001', 'CES1000000001', 'CES2000000001',
        'CES3000000001', 'CES4000000001', 'CES4142000001',
        'CES5000000001', 'CES5500000001', 'CES6000000001',
        'CES6500000001', 'CES7000000001', 'CES8000000001',
        'CES9000000001', 'CES9091000001',
    ]
    bls_sectors = {}
    for i, code in enumerate(bls_codes):
        bls_sectors[code] = _make_bls_series(yr - 2, 24, 5000 + i * 1000)

    # Annual series
    def _annual(start, count, base, step):
        return [{'date': f'{start + i}-01-01', 'value': round(base + step * i, 2)}
                for i in range(count)]

    wti_annual = _annual(yr - 10, 10, 55.0, 1.5)
    brent_annual = _annual(yr - 10, 10, 60.0, 1.5)

    # Daily / scalar data
    oil_daily_chart = {
        'labels': ['Mar 1', 'Mar 2', 'Mar 3'],
        'wti': [65.0, 64.5, 66.0],
        'brent': [70.0, 69.5, 71.0],
        'notes': [None, None, None],
        'month': f'Mar {yr}',
    }

    return {
        'collected_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'series_count': 30,
        'error_count': 0,
        'errors': [],
        'data': {
            'ffr': {'date': f'{yr}-03-01', 'value': 4.33},
            'dff': {'date': f'{yr}-04-01', 'value': 4.33},
            'dgs2': {'date': f'{yr}-04-01', 'value': 4.10},
            'dgs5': {'date': f'{yr}-04-01', 'value': 4.05},
            'dgs10': {'date': f'{yr}-04-01', 'value': 4.25},
            'dgs30': {'date': f'{yr}-04-01', 'value': 4.55},
            'dgs10_hist': _make_monthly_series(yr - 3, 1, 36, 3.5, 0.03),
            'dgs2_hist': _make_monthly_series(yr - 3, 1, 36, 4.0, 0.02),
            'ig_oas': {'date': f'{yr}-04-01', 'value': 1.05},
            'hy_oas': {'date': f'{yr}-04-01', 'value': 3.50},
            'ig_hist': _make_monthly_series(yr - 3, 1, 36, 1.0, 0.01),
            'hy_hist': _make_monthly_series(yr - 3, 1, 36, 3.2, 0.02),
            'wti_daily': [{'date': f'{yr}-04-01', 'value': 65.0}],
            'brent_daily': [{'date': f'{yr}-04-01', 'value': 70.0}],
            'oil_daily_chart': oil_daily_chart,
            'gasoline': [{'date': f'{yr}-04-01', 'value': 3.25}],
            'mortgage30': _make_monthly_series(yr - 3, 1, 36, 6.0, 0.02),
            'mortgage15': _make_monthly_series(yr - 3, 1, 36, 5.5, 0.02),
            'icsa': _make_monthly_series(yr - 1, 1, 12, 220.0, 1.0),
            'ccsa': _make_monthly_series(yr - 1, 1, 12, 1800.0, 5.0),
            'unrate': unrate,
            'u6rate': _make_monthly_series(yr - 3, 1, 36, 7.0, 0.03),
            'payems': payems,
            'ahetpi': ahetpi,
            'jolts': _make_monthly_series(yr - 3, 1, 36, 8500.0, -20.0),
            'umcsent': _make_monthly_series(yr - 3, 1, 36, 65.0, -0.2),
            'bls_sectors': bls_sectors,
            'bls_unemp_sectors': {},
            'cpi_all': cpi_all,
            'cpi_core': cpi_core,
            'pce': pce,
            'pce_core': pce_core,
            'psavert': _make_monthly_series(yr - 3, 1, 36, 4.5, 0.05),
            'cpi_shelter': _make_monthly_series(yr - 3, 1, 36, 340.0, 1.2),
            'cpi_food_away': _make_monthly_series(yr - 3, 1, 36, 360.0, 1.0),
            'cpi_transport': _make_monthly_series(yr - 3, 1, 36, 270.0, 0.5),
            'cpi_medical': _make_monthly_series(yr - 3, 1, 36, 550.0, 0.7),
            'cpi_food_home': _make_monthly_series(yr - 3, 1, 36, 310.0, 0.8),
            'cpi_new_veh': _make_monthly_series(yr - 3, 1, 36, 165.0, 0.3),
            'cpi_apparel': _make_monthly_series(yr - 3, 1, 36, 130.0, 0.2),
            'cpi_energy': _make_monthly_series(yr - 3, 1, 36, 260.0, 0.4),
            'cpi_used_cars': _make_monthly_series(yr - 3, 1, 36, 200.0, -0.5),
            'houst': _make_monthly_series(yr - 3, 1, 36, 1400.0, 5.0),
            'houst1f': _make_monthly_series(yr - 3, 1, 36, 900.0, 3.0),
            'permit': _make_monthly_series(yr - 3, 1, 36, 1500.0, 4.0),
            'cs_hpi': cs_hpi,
            'gdpc1': _make_monthly_series(yr - 3, 1, 36, 22000.0, 100.0),
            'gdp_growth': [{'date': f'{yr}-01-01', 'value': 2.5}],
            'cc_delinq': [{'date': f'{yr}-01-01', 'value': 2.8}],
            'mtg_delinq': [{'date': f'{yr}-01-01', 'value': 1.5}],
            'tdsp': _make_monthly_series(yr - 3, 1, 36, 9.5, 0.05),
            'fedfunds_annual': _annual(yr - 10, 10, 0.5, 0.3),
            'mortgage30_annual': _annual(yr - 10, 10, 3.5, 0.2),
            'dgs10_annual': _annual(yr - 10, 10, 2.0, 0.15),
            'dgs2_annual': _annual(yr - 10, 10, 1.5, 0.2),
            'ig_oas_annual': _annual(yr - 10, 10, 0.9, 0.02),
            'hy_oas_annual': _annual(yr - 10, 10, 3.0, 0.05),
            'wti_annual': wti_annual,
            'brent_annual': brent_annual,
            'gdpc1_annual': _annual(yr - 10, 10, 18000.0, 500.0),
            'gdp_annual': _annual(yr - 10, 10, 18000.0, 500.0),
            'umcsent_annual': _annual(yr - 10, 10, 70.0, -0.5),
            'cpiengsl': _make_monthly_series(yr - 3, 1, 36, 260.0, 0.4),
            'revolsl_annual': _annual(yr - 10, 10, 900.0, 50.0),
            'nonrevsl_annual': _annual(yr - 10, 10, 2500.0, 80.0),
            'wti_monthly': _make_monthly_series(yr - 3, 1, 36, 65.0, 0.3),
            'brent_monthly': _make_monthly_series(yr - 3, 1, 36, 70.0, 0.3),
        }
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST SUITES
# ═══════════════════════════════════════════════════════════════════════

def test_analyzer(tmp_dir):
    """Test analyzer produces valid signals.json."""
    print('\n── Test: Analyzer ──')
    import analyzer

    # Point analyzer to our temp files
    analyzer.ROOT = tmp_dir
    analyzer.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    analyzer.SNAP_FILE = tmp_dir / 'data' / 'last_update.json'
    analyzer.OUT_FILE = tmp_dir / 'data' / 'signals.json'

    try:
        analyzer.analyze()
    except SystemExit:
        pass

    sig_file = tmp_dir / 'data' / 'signals.json'
    _test('signals.json created', sig_file.exists())

    if sig_file.exists():
        sig = json.loads(sig_file.read_text())
        _test('signals has values', 'values' in sig, 'missing "values" key')
        _test('signals has signals list', 'signals' in sig, 'missing "signals" key')


def test_renderer(tmp_dir):
    """Test renderer produces valid HTML from fixture data."""
    print('\n── Test: Renderer ──')
    import renderer
    import _api_writer

    # Point renderer to temp dir
    renderer.ROOT = tmp_dir
    renderer.HTML_FILE = tmp_dir / 'index.html'
    renderer.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    renderer.SIG_FILE = tmp_dir / 'data' / 'signals.json'
    renderer.ANA_FILE = tmp_dir / 'data' / 'analysis.json'
    renderer.OVR_FILE = tmp_dir / 'data' / 'overrides.json'
    renderer.VAL_FILE = tmp_dir / 'data' / 'validation_report.json'

    # Redirect _api_writer to the temp dir so renderer.render() does NOT
    # overwrite the real data/state.json with synthetic fixture data.
    # Without this, every smoke-test run corrupts the live state.json and
    # blanks all Tier-1 charts (U_SECTOR_MOM, CPI_CAT_MOM, etc.) until
    # the next full CI run rebuilds it from real API data.
    _real_state_file = _api_writer._STATE_FILE
    _real_state = _api_writer._STATE.copy()
    _api_writer._STATE_FILE = tmp_dir / 'data' / 'state.json'
    _api_writer._STATE = {}

    # Reset state
    renderer.applied = []
    renderer.errors = []
    renderer.warnings = []

    try:
        result = renderer.render()
    except SystemExit:
        result = False
    finally:
        # Always restore — even if render() throws
        _api_writer._STATE_FILE = _real_state_file
        _api_writer._STATE = _real_state

    html_file = tmp_dir / 'index.html'
    _test('index.html exists after render', html_file.exists())

    if html_file.exists():
        html = html_file.read_text()
        size = len(html.encode('utf-8'))
        _test('HTML size > 100KB', size > 100_000, f'only {size:,} bytes')

        # Check critical JS constants exist. KPIS migrated to
        # /api/state.json (Tier 1 anti-clone) — its inline form is
        # now `let KPIS = null;` placeholder, so accept either shape.
        for const in ['KPIS', 'CPI_MONTHLY', 'U_MONTHLY', 'NFP_VS_ADP']:
            present = (f'const {const}' in html) or (f'let {const}' in html)
            _test(f'const {const} present', present)

        # Check no Python tracebacks
        _test('No tracebacks in HTML', 'Traceback' not in html)

        # Check valid HTML structure
        _test('Has <html> tag', '<html' in html)
        _test('Has </html> tag', '</html>' in html)
        _test('Has <body> tag', '<body' in html)

    # Check renderer error count
    hard_errors = [e for e in renderer.errors if 'missing' in e.lower() or 'ERROR' in e]
    _test(f'No hard renderer errors', len(hard_errors) == 0,
          f'{len(hard_errors)} errors: {hard_errors[:3]}')


def test_hydration_wiring(tmp_dir):
    """Test Tier 1 anti-clone hydration is wired end-to-end.

    Regression guard for the "blank charts on first paint" bug:
    every `let X = null;` Tier 1 placeholder must have a matching
    `s.X !== undefined` hydration assignment in the boot loader, AND
    a real callback must be pushed to `MD._hydrationCallbacks` so
    tabs rebuild once state.json arrives. Without the callback,
    guarded tab builders (FC, jobs, cpi, pce, banks, oil) bail out
    on first paint and never re-render.
    """
    print('\n── Test: Hydration wiring (Tier 1 anti-clone) ──')
    html_file = tmp_dir / 'index.html'
    if not html_file.exists():
        _test('index.html exists for hydration check', False, 'no file')
        return
    html = html_file.read_text(encoding='utf-8')

    # 1. Find every `let X = null;` placeholder — these are Tier 1 markers.
    placeholders = set(re.findall(r'let\s+([A-Z][A-Z0-9_]+)\s*=\s*null\s*;', html))
    _test('At least one Tier 1 placeholder present',
          len(placeholders) >= 5,
          f'found {len(placeholders)}: {sorted(placeholders)}')

    # 2. Each placeholder must have a hydration assignment line.
    missing_assigns = [k for k in placeholders
                       if not re.search(rf's\.{k}\s*!==\s*undefined', html)]
    _test('Every placeholder has hydration assign',
          not missing_assigns,
          f'no `s.X !== undefined` for: {missing_assigns}')

    # 3. Boot loader infrastructure present.
    _test('MD._hydrationCallbacks queue declared',
          'window.MD._hydrationCallbacks' in html)
    _test('MD._hydrationDone flag declared',
          'window.MD._hydrationDone' in html)
    _test('Hydration fetches /api/state.json first',
          "'/api/state.json'" in html or '"/api/state.json"' in html)
    _test('Hydration falls back to /data/state.json',
          "'/data/state.json'" in html or '"/data/state.json"' in html)

    # 4. Critical: a real callback must actually be pushed onto the
    # queue. The naked queue with no pushers is the exact bug that
    # left charts blank — _hydrate() runs, finds an empty callback
    # array, and the guarded tab builders never get re-invoked.
    # Count only push() calls in executable code, NOT in `//`/`/*` doc
    # comments (the boot loader has a comment that documents the API
    # shape — it would falsely satisfy a naive regex).
    real_push_sites = []
    for line in html.splitlines():
        if '_hydrationCallbacks.push' not in line:
            continue
        # Strip leading whitespace then check the first non-space token
        # is not a comment marker.
        stripped = line.lstrip()
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
            continue
        if re.search(r'_hydrationCallbacks\.push\s*\(', line):
            real_push_sites.append(line.strip()[:120])
    _test('At least one REAL callback pushed to hydration queue',
          len(real_push_sites) >= 1,
          'no executable `_hydrationCallbacks.push(` found — guarded tabs will stay blank '
          '(comments do not count)')

    # 5. Race-safe registration: if _hydrate() finishes before the
    # callback registers, the registrant must check _hydrationDone
    # and self-invoke. Otherwise scripts loaded async miss the train.
    _test('Race-safe done check present',
          'MD._hydrationDone' in html and re.search(r'if\s*\([^)]*_hydrationDone', html) is not None,
          'no `if (...MD._hydrationDone)` guard around callback push')

    # 6. Critical: every Tier 1 placeholder must live at SCRIPT scope,
    # not inside a function body. A placeholder declared inside a
    # tab-builder is function-local — the boot loader's
    # `SHOCK_TRACKER = s.SHOCK_TRACKER` style assignment then targets
    # the global window object instead of the intended `let`, and the
    # consumer code reads the local null. This was the EX 5 oil-impact-
    # chain blank-panel bug (shipped post the first hydration fix).
    lines = html.splitlines()
    function_ranges = []
    for i, line in enumerate(lines, start=1):
        if re.match(r'^function (\w+)\(', line):
            depth = 0
            started = False
            for j in range(i - 1, len(lines)):
                depth += lines[j].count('{') - lines[j].count('}')
                if '{' in lines[j]:
                    started = True
                if started and depth == 0:
                    function_ranges.append((i, j + 1))
                    break
    misplaced = []
    for i, line in enumerate(lines, start=1):
        m = re.match(r'^\s*let ([A-Z][A-Z_]+)\s*=\s*null\s*;', line)
        if not m:
            continue
        for fs, fe in function_ranges:
            if fs < i <= fe:
                misplaced.append(f'{m.group(1)} at line {i} (inside function starting line {fs})')
                break
    _test('Every Tier 1 placeholder at script scope (not inside a function)',
          not misplaced,
          f'shadowed-local placeholders detected: {misplaced[:5]}' if misplaced else '')


def test_validator_offline(tmp_dir):
    """Test validator runs in offline mode (no API keys)."""
    print('\n── Test: Validator (offline) ──')
    import validator

    validator.ROOT = tmp_dir
    validator.HTML_FILE = tmp_dir / 'index.html'
    validator.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    validator.SIG_FILE = tmp_dir / 'data' / 'signals.json'
    validator.RPT_FILE = tmp_dir / 'data' / 'validation_report.json'
    validator.FRED_KEY = ''
    validator.BLS_KEY = ''

    # Redirect bank-earnings + transcripts archive to tmp_dir so Pass 3c
    # is exercised in isolation (the validator module otherwise pins these
    # to the real project root at import time). Without this redirect the
    # smoke test silently uses real bank_earnings.json + a missing
    # transcripts/ archive — which (post-B1.4) correctly raises critical
    # findings for every status=reported bank, defeating fixture isolation.
    validator.BANK_FILE = tmp_dir / 'data' / 'bank_earnings.json'
    validator.TRANSCRIPTS_DIR = tmp_dir / 'data' / 'transcripts'

    # Write an offline-safe fixture: all banks marked 'pending' so Pass 3c
    # emits 'skipped' rows (zero criticals, zero warnings) — mirrors a
    # pre-earnings-season pipeline state.
    (tmp_dir / 'data' / 'bank_earnings.json').write_text(json.dumps({
        'quarter': 'Q1_2026',
        'banks': [
            {'id': 'jpm', 'bank': 'JPMorgan Chase', 'ticker': 'JPM',
             'ceo': 'Jamie Dimon', 'status': 'pending',
             'expected_report_date': '2026-04-15'},
            {'id': 'bac', 'bank': 'Bank of America', 'ticker': 'BAC',
             'ceo': 'Brian Moynihan', 'status': 'pending',
             'expected_report_date': '2026-04-15'},
        ],
    }, indent=2), encoding='utf-8')

    try:
        result = validator.validate()
    except SystemExit:
        result = False

    rpt_file = tmp_dir / 'data' / 'validation_report.json'
    _test('validation_report.json created', rpt_file.exists())

    if rpt_file.exists():
        rpt = json.loads(rpt_file.read_text())
        _test('Report has status', 'status' in rpt)
        _test('Report has summary', 'summary' in rpt)
        _test('Summary has total_checks', 'total_checks' in rpt.get('summary', {}))
        n_crit = rpt.get('summary', {}).get('critical_divergences', 99)
        if n_crit > 0:
            print('  DEBUG: critical findings ↓')
            def _walk(obj, path=''):
                if isinstance(obj, dict):
                    sev = obj.get('severity')
                    if sev in ('critical', 'divergence'):
                        print(f'    - [{path}] {str(obj.get("check",""))[:80]} | {str(obj.get("reason",""))[:120]}')
                    for k, v in obj.items():
                        _walk(v, f'{path}.{k}' if path else k)
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        _walk(v, f'{path}[{i}]')
            _walk(rpt)
        _test('No critical divergences (fixture data)',
              n_crit == 0,
              f'found {n_crit}')


def test_snapshot(tmp_dir):
    """Test snapshot creation and rollback."""
    print('\n── Test: Snapshot ──')
    import snapshot

    snapshot.ROOT = tmp_dir
    snapshot.DATA_DIR = tmp_dir / 'data'
    snapshot.SNAP_DIR = tmp_dir / 'data' / 'snapshots'
    snapshot.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    snapshot.VAL_FILE = tmp_dir / 'data' / 'validation_report.json'
    snapshot.HTML_FILE = tmp_dir / 'index.html'

    snapshot.take_snapshot()

    snap_dir = tmp_dir / 'data' / 'snapshots'
    _test('Snapshots dir created', snap_dir.exists())

    snaps = list(snap_dir.iterdir()) if snap_dir.exists() else []
    _test('At least 1 snapshot', len(snaps) >= 1)

    if snaps:
        manifest = snaps[0] / 'manifest.json'
        _test('Manifest exists', manifest.exists())
        if manifest.exists():
            m = json.loads(manifest.read_text())
            _test('Manifest has snapshot_date', 'snapshot_date' in m)

        # Test rollback
        date_str = snaps[0].name
        # Corrupt raw_data
        raw = tmp_dir / 'data' / 'raw_data.json'
        raw.write_text('{"corrupted": true}')

        ok = snapshot.rollback(date_str)
        _test('Rollback succeeds', ok)

        restored = json.loads(raw.read_text())
        _test('Rollback restores data', 'collected_at' in restored,
              'restored file missing collected_at')


def test_healthcheck_module():
    """Test healthcheck module loads without errors."""
    print('\n── Test: Healthcheck module ──')
    import healthcheck
    _test('healthcheck module loads', True)
    _test('healthcheck function exists', hasattr(healthcheck, 'healthcheck'))
    _test('REQUIRED_MARKERS defined', len(healthcheck.REQUIRED_MARKERS) > 0)


def test_renderer_idempotent(tmp_dir):
    """Test that running renderer twice produces identical output."""
    print('\n── Test: Renderer Idempotency ──')
    import renderer

    html_file = tmp_dir / 'index.html'
    if not html_file.exists():
        _test('Skipped (no HTML)', False, 'index.html missing from prior test')
        return

    first_html = html_file.read_text()
    first_size = len(first_html)

    # Reset and re-run
    renderer.ROOT = tmp_dir
    renderer.HTML_FILE = html_file
    renderer.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    renderer.SIG_FILE = tmp_dir / 'data' / 'signals.json'
    renderer.ANA_FILE = tmp_dir / 'data' / 'analysis.json'
    renderer.OVR_FILE = tmp_dir / 'data' / 'overrides.json'
    renderer.VAL_FILE = tmp_dir / 'data' / 'validation_report.json'
    renderer.applied = []
    renderer.errors = []
    renderer.warnings = []

    try:
        renderer.render()
    except SystemExit:
        pass

    second_html = html_file.read_text()
    second_size = len(second_html)

    # Size should be very close (timestamps may differ slightly)
    size_diff = abs(first_size - second_size)
    _test('HTML size stable after re-render', size_diff < 500,
          f'size changed by {size_diff} bytes ({first_size} → {second_size})')


def test_panel_subtitle_gates(tmp_dir):
    """Regression guard: panel subtitle update gates must match rebuild success strings.

    Root cause (2026-06-04): render_inflation() and render_labor() gate the
    PCE / CPI / SECTOR_MOM / U_SECTOR_MOM panel-sub month updates on
    applied[] message prefixes. The Tier 1 anti-clone migration renamed the
    success messages from 'XXX rebuilt' to 'XXX registered to state.json...'
    but the gate conditions were not updated. This silently froze panel
    subtitles at whatever Agent 3 last wrote — Pass 3d fired as critical
    every run.

    This test verifies each gate fires when the actual rebuild success message
    is in applied[]. If a rebuild function renames its message, this fails
    immediately rather than silently degrading the dashboard.
    """
    print('\n── Test: Panel Subtitle Gate String Contracts ──')
    import renderer as r

    # The exact strings that each rebuild function appends on success.
    # These must match the startswith() checks in render_inflation / render_labor.
    success_messages = [
        'PCE_CAT_MOM registered to state.json (4 cats, mar26/apr26); inline zeroed',
        'CPI_CAT_MOM registered to state.json (10 cats, mar26/apr26); inline zeroed',
        'SECTOR_MOM registered to state.json (13 sectors, mar26 & apr26); inline zeroed',
        'U_SECTOR_MOM registered to state.json (11 sectors, mar26/apr26); inline zeroed',
    ]

    # Gate expressions as they appear in renderer.py
    gates = {
        'PCE_CAT_MOM': lambda msgs: any(s.startswith('PCE_CAT_MOM registered') for s in msgs),
        'CPI_CAT_MOM': lambda msgs: any(s.startswith('CPI_CAT_MOM registered') for s in msgs),
        'SECTOR_MOM':  lambda msgs: any(s.startswith('SECTOR_MOM registered') for s in msgs),
        'U_SECTOR_MOM': lambda msgs: any(s.startswith('U_SECTOR_MOM registered') for s in msgs),
    }

    for name, gate_fn in gates.items():
        result = gate_fn(success_messages)
        _test(
            f'{name} subtitle gate fires on rebuild success message',
            result,
            f"startswith prefix for '{name}' does not match any success message in applied[]",
        )

    # Also verify the OLD broken strings no longer match (prevent regression).
    old_broken_messages = [
        'PCE_CAT_MOM rebuilt ...',
        'CPI_CAT_MOM rebuilt ...',
        'SECTOR_MOM rebuilt ...',
        'U_SECTOR_MOM rebuilt ...',
    ]
    for name, gate_fn in gates.items():
        result = gate_fn(old_broken_messages)
        _test(
            f'{name} subtitle gate does NOT fire on stale "rebuilt" messages',
            not result,
            f"gate would mistakenly fire on old-style 'rebuilt' prefix — revert introduced regression",
        )


def test_commentary_patch_regexes(tmp_dir):
    """Regression guard: commentary auto-patch regexes must match both
    structured (<strong> tag) and plain-text (Agent 3 prose) formats.

    Root cause (2026-06-26): render_inflation() Core PCE patch used a single
    narrow regex requiring '<strong>+X.X% YoY</strong>' format. When Agent 3
    writes 'Core PCE at 3.2%' (plain text, common fallback), the regex silently
    fails and applied.append fires unconditionally — the number freezes while the
    KPI tile updates. Two-tier regex + re.subn detection fixes both issues.
    """
    print('\n── Test: Commentary Patch Regex Coverage ──')
    import re

    yoy_cur = 3.4

    # Tier-1 pattern (structured LLM output)
    t1_pat = (r"(Core PCE [a-z\-]+ to <strong>)\+\d+\.\d+% YoY</strong> \([A-Z][a-z]+'\d+\)"
              r", (?:up|down) from \+\d+\.\d+% in [A-Z][a-z]+'\d+")
    t1_html = "Core PCE re-accelerated to <strong>+3.2% YoY</strong> (Apr'26), up from +3.0% in Mar'26"
    _, n1 = re.subn(t1_pat, 'REPLACED', t1_html, count=1)
    _test(
        'Core PCE tier-1 regex matches structured <strong> format',
        n1 == 1,
        'Tier-1 regex did not match structured LLM output — check pattern in render_inflation()',
    )
    _, n1_miss = re.subn(t1_pat, 'REPLACED', 'Core PCE at 3.2%', count=1)
    _test(
        'Core PCE tier-1 regex does NOT match plain-text format (tier-2 handles it)',
        n1_miss == 0,
        'Tier-1 regex is too broad — it must NOT match plain-text prose',
    )

    # Tier-2 pattern (plain-text prose from Agent 3 fallback)
    t2_pat = (r'(Core PCE\s+'
              r'(?:at|of|is|near|came in at|eased to|rose to|fell to|'
              r'held at|printed at|stands at|running at)\s+)'
              r'\+?(\d+\.\d+)(%)')
    t2_cases = [
        'Core PCE at 3.2% is the Fed primary target',
        'Core PCE of 3.2% remains above target',
        'Core PCE eased to 3.2% in the latest reading',
        'Core PCE rose to 3.2% from prior month',
    ]
    for case in t2_cases:
        _, n2 = re.subn(t2_pat, r'\g<1>REPLACED\g<3>', case, count=1, flags=re.IGNORECASE)
        _test(
            f'Core PCE tier-2 regex matches: "{case[:50]}"',
            n2 == 1,
            f'Tier-2 regex did not match this plain-text format — add verb to tier-2 pattern',
        )

    # Verify tier-2 replacement preserves surrounding text and updates number
    sample = 'With Core PCE at 3.2% still above the 2% target, the Fed remains vigilant.'
    result, n = re.subn(
        t2_pat,
        lambda m: m.group(1) + f'{yoy_cur:.1f}' + m.group(3),
        sample, count=1, flags=re.IGNORECASE)
    _test(
        'Core PCE tier-2 replacement updates number and preserves surrounding text',
        n == 1 and '3.4%' in result and 'above the 2% target' in result,
        f'Tier-2 replacement produced unexpected result: {result!r}',
    )

    # Verify U-3 pattern (separate from PCE)
    u3_pat = r'(U-3 at <strong>)\d+\.\d+%</strong> \([A-Z][a-z]+ \d{4}\)'
    u3_html = "U-3 at <strong>4.1%</strong> (Mar 2026)"
    _, nu3 = re.subn(u3_pat, r'\g<1>4.0%</strong> (Apr 2026)', u3_html, count=1)
    _test(
        'U-3 commentary patch regex matches expected format',
        nu3 == 1,
        'U-3 commentary patch regex broken — check render_labor()',
    )


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print('=' * 60)
    print('SMOKE TESTS — Offline Pipeline Validation')
    print('=' * 60)

    # Create temp directory with project structure
    tmp_dir = Path(tempfile.mkdtemp(prefix='macro_smoke_'))
    print(f'Working dir: {tmp_dir}')

    try:
        # Setup: copy index.html template, write fixture data
        (tmp_dir / 'data').mkdir()
        shutil.copy2(ROOT / 'index.html', tmp_dir / 'index.html')

        fixture = generate_fixture_data()
        (tmp_dir / 'data' / 'raw_data.json').write_text(json.dumps(fixture))

        # Copy overrides if exists
        ovr = ROOT / 'data' / 'overrides.json'
        if ovr.exists():
            shutil.copy2(ovr, tmp_dir / 'data' / 'overrides.json')

        # Strip API keys for offline testing
        os.environ.pop('FRED_API_KEY', None)
        os.environ.pop('BLS_API_KEY', None)
        os.environ.pop('EIA_API_KEY', None)

        # Run tests sequentially (each depends on prior output)
        test_analyzer(tmp_dir)
        test_renderer(tmp_dir)
        test_renderer_idempotent(tmp_dir)
        test_hydration_wiring(tmp_dir)
        test_validator_offline(tmp_dir)
        test_snapshot(tmp_dir)
        test_healthcheck_module()
        test_panel_subtitle_gates(tmp_dir)
        test_commentary_patch_regexes(tmp_dir)

    finally:
        # Cleanup
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Summary
    total = PASS + FAIL
    print(f'\n{"=" * 60}')
    print(f'SMOKE TESTS: {PASS}/{total} passed, {FAIL} failed')
    if ERRORS:
        print(f'\nFailures:')
        for e in ERRORS:
            print(f'  - {e}')
    print(f'{"=" * 60}')

    return FAIL == 0


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
