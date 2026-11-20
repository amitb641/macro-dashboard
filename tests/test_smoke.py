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
# REAL-FILE ISOLATION GUARD — every phase below must operate on tmp_dir
# copies only. This fingerprints the live project files most at risk
# (validator.py's embedded visual_qa call resolves paths from repo ROOT
# regardless of module-level overrides) so a future isolation regression
# fails loudly instead of silently dirtying the working tree.
# ═══════════════════════════════════════════════════════════════════════

GUARDED_REAL_FILES = [
    ROOT / 'data' / 'signals.json',
    ROOT / 'data' / 'validation_report.json',
    ROOT / 'data' / 'visual_qa_report.json',
    ROOT / 'data' / 'visual_review_report.json',
    ROOT / 'index.html',
]


def _hash_real_files():
    import hashlib
    files = list(GUARDED_REAL_FILES)
    screenshots_dir = ROOT / 'data' / 'screenshots'
    if screenshots_dir.exists():
        files += sorted(screenshots_dir.glob('*.png'))
    # test_monthly_archive redirects monthly_archive.ARCHIVE_DIR to tmp_dir,
    # but guard the real archive anyway — it's a permanent, never-pruned
    # historical record, so a test accidentally writing into it would be
    # worse than the usual "smoke test dirtied a regenerable file" case.
    archive_dir = ROOT / 'data' / 'monthly_archive'
    if archive_dir.exists():
        files += sorted(archive_dir.rglob('*.*'))
    return {str(f): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in files if f.exists()}


def test_no_real_file_mutation(before):
    """Regression guard: smoke tests must never modify real project data."""
    print('\n── Test: Real Project Data Untouched ──')
    after = _hash_real_files()
    changed = sorted(p for p, h in before.items() if after.get(p) != h)
    _test('No real project files modified by smoke tests', not changed,
          f'{len(changed)} file(s) changed: {changed[:5]}')


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
            # Atlanta Fed Wage Growth Tracker (feeds WAGE_MONTHLY + the wage tile).
            # Without it the tile falls back to AHETPI while the chart keeps the
            # repo's Atlanta Fed data — a tile/chart split Pass 3j rightly fails.
            'wage_growth_atl': _make_monthly_series(yr - 3, 1, 36, 4.2, -0.01),
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
            # PCE components (PCE_CAT_MOM). Without them that rebuild is skipped
            # and Pass 3j correctly flags stale category months.
            'pce_goods':    _make_monthly_series(yr - 3, 1, 36, 110.0, 0.15),
            'pce_services': _make_monthly_series(yr - 3, 1, 36, 125.0, 0.30),
            'pce_food':     _make_monthly_series(yr - 3, 1, 36, 118.0, 0.20),
            'pce_energy':   _make_monthly_series(yr - 3, 1, 36, 105.0, 0.25),
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
        html = html_file.read_text(encoding='utf-8')
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

    # Every renderer error counts. The old filter ('missing'/'ERROR' only)
    # ignored "not found" — the exact signature of a regex patch that silently
    # stopped matching — so 12 such errors ran on every pipeline run unnoticed.
    _test('Renderer reports zero errors', len(renderer.errors) == 0,
          f'{len(renderer.errors)} errors: {renderer.errors[:3]}')


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


