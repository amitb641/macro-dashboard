#!/usr/bin/env python3
"""
Agent 6 — VALIDATOR (unified data + visual quality)
Independent quality agent. Runs after the renderer (Agent 4).
Four-pass validation:
  1. Internal consistency — compares index.html values vs raw_data.json
  2. Source verification — fresh API spot-checks against FRED/BLS
  3. Staleness detection — flags data beyond expected publication lags
  4. Visual QA — DOM-based checks via headless Chromium (if available)
Outputs: data/validation_report.json
Exit code: 0 = pass, 1 = critical divergences found
"""

import os, json, re, datetime, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

ROOT      = Path(__file__).parent.parent
HTML_FILE = ROOT / 'index.html'
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SIG_FILE  = ROOT / 'data' / 'signals.json'
RPT_FILE  = ROOT / 'data' / 'validation_report.json'

FRED_KEY  = os.environ.get('FRED_API_KEY', '')
BLS_KEY   = os.environ.get('BLS_API_KEY', '')

# ── Tolerance thresholds ──────────────────────────────────────────────
# How much divergence to allow before flagging (accounts for rounding)
TOLERANCES = {
    'rate':       0.05,   # percentage points (e.g. unemployment, CPI YoY)
    'index':      0.5,    # index level (CPI, PCE indices)
    'jobs':       5,      # thousands (payroll MoM)
    'price':      0.5,    # dollars (oil)
    'default':    0.2,    # catch-all
}

# Severity: how many checks must fail for exit code 1
CRITICAL_THRESHOLD = 3


# ═══════════════════════════════════════════════════════════════════════
# PASS 1: INTERNAL CONSISTENCY
#   Compare index.html rendered values against raw_data.json source
# ═══════════════════════════════════════════════════════════════════════

def _extract_js_const(html, var_name):
    """Extract a JS const object/array from HTML as a Python object."""
    pattern = rf'const {var_name}\s*=\s*(\{{[\s\S]*?\}}|\[[\s\S]*?\]);'
    m = re.search(pattern, html)
    if not m:
        return None
    raw = m.group(1)
    # Convert JS to JSON-ish: handle unquoted keys, trailing commas
    # Replace JS unquoted keys with quoted keys
    raw = re.sub(r'(?<=[{,\n])\s*([a-zA-Z_]\w*)\s*:', r'"\1":', raw)
    # Remove trailing commas before } or ]
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    # Handle single quotes → double quotes (but not inside strings)
    raw = raw.replace("'", '"')
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _yoy_from_index(series, n=1):
    """Compute YoY % for the nth most recent month from index series (newest-first).
    Uses calendar-month matching to handle data gaps."""
    if not series or len(series) < 13 + n:
        return None
    obs = series[n - 1]
    d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
    # Find same month, year ago
    for prev in series:
        pd = datetime.datetime.strptime(prev['date'], '%Y-%m-%d')
        if pd.year == d.year - 1 and pd.month == d.month:
            if prev['value'] == 0:
                return None
            return round((obs['value'] - prev['value']) / prev['value'] * 100, 1)
    return None


