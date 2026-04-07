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

    # Point renderer to temp dir
    renderer.ROOT = tmp_dir
    renderer.HTML_FILE = tmp_dir / 'index.html'
    renderer.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    renderer.SIG_FILE = tmp_dir / 'data' / 'signals.json'
    renderer.ANA_FILE = tmp_dir / 'data' / 'analysis.json'
    renderer.OVR_FILE = tmp_dir / 'data' / 'overrides.json'
    renderer.VAL_FILE = tmp_dir / 'data' / 'validation_report.json'

    # Reset state
    renderer.applied = []
    renderer.errors = []
    renderer.warnings = []

    try:
        result = renderer.render()
    except SystemExit:
        result = False

    html_file = tmp_dir / 'index.html'
    _test('index.html exists after render', html_file.exists())

    if html_file.exists():
        html = html_file.read_text()
        size = len(html.encode('utf-8'))
        _test('HTML size > 100KB', size > 100_000, f'only {size:,} bytes')

        # Check critical JS constants exist
        for const in ['KPIS', 'CPI_MONTHLY', 'U_MONTHLY', 'NFP_VS_ADP']:
            _test(f'const {const} present', f'const {const}' in html)

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
        _test('No critical divergences (fixture data)',
              rpt.get('summary', {}).get('critical_divergences', 99) == 0,
              f'found {rpt.get("summary", {}).get("critical_divergences", "?")}')


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
        test_validator_offline(tmp_dir)
        test_snapshot(tmp_dir)
        test_healthcheck_module()

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