def test_monthly_archive(tmp_dir):
    """Test the durable monthly archive + its derived SQLite index."""
    print('\n── Test: Monthly Archive ──')
    import monthly_archive
    import build_archive_index

    monthly_archive.ROOT = tmp_dir
    monthly_archive.DATA_DIR = tmp_dir / 'data'
    monthly_archive.ARCHIVE_DIR = tmp_dir / 'data' / 'monthly_archive'
    monthly_archive.RAW_FILE = tmp_dir / 'data' / 'raw_data.json'
    monthly_archive.STATE_FILE = tmp_dir / 'data' / 'state.json'
    monthly_archive.SIG_FILE = tmp_dir / 'data' / 'signals.json'
    monthly_archive.VAL_FILE = tmp_dir / 'data' / 'validation_report.json'
    monthly_archive.CEO_FILE = tmp_dir / 'data' / 'ceo_grade_verdict.json'
    monthly_archive.HTML_FILE = tmp_dir / 'index.html'

    monthly_archive.archive_month()

    archive_dir = tmp_dir / 'data' / 'monthly_archive'
    _test('Archive dir created', archive_dir.exists())

    months = list(archive_dir.iterdir()) if archive_dir.exists() else []
    _test('Exactly 1 month archived', len(months) == 1,
          f'found {len(months)}')

    if months:
        month_dir = months[0]
        manifest_path = month_dir / 'manifest.json'
        metrics_path = month_dir / 'metrics.json'
        _test('manifest.json exists', manifest_path.exists())
        _test('metrics.json exists', metrics_path.exists())

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            _test('Manifest has schema_version', manifest.get('schema_version') == 1)
            _test('Manifest has git_sha', bool(manifest.get('git_sha')))
            _test('Manifest has sha256 checksums', bool(manifest.get('sha256')))

        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
            _test('Metrics has entries', len(metrics.get('metrics', [])) > 0,
                  'signals.json values should populate metrics.json')

        # Idempotency: running again for the same month must upsert in
        # place, never create a second directory for the same YYYY-MM.
        monthly_archive.archive_month()
        months_after = list(archive_dir.iterdir())
        _test('Re-run is idempotent (still 1 month dir)', len(months_after) == 1,
              f'found {len(months_after)}')

    # Derived SQLite index — build against the same tmp archive dir.
    build_archive_index.ARCHIVE_DIR = archive_dir
    db_path = tmp_dir / 'data' / 'monthly_archive.db'
    n_indexed = build_archive_index.build(db_path)
    _test('Archive index built', db_path.exists())
    _test('Archive index indexed 1 month', n_indexed == 1, f'indexed {n_indexed}')

    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        snap_rows = conn.execute('SELECT month FROM monthly_snapshots').fetchall()
        _test('monthly_snapshots has 1 row', len(snap_rows) == 1)
        metric_rows = conn.execute('SELECT DISTINCT series_id FROM monthly_metrics').fetchall()
        _test('monthly_metrics has series rows', len(metric_rows) > 0)
        conn.close()


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

    first_html = html_file.read_text(encoding='utf-8')
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

    second_html = html_file.read_text(encoding='utf-8')
    second_size = len(second_html)

    # Size should be very close (timestamps may differ slightly)
    size_diff = abs(first_size - second_size)
    _test('HTML size stable after re-render', size_diff < 500,
          f'size changed by {size_diff} bytes ({first_size} → {second_size})')


def test_oil_window_coverage(tmp_dir):
    """Regression guard for the OIL_DAILY fetch-window bug (fixed 2026-09-28):
    collector.py used to fetch a fixed 60 most-recent daily oil observations,
    commented '~2 months to cover from Mar 1' -- true only when run close to
    March. By Sep 28 2026, 60 trading days back landed on Jun 29, silently
    truncating build_oil_daily()'s own Mar-1 filter input and losing ~4
    months of the shock tracker's claimed history (the chart's own date
    range drifted off its "Since Mar 2026" banner). Fixed by sizing the
    fetch window from the actual calendar gap; this test guards the
    self-check (check_oil_window_coverage) that now catches a regression
    of the same shape offline, without live API keys.
    """
    print('\n── Test: Oil Daily Window Coverage Guard ──')
    import collector
    import datetime as _dt

    today = _dt.date(2026, 9, 28)

    # Simulate the bug: a fixed-count fetch that only reaches back 60
    # trading days (~Jun 29), same shape as the original defect.
    truncated = [{'date': (today - _dt.timedelta(days=i)).isoformat(), 'value': 90.0}
                 for i in range(0, 62, 1) if (today - _dt.timedelta(days=i)).weekday() < 5][:60]
    errs = collector.check_oil_window_coverage(truncated, [], today=today)
    _test(
        'check_oil_window_coverage flags a window that does not reach Mar 1',
        len(errs) == 1 and 'OIL_DAILY window too short' in errs[0],
        f'Expected exactly one "window too short" finding, got: {errs!r}',
    )

    # Healthy case: window genuinely reaches back to (near) March 1.
    healthy = truncated + [{'date': '2026-03-02', 'value': 71.0},
                            {'date': '2026-03-03', 'value': 71.5}]
    errs2 = collector.check_oil_window_coverage(healthy, [], today=today)
    _test(
        'check_oil_window_coverage stays silent when the window reaches Mar 1',
        errs2 == [],
        f'Expected no findings for a healthy window, got: {errs2!r}',
    )

    # Boundary: a 5-day-late start is within tolerance (weekends/holidays).
    boundary = [{'date': '2026-03-05', 'value': 71.2}]
    errs3 = collector.check_oil_window_coverage(boundary, [], today=today)
    _test(
        'check_oil_window_coverage tolerates a <=5-day gap from Mar 1',
        errs3 == [],
        f'Expected no findings within the 5-day tolerance, got: {errs3!r}',
    )

    # Malformed/missing-date observations must not crash the check.
    errs4 = collector.check_oil_window_coverage([{'value': 1.0}, {'date': None, 'value': 2.0}], [], today=today)
    _test(
        'check_oil_window_coverage tolerates malformed observations without crashing',
        errs4 == [],
        f'Expected no findings (no valid dates to check), got: {errs4!r}',
    )