def check_internal(html, data, sig_vals):
    """Compare dashboard HTML against raw_data.json. Returns list of findings."""
    findings = []

    def _check(label, html_val, source_val, tol_key='default', severity='warning'):
        if html_val is None or source_val is None:
            return
        tol = TOLERANCES.get(tol_key, TOLERANCES['default'])
        diff = abs(float(html_val) - float(source_val))
        if diff > tol:
            findings.append({
                'check': label,
                'html_value': html_val,
                'source_value': source_val,
                'difference': round(diff, 3),
                'tolerance': tol,
                'severity': severity if diff > tol * 3 else 'warning',
                'pass': False,
            })
        else:
            findings.append({
                'check': label,
                'html_value': html_val,
                'source_value': source_val,
                'difference': round(diff, 3),
                'tolerance': tol,
                'severity': 'ok',
                'pass': True,
            })

    # ── CPI_MONTHLY vs raw CPI index ──
    cpi_monthly = _extract_js_const(html, 'CPI_MONTHLY')
    cpi_all = data.get('cpi_all', [])
    if cpi_monthly and cpi_all and len(cpi_all) >= 14:
        html_headline = cpi_monthly.get('headline', [])
        if html_headline:
            source_yoy = _yoy_from_index(cpi_all, 1)
            _check('CPI headline YoY (latest)', html_headline[-1], source_yoy, 'rate')

    cpi_core = data.get('cpi_core', [])
    if cpi_monthly and cpi_core and len(cpi_core) >= 14:
        html_core = cpi_monthly.get('core', [])
        if html_core:
            source_core = _yoy_from_index(cpi_core, 1)
            _check('CPI core YoY (latest)', html_core[-1], source_core, 'rate')

    # ── PCE_MONTHLY vs raw PCE index ──
    pce_monthly = _extract_js_const(html, 'PCE_MONTHLY')
    pce = data.get('pce', [])
    pce_core = data.get('pce_core', [])
    if pce_monthly and pce and len(pce) >= 14:
        html_pce_hl = pce_monthly.get('headline', [])
        if html_pce_hl:
            source_pce = _yoy_from_index(pce, 1)
            _check('PCE headline YoY (latest)', html_pce_hl[-1], source_pce, 'rate')
    if pce_monthly and pce_core and len(pce_core) >= 14:
        html_pce_core = pce_monthly.get('core', [])
        if html_pce_core:
            source_pce_core = _yoy_from_index(pce_core, 1)
            _check('PCE core YoY (latest)', html_pce_core[-1], source_pce_core, 'rate')

    # ── U_MONTHLY vs raw unemployment ──
    u_monthly = _extract_js_const(html, 'U_MONTHLY')
    unrate = data.get('unrate', [])
    if u_monthly and unrate:
        html_u = u_monthly.get('data', [])
        if html_u:
            _check('Unemployment rate (latest)', html_u[-1], unrate[0]['value'], 'rate')

    # ── NFP_VS_ADP BLS vs PAYEMS ──
    nfp_vs_adp = _extract_js_const(html, 'NFP_VS_ADP')
    payems = data.get('payems', [])
    if nfp_vs_adp and payems and len(payems) >= 2:
        html_bls = nfp_vs_adp.get('bls', [])
        if html_bls:
            source_nfp = round(payems[0]['value'] - payems[1]['value'])
            _check('NFP BLS MoM (latest)', html_bls[-1], source_nfp, 'jobs')

    # ── KPI strip values ──
    kpis_match = re.search(r'const KPIS\s*=\s*(\[[\s\S]*?\]);', html)
    if kpis_match and sig_vals:
        # Check unemployment KPI
        unemp_kpi = re.search(r'"metric":"unemp"[^}]*"val":"([\d.]+)%"', html)
        if unemp_kpi and 'unrate' in sig_vals:
            _check('KPI Unemployment', float(unemp_kpi.group(1)), sig_vals['unrate'], 'rate')

        # Check CPI KPI
        cpi_kpi = re.search(r'"metric":"cpi"[^}]*"val":"([\d.]+)%"', html)
        if cpi_kpi and 'cpi_yoy' in sig_vals:
            _check('KPI CPI YoY', float(cpi_kpi.group(1)), sig_vals['cpi_yoy'], 'rate')

        # Check Core PCE KPI
        pce_kpi = re.search(r'"metric":"pce"[^}]*"val":"[+]?([\d.]+)%"', html)
        if pce_kpi and 'core_pce_yoy' in sig_vals:
            _check('KPI Core PCE', float(pce_kpi.group(1)), sig_vals['core_pce_yoy'], 'rate')

    # ── Oil tiles vs OIL_ANNUAL ──
    oil_annual = _extract_js_const(html, 'OIL_ANNUAL')
    wti_annual = data.get('wti_annual', [])
    if oil_annual and wti_annual:
        html_wti_vals = oil_annual.get('wti', [])
        if html_wti_vals:
            # Check last completed year
            prev_yr = datetime.date.today().year - 1
            for obs in wti_annual:
                if isinstance(obs, dict) and int(obs['date'][:4]) == prev_yr:
                    _check(f'OIL_ANNUAL WTI {prev_yr}', html_wti_vals[-1],
                           round(obs['value'], 1), 'price')
                    break

    # ── HOUSING_MONTHLY Case-Shiller vs raw ──
    housing = _extract_js_const(html, 'HOUSING_MONTHLY')
    cs_hpi = data.get('cs_hpi', [])
    if housing and cs_hpi and len(cs_hpi) >= 14:
        html_cs = housing.get('caseShiller', [])
        if html_cs:
            source_cs = _yoy_from_index(cs_hpi, 1)
            _check('Case-Shiller YoY (latest)', html_cs[-1], source_cs, 'rate')

    # ── FC_MACRO actuals ──
    fc_match = re.search(r'const FC_MACRO\s*=\s*\{[\s\S]*?\};', html)
    if fc_match and unrate:
        prev_yr = datetime.date.today().year - 1
        # Check unemployment actual
        act_match = re.search(rf'act{str(prev_yr)[2:]}:\s*\[([^\]]+)\]', fc_match.group(0))
        if act_match:
            vals = [float(v.strip()) for v in act_match.group(1).split(',')]
            if len(vals) >= 2:
                # vals[1] = unemployment
                for obs in unrate:
                    yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
                    if yr == prev_yr and mo == 12:
                        _check(f'FC_MACRO unemployment {prev_yr}', vals[1], obs['value'], 'rate')
                        break

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 2: SOURCE VERIFICATION
#   Fresh API spot-checks against FRED/BLS to verify raw_data.json
# ═══════════════════════════════════════════════════════════════════════

def _fred_latest(series_id):
    """Fetch single latest observation from FRED. Returns (date, value) or None."""
    if not FRED_KEY:
        return None
    try:
        r = requests.get('https://api.stlouisfed.org/fred/series/observations',
                         params={'series_id': series_id, 'api_key': FRED_KEY,
                                 'file_type': 'json', 'sort_order': 'desc', 'limit': 1},
                         timeout=10)
        r.raise_for_status()
        obs = [o for o in r.json().get('observations', []) if o['value'] != '.']
        if obs:
            return obs[0]['date'], float(obs[0]['value'])
    except Exception:
        pass
    return None


def _bls_latest(series_id):
    """Fetch latest month from BLS. Returns (period_label, value) or None."""
    if not BLS_KEY:
        return None
    yr = datetime.date.today().year
    try:
        r = requests.post('https://api.bls.gov/publicAPI/v2/timeseries/data/', json={
            'seriesid': [series_id], 'startyear': str(yr - 1), 'endyear': str(yr),
            'registrationkey': BLS_KEY}, timeout=15)
        r.raise_for_status()
        body = r.json()
        if body.get('status') == 'REQUEST_SUCCEEDED':
            series = body['Results']['series'][0]['data']
            if series:
                latest = series[0]
                return f"{latest['periodName']} {latest['year']}", round(float(latest['value']))
    except Exception:
        pass
    return None


def check_sources(data):
    """Spot-check raw_data.json against fresh API calls. Returns list of findings."""
    findings = []
    apis_checked = 0

    def _verify(label, raw_val, api_result, tol_key='default'):
        nonlocal apis_checked
        if api_result is None:
            findings.append({
                'check': label, 'severity': 'skipped',
                'reason': 'API unavailable (key missing or timeout)',
                'pass': True,
            })
            return
        apis_checked += 1
        _, api_val = api_result if isinstance(api_result, tuple) else (None, api_result)
        tol = TOLERANCES.get(tol_key, TOLERANCES['default'])
        diff = abs(float(raw_val) - float(api_val))
        is_pass = diff <= tol
        severity = 'ok' if is_pass else ('critical' if diff > tol * 5 else 'divergence')
        findings.append({
            'check': label,
            'raw_data_value': raw_val,
            'fresh_api_value': api_val,
            'difference': round(diff, 3),
            'tolerance': tol,
            'severity': severity,
            'pass': is_pass,
        })
        if not is_pass:
            print(f'  🔴 SOURCE DIVERGENCE: {label} — raw={raw_val}, API={api_val} (Δ={diff:.2f})')

    # ── FRED spot-checks ──
    # Unemployment rate
    unrate = data.get('unrate', [])
    if unrate:
        result = _fred_latest('UNRATE')
        _verify('FRED UNRATE (latest)', unrate[0]['value'], result, 'rate')

    # CPI All Items
    cpi = data.get('cpi_all', [])
    if cpi:
        result = _fred_latest('CPIAUCSL')
        _verify('FRED CPIAUCSL (latest index)', cpi[0]['value'], result, 'index')

    # Core CPI
    cpi_core = data.get('cpi_core', [])
    if cpi_core:
        result = _fred_latest('CPILFESL')
        _verify('FRED CPILFESL (core CPI index)', cpi_core[0]['value'], result, 'index')

    # PCE
    pce = data.get('pce', [])
    if pce:
        result = _fred_latest('PCEPI')
        _verify('FRED PCEPI (PCE index)', pce[0]['value'], result, 'index')

    # Core PCE
    pce_core = data.get('pce_core', [])
    if pce_core:
        result = _fred_latest('PCEPILFE')
        _verify('FRED PCEPILFE (core PCE index)', pce_core[0]['value'], result, 'index')

    # 10Y Treasury
    dgs10 = data.get('dgs10')
    if dgs10 and isinstance(dgs10, dict):
        result = _fred_latest('DGS10')
        _verify('FRED DGS10 (10Y yield)', dgs10['value'], result, 'rate')

    # Fed Funds Rate
    ffr = data.get('ffr')
    if ffr and isinstance(ffr, dict):
        result = _fred_latest('FEDFUNDS')
        _verify('FRED FEDFUNDS', ffr['value'], result, 'rate')

    # Payrolls (PAYEMS)
    payems = data.get('payems', [])
    if payems:
        result = _fred_latest('PAYEMS')
        _verify('FRED PAYEMS (latest level, 000s)', payems[0]['value'], result, 'jobs')

    # Mortgage rate
    mtg = data.get('mortgage30', [])
    if mtg:
        result = _fred_latest('MORTGAGE30US')
        _verify('FRED MORTGAGE30US', mtg[0]['value'], result, 'rate')

    # ── BLS spot-check: Total Nonfarm ──
    bls_sectors = data.get('bls_sectors', {})
    total_nfp = bls_sectors.get('CES0000000001', [])
    if total_nfp:
        result = _bls_latest('CES0000000001')
        if result:
            _, api_val = result
            _verify('BLS Total Nonfarm (latest)', round(float(total_nfp[0]['value'])), (None, api_val), 'jobs')

    if apis_checked == 0:
        print('  ⚠  No API keys available — source verification skipped')
    else:
        print(f'  ✅ Source verification: {apis_checked} API spot-checks completed')

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3: STALENESS CHECK
#   Flag data that hasn't been updated within expected windows
# ═══════════════════════════════════════════════════════════════════════