def test_chart_contracts():
    """Pass 3j fixture test: a correct chart passes; each of this year's
    corruption shapes fails CRITICAL (forward-fill, 13-month "YoY" in a gap,
    last slot overwritten, chart behind source, tile/chart month mismatch)."""
    print('\n── Test: Chart Contracts (Pass 3j) ──')
    import datetime as _dt, json as _json
    import validator
    today = _dt.date(2026, 11, 20)
    # CPI-like index with Oct'25 missing (shutdown); +1.0/month.
    months = [(2025, m) for m in range(1, 13) if m != 10] + [(2026, m) for m in range(1, 11)]
    idx = {ym: 300.0 + i for i, ym in enumerate(months)}
    cpi = [{'date': f'{y}-{m:02d}-01', 'value': v} for (y, m), v in sorted(idx.items(), reverse=True)]
    def yoy(y, m): return round((idx[(y, m)] - idx[(y - 1, m)]) / idx[(y - 1, m)] * 100, 1)
    lbls = [f"{_dt.date(2026, m, 1):%b'%y}" for m in range(1, 10)]          # Jan..Sep'26
    good = [yoy(2026, m) for m in range(1, 10)]
    def page(head, tile_lbl, tile_val):
        cm = {'labels': lbls, 'headline': head, 'core': head}
        kp = [{'lbl': tile_lbl, 'val': tile_val}, {'lbl': tile_lbl.replace('Headline', 'Core'), 'val': tile_val}]
        return f'const CPI_MONTHLY = {_json.dumps(cm)};\nconst KPIS = {_json.dumps(kp)};'
    data = {'cpi_all': cpi, 'cpi_core': cpi}
    old = validator.CHART_CONTRACTS, validator.TILE_CHART_LINKS, validator.CATEGORY_LINKS
    validator.CATEGORY_LINKS = []
    validator.CHART_CONTRACTS = [('CPI_MONTHLY', 'headline', 'cpi_all', 'yoy', 1, None)]
    validator.TILE_CHART_LINKS = [('Headline CPI', 'CPI_MONTHLY', 'headline')]
    try:
        def crit(html):
            return [f for f in validator.check_chart_contracts(html, data, today)
                    if not f['pass'] and f['severity'] == 'critical']
        ok = page(good, "Headline CPI Sep'26", f'{good[-1]}%')
        _test('3j: correct chart + tile pass', not crit(ok), str(crit(ok))[:200])
        thirteen = round((idx[(2026, 10)] - idx[(2025, 9)]) / idx[(2025, 9)] * 100, 1)
        bad_slot = page(good[:-1] + [thirteen], "Headline CPI Sep'26", f'{thirteen}%')
        _test('3j: last slot overwritten with 13-month change → critical', bool(crit(bad_slot)))
        ffill = {'labels': lbls + ["Oct'26"], 'headline': good + [good[-1]], 'core': good + [good[-1]]}
        ff = f'const CPI_MONTHLY = {_json.dumps(ffill)};\nconst KPIS = {_json.dumps([{"lbl": "Headline CPI Oct\'26", "val": "1%"}])};'
        _test('3j: value for a month with no year-ago (forward-fill/positional) → critical', bool(crit(ff)))
        behind = page(good[:-1], "Headline CPI Aug'26", f'{good[-2]}%')
        behind = behind.replace(_json.dumps(lbls), _json.dumps(lbls[:-1]))
        _test('3j: chart stops before newest supported month → critical', bool(crit(behind)))
        tile = page(good, "Headline CPI Oct'26", f'{good[-1]}%')
        _test('3j: tile month ≠ chart last month → critical', bool(crit(tile)))
    finally:
        validator.CHART_CONTRACTS, validator.TILE_CHART_LINKS, validator.CATEGORY_LINKS = old