def check_staleness(data, collected_at):
    """Check if any data series are stale beyond expected lag."""
    findings = []
    today = datetime.date.today()

    # Expected max lag (in days) from today for each series
    EXPECTED_LAGS = {
        'unrate':    45,   # Monthly, ~1 month lag
        'cpi_all':   75,   # Monthly, ~2-3 week lag; can span 2 release cycles
        'cpi_core':  75,
        'pce':       95,   # Monthly, ~4 week lag; can span 2 release cycles
        'pce_core':  95,
        'payems':    40,   # Monthly, ~1 week lag from reference period
        'cs_hpi':   100,   # Monthly, ~2 month lag (Case-Shiller)
        'mortgage30': 10,  # Weekly
    }

    for key, max_lag in EXPECTED_LAGS.items():
        series = data.get(key, [])
        if not series:
            findings.append({
                'check': f'Staleness: {key}',
                'severity': 'warning',
                'reason': 'Series missing from raw_data',
                'pass': False,
            })
            continue

        if isinstance(series, list) and series:
            latest_date = datetime.date.fromisoformat(series[0]['date'])
            age_days = (today - latest_date).days
            is_stale = age_days > max_lag
            findings.append({
                'check': f'Staleness: {key}',
                'latest_date': series[0]['date'],
                'age_days': age_days,
                'max_lag_days': max_lag,
                'severity': 'stale' if is_stale else 'ok',
                'pass': not is_stale,
            })
            if is_stale:
                print(f'  ⏰ STALE: {key} — last update {series[0]["date"]} ({age_days}d ago, max {max_lag}d)')

    # Check collection timestamp itself
    if collected_at:
        try:
            coll_dt = datetime.datetime.fromisoformat(collected_at.replace('Z', '+00:00'))
            age_hrs = (datetime.datetime.now(datetime.timezone.utc) - coll_dt).total_seconds() / 3600
            findings.append({
                'check': 'Collection recency',
                'collected_at': collected_at,
                'age_hours': round(age_hrs, 1),
                'severity': 'stale' if age_hrs > 168 else 'ok',  # >7 days
                'pass': age_hrs <= 168,
            })
        except Exception:
            pass

    return findings


# ═══════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════