def test_no_tdz_in_tab_builders():
    """Static guard (2026-11-20): inside each top-level JS function in
    index.html, a const/let must not be referenced above its own declaration.
    That is a guaranteed ReferenceError (temporal dead zone) every time the
    function runs. buildOilTab() had one for two months; a try/catch hid it
    and the tiles showed hard-coded March fallback values."""
    print('\n── Test: No TDZ use-before-declare in index.html functions ──')
    import re as _re
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    starts = [m.start() for m in _re.finditer(r'(?m)^function\s+\w+\s*\(', html)]
    problems = []
    for i, a in enumerate(starts):
        b = starts[i + 1] if i + 1 < len(starts) else len(html)
        body = html[a:b]
        fname = _re.match(r'function\s+(\w+)', body).group(1)
        # strip // comments and string literals so names in prose don't count
        code = _re.sub(r'//[^\n]*', '', body)
        code = _re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', '""', code)
        # Scoped to ALL_CAPS data consts (OIL_DAILY, SHOCK_TRACKER, …) — the
        # renderer-injected names this bug class involves. Lower-case locals
        # hit comma-lists, arrow params and block scopes a regex can't model.
        for d in _re.finditer(r'\b(?:const|let)\s+([A-Z][A-Z0-9_]{2,})\s*=', code):
            name = d.group(1)
            # Only names declared once in this function (shadowing in inner
            # scopes is legal and would produce false positives).
            if len(_re.findall(r'\b(?:const|let|var)\s+' + _re.escape(name) + r'\b', code)) != 1:
                continue
            before = code[:d.start()]
            if _re.search(r'(?<![\w$.])' + _re.escape(name) + r'(?![\w$])', before):
                problems.append(f'{fname}: {name}')
    _test('No const/let used before its declaration in any function',
          not problems, f'{problems[:5]}')


def test_no_positional_patching():
    """Static guard (2026-11-20). Bans the code shapes behind this year's
    silent data corruption so they cannot be reintroduced:
      * patch_array_last / patch_kpi / patch_kpi_full — overwrote "the array's
        last element" or fuzzy-matched tile labels (FFR/MORTGAGE/STARTS/CPI/OIL
        last slots, a JS label rewritten to "Nov'26Oct'26").
      * year-ago by row offset (series[12], [i+12]) — a missing month (Oct'25,
        shutdown) turns it into a 13-month change published as YoY.
      * carrying an array forward by position across runs (ADP history).
    Rebuild from source and match by calendar month / label instead."""
    print('\n── Test: No Positional Patching / Positional Year-Ago ──')
    import re as _re
    scripts = ROOT / 'scripts'
    banned = [
        (r'\bdef\s+patch_array_last\b|\bpatch_array_last\s*\(', 'patch_array_last'),
        (r'\bdef\s+patch_kpi(_full)?\b|\bpatch_kpi(_full)?\s*\(', 'patch_kpi / patch_kpi_full'),
        (r"\[\s*1[23]\s*\]\s*\[\s*['\"]value['\"]\s*\]", "series[12]['value'] year-ago by row"),
        (r"\[\s*\w+\s*\+\s*1[23]\s*\]\s*\[\s*['\"]value['\"]\s*\]", "series[i+12]['value'] year-ago by row"),
        (r"\+\s*\[None\]\s*\*\s*len\([^)]*\)\)\s*\[\s*:\s*len\(", 'array carried forward by position'),
    ]
    for py in sorted(scripts.glob('*.py')):
        src = py.read_text(encoding='utf-8')
        code = '\n'.join(l for l in src.splitlines() if not l.lstrip().startswith('#'))
        for pat, name in banned:
            hits = [m.group(0) for m in _re.finditer(pat, code)]
            _test(f'{py.name}: no {name}', not hits, f'found {hits[:2]}')