def check_visual():
    """Run DOM-based visual QA checks if Playwright is available.
    Returns list of findings from the visual QA agent."""
    try:
        # Add scripts dir to path for visual_qa import
        scripts_dir = str(Path(__file__).parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        import visual_qa
        # Reset visual_qa state
        visual_qa.PASS = 0
        visual_qa.FAIL = 0
        visual_qa.findings = []

        # Run visual QA silently
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            visual_qa.run_visual_qa(take_screenshots=False)
        except SystemExit:
            pass
        finally:
            sys.stdout = old_stdout

        # Convert visual QA findings to our format
        results = []
        for f in visual_qa.findings:
            results.append({
                'check': f'Visual: {f["category"]} — {f["check"]}',
                'severity': f.get('severity', 'warning'),
                'pass': f.get('pass', False),
                'detail': f.get('detail', ''),
            })
        return results
    except ImportError:
        return [{
            'check': 'Visual QA',
            'severity': 'skipped',
            'pass': True,
            'reason': 'Playwright not installed (pip install playwright)',
        }]
    except Exception as e:
        return [{
            'check': 'Visual QA',
            'severity': 'skipped',
            'pass': True,
            'reason': f'Visual QA error: {e}',
        }]


def build_report(internal, sources, staleness, visual=None):
    """Compile all findings into a validation report."""
    if visual is None:
        visual = []
    all_findings = internal + sources + staleness + visual

    n_pass = sum(1 for f in all_findings if f.get('pass'))
    n_fail = sum(1 for f in all_findings if not f.get('pass') and f.get('severity') != 'skipped')
    n_skip = sum(1 for f in all_findings if f.get('severity') == 'skipped')
    n_critical = sum(1 for f in all_findings if f.get('severity') in ('critical', 'divergence'))

    status = 'PASS'
    if n_critical >= CRITICAL_THRESHOLD:
        status = 'FAIL'
    elif n_fail > 0:
        status = 'WARN'

    report = {
        'validated_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'status': status,
        'summary': {
            'total_checks': len(all_findings),
            'passed': n_pass,
            'failed': n_fail,
            'skipped': n_skip,
            'critical_divergences': n_critical,
        },
        'internal_consistency': internal,
        'source_verification': sources,
        'staleness': staleness,
        'visual_qa': visual,
    }
    return report


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def validate():
    print('[Agent 6 — Validator] Starting data quality checks...')

    # Load inputs
    if not HTML_FILE.exists():
        print('ERROR: index.html missing'); sys.exit(1)
    if not RAW_FILE.exists():
        print('ERROR: raw_data.json missing'); sys.exit(1)

    html = HTML_FILE.read_text(encoding='utf-8')
    raw = json.loads(RAW_FILE.read_text())
    data = raw.get('data', {})
    collected_at = raw.get('collected_at', '')

    sig_vals = {}
    if SIG_FILE.exists():
        sig = json.loads(SIG_FILE.read_text())
        sig_vals = sig.get('values', {})

    # Pass 1: Internal consistency
    print('\n  ── Pass 1: Internal Consistency (HTML vs raw_data) ──')
    internal = check_internal(html, data, sig_vals)
    ic_pass = sum(1 for f in internal if f.get('pass'))
    ic_fail = sum(1 for f in internal if not f.get('pass'))
    print(f'  {ic_pass} passed, {ic_fail} failed')

    # Pass 2: Source verification (fresh API calls)
    print('\n  ── Pass 2: Source Verification (fresh API spot-checks) ──')
    sources = check_sources(data)

    # Pass 3: Staleness
    print('\n  ── Pass 3: Staleness Checks ──')
    staleness = check_staleness(data, collected_at)
    stale_count = sum(1 for f in staleness if f.get('severity') == 'stale')
    if stale_count:
        print(f'  {stale_count} series stale')
    else:
        print(f'  All series within expected freshness windows')

    # Pass 4: Visual QA (DOM checks via Playwright, if available)
    print('\n  ── Pass 4: Visual QA (DOM-based rendering checks) ──')
    visual = check_visual()
    vqa_pass = sum(1 for f in visual if f.get('pass'))
    vqa_fail = sum(1 for f in visual if not f.get('pass') and f.get('severity') != 'skipped')
    vqa_skip = sum(1 for f in visual if f.get('severity') == 'skipped')
    if vqa_skip:
        print(f'  Skipped ({visual[0].get("reason", "unavailable")})')
    else:
        print(f'  {vqa_pass} passed, {vqa_fail} failed')

    # Build and save report
    report = build_report(internal, sources, staleness, visual)
    RPT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')

    # Summary
    s = report['summary']
    status = report['status']
    status_icon = '✅' if status == 'PASS' else '⚠️' if status == 'WARN' else '❌'
    print(f'\n[Agent 6] {status_icon} Validation {status} — '
          f'{s["passed"]}/{s["total_checks"]} checks passed, '
          f'{s["critical_divergences"]} critical divergences')
    print(f'  Report saved to {RPT_FILE.name}')

    # Print divergences for visibility
    for section_name, section in [('Internal', internal), ('Source', sources),
                                   ('Staleness', staleness), ('Visual', visual)]:
        for f in section:
            if not f.get('pass') and f.get('severity') != 'skipped':
                print(f'  → [{section_name}] {f["check"]}: {f.get("severity", "fail")}')

    return status != 'FAIL'


if __name__ == '__main__':
    sys.exit(0 if validate() else 1)