def test_yoy_missing_year_ago():
    """Regression guard (fixed 2026-11-20): Oct 2025 CPI was never collected
    (shutdown), so Oct 2026 has no year-ago index and BLS published no 12-month
    change. analyzer.yoy() used to fall back to series[12] (Sep'25) and report a
    13-month change as "Oct'26 YoY" (4.1% vs the real Sep'26 3.7%). It must now
    anchor to the newest month with a real year-ago match."""
    print('\n── Test: YoY With Missing Year-Ago Month ──')
    import analyzer
    # Newest-first monthly index, Oct'25 absent, +0.3/month, Oct'26 jumps.
    months = [(2026, m) for m in range(10, 0, -1)] + [(2025, 12), (2025, 11)] + \
             [(2025, m) for m in range(9, 0, -1)]
    series, v = [], 300.0
    for y, m in reversed(months):
        v += 1.0
        series.append({'date': f'{y}-{m:02d}-01', 'value': v})
    series.reverse()
    series[0]['value'] += 5.0           # Oct'26 spike that a 13-mo compare would inflate
    val, date = analyzer.yoy_with_date(series)
    _test('yoy anchors to latest month with real year-ago data (Sep\'26)', date == '2026-09-01',
          f'got date={date}')
    sep26 = next(o for o in series if o['date'] == '2026-09-01')['value']
    sep25 = next(o for o in series if o['date'] == '2025-09-01')['value']
    _test('yoy value is the true Sep\'26/Sep\'25 change, not a 13-month change',
          val == round((sep26 - sep25) / sep25 * 100, 2), f'got {val}')
    full = [o for o in series if o['date'] != '2026-10-01']
    _test('yoy unchanged behaviour when latest month has a year-ago match',
          analyzer.yoy_with_date(full)[1] == '2026-09-01')


def test_agent9_merge_clears_stale_fields(tmp_dir):
    """Regression guard (2026-10-28): merge_bank_update() used
    `entry.get('text','') or b.get(f,'')`, so a field Claude returned empty
    (GS has no card business -> cards_loans) kept LAST quarter's text,
    relabelled as the new quarter. Pass 3c blocked the whole commit on the
    stale Q1 quote; stale unquoted figures would have passed silently.
    """
    print('-- Test: Agent 9 merge does not carry over prior-quarter text --')
    import types
    stubbed = 'anthropic' not in sys.modules
    if stubbed:
        # earnings_agent sys.exit()s at import without the SDK; the merge
        # logic under test never touches it.
        sys.modules['anthropic'] = types.ModuleType('anthropic')
    try:
        import earnings_agent as ea
        earn = {'banks': [{'ticker': 'GS',
                           'cards_loans': 'Q1 text: Solomon: "if the resolution of the conflict drags, that probably will be a headwind"',
                           'economy': 'old economy'}]}
        fields = {'economy': {'text': 'new economy', 'src_tag': 'Q&A'}}  # cards_loans omitted
        ok = ea.merge_bank_update(earn, 'GS', fields, '2026-10-29', 'http://example.invalid')
        b = earn['banks'][0]
        _test('merge_bank_update finds and updates the bank', ok is True, f'returned {ok!r}')
        _test('empty extracted field is cleared, not carried over from the prior quarter',
              b['cards_loans'] == '', f"cards_loans still {b['cards_loans']!r}")
        _test('populated field takes the new text', b['economy'] == 'new economy', f"economy={b['economy']!r}")
        _test('bank marked reported', b['status'] == 'reported', f"status={b.get('status')!r}")
    finally:
        if stubbed:
            sys.modules.pop('anthropic', None)
            sys.modules.pop('earnings_agent', None)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print('=' * 60)
    print('SMOKE TESTS — Offline Pipeline Validation')
    print('=' * 60)

    # Fingerprint real project files before touching anything, so we can
    # prove at the end that no phase leaked a write onto the live repo.
    before_hashes = _hash_real_files()

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

        # Offline smoke tests must never spin up a real browser against the
        # live index.html — validator.validate() embeds a Playwright visual
        # QA pass that (unlike this suite's other phases) resolves its file
        # paths from repo ROOT, not from a redirectable module global.
        os.environ['MACRO_SKIP_VISUAL_QA'] = '1'

        # Run tests sequentially (each depends on prior output)
        test_analyzer(tmp_dir)
        test_renderer(tmp_dir)
        test_renderer_idempotent(tmp_dir)
        test_validator_offline(tmp_dir)
        test_snapshot(tmp_dir)
        test_monthly_archive(tmp_dir)
        test_healthcheck_module()
        test_oil_window_coverage(tmp_dir)
        test_yoy_missing_year_ago()
        test_no_positional_patching()
        test_chart_contracts()
        test_no_tdz_in_tab_builders()
        test_agent9_merge_clears_stale_fields(tmp_dir)
        test_no_real_file_mutation(before_hashes)

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
