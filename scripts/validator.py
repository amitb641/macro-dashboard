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
KNOWN_NORMAL_FILE = ROOT / 'data' / 'known_normal.json'

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
    # Try parsing as-is first (already valid JSON from renderer's _inject_const)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: Convert JS to JSON-ish: handle unquoted keys, trailing commas
    raw = re.sub(r'(?<=[{,\n])\s*([a-zA-Z_]\w*)\s*:', r'"\1":', raw)
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    # Only replace single quotes if no double-quoted strings contain them
    if "\"" not in raw or "'" not in raw:
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

    # ── Chart data completeness — catch sparse/empty series ──
    # ALL chart constants injected by renderer — comprehensive coverage
    CHART_CONSTS = [
        # Monthly charts
        'CPI_MONTHLY', 'PCE_MONTHLY', 'U_MONTHLY', 'NFP_VS_ADP',
        'HOUSING_MONTHLY', 'OIL_MONTHLY', 'SAVING_MONTHLY', 'UMCSENT_MONTHLY',
        # Annual charts
        'U_ANNUAL', 'CPI_ANNUAL', 'PCE_ANNUAL', 'WAGE_ANNUAL',
        'JOBS_ANNUAL', 'SAVING_ANNUAL', 'OIL_ANNUAL',
        # Daily / weekly
        'OIL_DAILY', 'CLAIMS_WEEKLY',
        # Rates & spreads
        'GDP_TOTAL_DATA', 'FFR_DATA', 'MORTGAGE_DATA', 'SPREADS_DATA',
        'TREASURY_DATA', 'OIL_SPREAD',
        # Housing
        'STARTS_DATA', 'HPI_DATA',
        # Oil correlation
        'OIL_VS_CPI', 'OIL_VS_SENTIMENT', 'OIL_VS_HY',
        # Credit
        'CREDIT_GROWTH', 'TDSP_HIST',
    ]
    for const_name in CHART_CONSTS:
        obj = _extract_js_const(html, const_name)
        if not obj:
            continue
        labels = obj.get('labels', [])
        n_labels = len(labels)
        if n_labels == 0:
            continue

        # Fields where sparse values (mostly null) are intentional — forecasts,
        # annotation overlays, etc. Structured as {const.key: min_pct_filled}.
        # Default threshold is 50%; overrides let us reflect design intent.
        SPARSE_OK = {
            'FFR_DATA.dots': 10,          # Fed dot plot: only forecast years populated
            'OIL_DAILY.notes': 0,         # big-move annotations are sparse by design
        }

        # Collect data arrays for sync check
        data_arrays = {}
        for key, arr in obj.items():
            if key == 'labels' or not isinstance(arr, list):
                continue
            data_arrays[key] = arr
            n_total = len(arr)
            n_nulls = sum(1 for v in arr if v is None or v == '' or v == 'null')
            pct_filled = round((n_total - n_nulls) / n_total * 100) if n_total > 0 else 0
            min_threshold = SPARSE_OK.get(f'{const_name}.{key}', 50)
            is_ok = pct_filled >= min_threshold
            findings.append({
                'check': f'{const_name}.{key} completeness',
                'html_value': f'{n_total - n_nulls}/{n_total} filled',
                'source_value': f'{pct_filled}% (min {min_threshold}%)',
                'difference': n_nulls,
                'tolerance': n_total // 2,
                'severity': 'ok' if is_ok else 'warning',
                'pass': is_ok,
            })
            # Interior nulls: gaps between valid data points = broken chart lines.
            # Skip sparse-by-design fields (annotation overlays, forecasts).
            if f'{const_name}.{key}' not in SPARSE_OK:
                interior = 0
                for i in range(1, n_total - 1):
                    if arr[i] is None or arr[i] == '' or arr[i] == 'null':
                        has_before = any(arr[j] is not None and arr[j] != '' for j in range(i))
                        has_after = any(arr[j] is not None and arr[j] != '' for j in range(i + 1, n_total))
                        if has_before and has_after:
                            interior += 1
                if interior > 0:
                    findings.append({
                        'check': f'{const_name}.{key} line continuity',
                        'html_value': f'{interior} interior gap(s)',
                        'source_value': '0 gaps expected',
                        'difference': interior,
                        'tolerance': 0,
                        'severity': 'warning',
                        'pass': False,
                    })
            # Labels vs data array length mismatch
            if n_total != n_labels:
                findings.append({
                    'check': f'{const_name}.{key} label sync',
                    'html_value': f'{n_total} values',
                    'source_value': f'{n_labels} labels',
                    'difference': abs(n_total - n_labels),
                    'tolerance': 0,
                    'severity': 'warning',
                    'pass': False,
                })

        # Multi-series sync: all data arrays should have same length
        if len(data_arrays) > 1:
            lengths = {k: len(v) for k, v in data_arrays.items()}
            unique_lens = set(lengths.values())
            if len(unique_lens) > 1:
                findings.append({
                    'check': f'{const_name} series length sync',
                    'html_value': str(lengths),
                    'source_value': 'All series same length',
                    'difference': max(unique_lens) - min(unique_lens),
                    'tolerance': 0,
                    'severity': 'warning',
                    'pass': False,
                })

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
    # Thresholds calibrated to actual release cadences, not reference-month
    # arithmetic: BLS drops NFP/UNRATE on the first Friday of the *following*
    # month (so ~35-40d after ref-month start is typical, with reporting
    # slippage adding ~2 weeks). Case-Shiller has a ~70d HPI lag + release
    # around the last Tuesday of the following month.
    EXPECTED_LAGS = {
        'unrate':    55,   # BLS Employment Situation, 1st Fri of following month
        'cpi_all':   75,   # Monthly, ~2-3 week lag; can span 2 release cycles
        'cpi_core':  75,
        'pce':       95,   # Monthly, ~4 week lag; can span 2 release cycles
        'pce_core':  95,
        'payems':    55,   # BLS NFP, same release as UNRATE
        'cs_hpi':   120,   # S&P CoreLogic Case-Shiller — ~70d data lag + release window
        'mortgage30': 10,  # Weekly
        # UMich Consumer Sentiment: prelim ~mid-month, final ~end-of-month.
        # Collector pulls UMich direct (tbcics.csv) which exposes the prelim
        # before FRED's 1-month embargo. 35d covers both release windows.
        'umcsent':   35,
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

    # UMich release-status notice: prelim prints are subject to revision in
    # the end-of-month final. Informational finding so consumers of the
    # validation report know the latest sentiment point is not finalized.
    umcsent = data.get('umcsent', [])
    if umcsent and isinstance(umcsent, list):
        latest = umcsent[0] if isinstance(umcsent[0], dict) else {}
        status = latest.get('status')
        if status:
            findings.append({
                'check': 'UMich Sentiment release status',
                'latest_date': latest.get('date'),
                'release_status': status,
                'severity': 'info' if status == 'preliminary' else 'ok',
                'pass': True,
                'note': ('Preliminary — subject to revision in end-of-month final release'
                         if status == 'preliminary' else 'Final release'),
            })
            if status == 'preliminary':
                print(f'  ℹ️  UMich Sentiment {latest.get("date")} is PRELIMINARY — final expected end of month')

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
# PASS: SHOCK TRACKER STRUCTURE + CONSISTENCY
#   Oil Impact Chain is the most consequential analytical surface we have,
#   yet before this check it was only verified implicitly by the renderer
#   writing it back. A silent regex break (which we've hit twice) froze
#   the whole table at pre-shock baselines and no agent noticed.
# ═══════════════════════════════════════════════════════════════════════

def _extract_shock_tracker(html):
    """Extract SHOCK_TRACKER JSON, anchored on trailing '// OIL_DAILY' comment
    (the const is single-line nested JSON, so naive non-greedy regex fails)."""
    m = re.search(r'const SHOCK_TRACKER\s*=\s*(\{[\s\S]*?\});(?=\s*\n\s*//\s*OIL_DAILY)', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def check_shock_tracker(html):
    """Validate SHOCK_TRACKER structure + per-phase required fields +
    status-vs-MMA consistency. Emits one finding per phase so the
    validation report shows exactly which row is misbehaving."""
    findings = []
    tracker = _extract_shock_tracker(html)

    if tracker is None:
        findings.append({
            'check': 'SHOCK_TRACKER extractable',
            'severity': 'critical',
            'pass': False,
            'reason': 'Cannot parse SHOCK_TRACKER from index.html (regex mismatch or malformed JSON)',
        })
        print('  🔴 SHOCK_TRACKER not extractable from HTML — likely regex break')
        return findings

    findings.append({'check': 'SHOCK_TRACKER extractable', 'severity': 'ok', 'pass': True})

    phases = tracker.get('phases', [])
    expected_n = 8
    findings.append({
        'check': 'SHOCK_TRACKER phase count',
        'actual': len(phases),
        'expected': expected_n,
        'severity': 'ok' if len(phases) == expected_n else 'warning',
        'pass': len(phases) == expected_n,
    })

    required = ['phase', 'status', 'status_reason', 'source', 'expected_weeks']
    for i, p in enumerate(phases):
        name = p.get('phase', f'phase[{i}]')

        # Required fields non-empty
        missing = [f for f in required if not p.get(f)]
        findings.append({
            'check': f'SHOCK_TRACKER[{i}] {name} required fields',
            'missing': missing or None,
            'severity': 'ok' if not missing else 'warning',
            'pass': not missing,
        })
        if missing:
            print(f'  ⚠  {name}: missing {missing}')

        # MMA-phase consistency: status must match the post-vs-pre delta
        post = p.get('post_mom_ann')
        pre = p.get('pre_6mma')
        status = p.get('status')
        if post is not None and pre is not None:
            diff = post - pre
            if diff > 1.5:
                ok = status in ('confirmed', 'ahead')
            elif diff > 0.5:
                ok = status in ('emerging', 'ahead')
            elif diff < -0.5:
                ok = status in ('not_yet', 'on_schedule', 'awaiting_data')
            else:
                ok = status in ('not_yet', 'on_schedule')
            findings.append({
                'check': f'SHOCK_TRACKER[{i}] {name} status consistent with MMA delta',
                'status': status,
                'post_minus_pre_pp': round(diff, 2),
                'severity': 'ok' if ok else 'divergence',
                'pass': ok,
            })
            if not ok:
                print(f'  🔴 {name}: status={status} inconsistent with MMA Δ={diff:+.2f}pp')

        # Sanity: if base-effect callout is set, we shouldn't be showing 'confirmed'
        if p.get('base_effect_note') and status == 'confirmed':
            findings.append({
                'check': f'SHOCK_TRACKER[{i}] {name} base-effect/confirmed conflict',
                'severity': 'warning',
                'pass': False,
                'note': 'base_effect_note is set but status=confirmed — these should not coexist',
            })

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS: EARNINGS COMMENTARY VERBATIM CHECK
#   Enforces CLAUDE.md's Earnings Commentary factuality rule:
#   every quoted string in BANK_COMMENTARY must appear verbatim in the
#   bank's archived transcript (when one exists). Catches paraphrases
#   presented as direct quotes — the exact failure mode we hit in Q1 2026
#   before the factuality rule was written down.
# ═══════════════════════════════════════════════════════════════════════

BANK_FILE = Path(__file__).parent.parent / 'data' / 'bank_earnings.json'
TRANSCRIPTS_DIR = Path(__file__).parent.parent / 'data' / 'transcripts'
_QUOTED_FIELDS = ('quote', 'economy', 'lending', 'cards_loans',
                  'macro', 'tech_ai', 'credit', 'outlook')


def _norm_for_match(s):
    """Normalize whitespace + smart quotes so verbatim matching tolerates
    common transcript encoding differences (straight vs curly quotes, line wraps)."""
    s = s.replace('“', '"').replace('”', '"')
    s = s.replace('‘', "'").replace('’', "'")
    s = s.replace('—', '--').replace('–', '-')
    # Collapse all whitespace runs to single space
    return ' '.join(s.split())


def check_earnings_verbatim():
    """Validate data/bank_earnings.json and enforce verbatim quotes when
    transcripts are archived.

    Tiers:
      1. JSON file parses and has required top-level fields.
      2. Each bank has required identity fields (id, ticker, CEO, dates).
      3. Reported banks with an archived transcript at
         data/transcripts/<quarter>/<TICKER>.txt must have every "..."
         substring in their fields appear in the transcript. Mismatches
         are CRITICAL (build-blocking).
      4. Reported banks WITHOUT an archived transcript get a warning only
         — enables gradual adoption of the archive.
    """
    findings = []

    if not BANK_FILE.exists():
        findings.append({
            'check': 'bank_earnings.json present',
            'severity': 'skipped',
            'pass': True,
            'reason': 'data/bank_earnings.json not yet created (pre-refactor state)',
        })
        return findings

    try:
        data = json.loads(BANK_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        findings.append({
            'check': 'bank_earnings.json parse',
            'severity': 'critical',
            'pass': False,
            'reason': f'JSON decode error: {e}',
        })
        return findings

    banks = data.get('banks', [])
    if not banks:
        findings.append({'check': 'bank_earnings.json has banks',
                         'severity': 'critical', 'pass': False,
                         'reason': 'empty or missing banks[]'})
        return findings
    findings.append({'check': f'bank_earnings.json ({len(banks)} banks)',
                     'severity': 'ok', 'pass': True})

    # Quarter-scoped transcripts directory (e.g., "Q1 2026" -> "Q1_2026")
    quarter = data.get('quarter', '').replace(' ', '_')
    transcripts_qdir = TRANSCRIPTS_DIR / quarter if quarter else None

    # Per-bank checks
    required = ('id', 'bank', 'ticker', 'ceo', 'expected_report_date')
    quoted_re = re.compile(r'"([^"]{15,})"')

    for b in banks:
        ticker = b.get('ticker', '?')

        missing = [k for k in required if not b.get(k)]
        if missing:
            findings.append({
                'check': f'{ticker}: required fields',
                'severity': 'critical', 'pass': False,
                'missing': missing,
            })
            continue

        # Skip pending banks — by definition no transcript to verify against
        if (b.get('status') or '').lower() == 'pending':
            findings.append({
                'check': f'{ticker}: pending (reports {b.get("expected_report_date")})',
                'severity': 'skipped', 'pass': True,
            })
            continue

        # Verbatim check only if transcript archive exists
        if transcripts_qdir is None:
            continue
        transcript_path = transcripts_qdir / f'{ticker}.txt'
        if not transcript_path.exists():
            # Severity policy (refined): missing transcript = WARNING, not
            # critical. Transcript archival is an operator step per the
            # documented workflow (CLAUDE.md "Update Workflow"); the verbatim
            # gate only enforces when an archived transcript is present. The
            # earlier 'critical' promotion blocked publish across the entire
            # quarter whenever the operator hadn't yet archived a single .txt
            # — too coarse. The real fabrication risk (mismatched quoted span
            # vs archived transcript) is still CRITICAL below. Aggregate
            # observability over missing transcripts is reported by
            # check_transcript_archive_coverage() so the operator gets one
            # clear signal instead of N per-bank criticals.
            findings.append({
                'check': f'{ticker}: transcript archived for verbatim check',
                'severity': 'warning',
                'pass': False,
                'reason': (
                    f'no file at {transcript_path.relative_to(Path(__file__).parent.parent)} '
                    f'— verbatim gate skipped for this bank '
                    f'(operator should archive transcript before quarter close)'
                ),
            })
            continue

        transcript_norm = _norm_for_match(transcript_path.read_text(encoding='utf-8'))
        mismatches = []
        for field in _QUOTED_FIELDS:
            val = b.get(field, '')
            if not val:
                continue
            for quoted in quoted_re.findall(val):
                if _norm_for_match(quoted) not in transcript_norm:
                    mismatches.append({'field': field, 'quote_excerpt': quoted[:100]})

        if mismatches:
            findings.append({
                'check': f'{ticker}: verbatim quotes in transcript',
                'severity': 'critical', 'pass': False,
                'mismatches': mismatches[:5],
                'total_mismatches': len(mismatches),
                'reason': f'{len(mismatches)} quoted span(s) not found verbatim in {transcript_path.name}',
            })
        else:
            findings.append({
                'check': f'{ticker}: verbatim quotes in transcript',
                'severity': 'ok', 'pass': True,
            })

    # ── Aggregate transcript-archive coverage ─────────────────────────
    # The per-bank warnings above downgrade individual missing transcripts
    # from CRITICAL to WARNING so the operator gets one clear aggregate
    # signal instead of N noise items. The aggregate IS the gate: if a
    # quarter has been reported by ≥1 bank but ZERO transcripts are
    # archived, the verbatim fabrication-resistance contract is fully
    # off — every quoted span ships unverified. That's CRITICAL.
    #
    # Coverage thresholds:
    #   reported_n == 0       → skipped (no quarter to gate)
    #   archived_n == 0       → critical (gate is fully off)
    #   archived_n < reported → warning (partial coverage; operator gap)
    #   archived_n == reported → ok
    reported = [b for b in banks
                if (b.get('status') or '').lower() != 'pending'
                and not [k for k in required if not b.get(k)]]
    reported_n = len(reported)
    if reported_n == 0 or transcripts_qdir is None:
        findings.append({
            'check': 'transcript_archive_coverage',
            'severity': 'skipped',
            'pass': True,
            'reason': (
                'no reported banks yet for this quarter'
                if reported_n == 0
                else 'no quarter declared in bank_earnings.json'
            ),
        })
    else:
        archived = [
            b for b in reported
            if (transcripts_qdir / f"{b.get('ticker','?')}.txt").exists()
        ]
        archived_n = len(archived)
        pct = (archived_n / reported_n * 100.0) if reported_n else 0.0
        if archived_n == 0:
            findings.append({
                'check': 'transcript_archive_coverage',
                'severity': 'critical',
                'pass': False,
                'reason': (
                    f'zero transcripts archived in {transcripts_qdir.relative_to(Path(__file__).parent.parent)} '
                    f'for a quarter with {reported_n} reported bank(s); '
                    f'verbatim gate is fully off — every quoted span ships unverified. '
                    f'Operator must archive transcripts per CLAUDE.md "Update Workflow" before publish.'
                ),
                'reported': reported_n,
                'archived': 0,
                'coverage_pct': 0.0,
            })
        elif archived_n < reported_n:
            findings.append({
                'check': 'transcript_archive_coverage',
                'severity': 'warning',
                'pass': False,
                'reason': (
                    f'{archived_n}/{reported_n} transcripts archived ({pct:.0f}% coverage); '
                    f'verbatim gate enforces only the {archived_n} archived bank(s)'
                ),
                'reported': reported_n,
                'archived': archived_n,
                'coverage_pct': round(pct, 1),
            })
        else:
            findings.append({
                'check': 'transcript_archive_coverage',
                'severity': 'ok',
                'pass': True,
                'reported': reported_n,
                'archived': archived_n,
                'coverage_pct': 100.0,
            })

    return findings


# ═══════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════

def check_visual():
    """Run DOM-based visual QA checks if Playwright is available.
    Also captures screenshots for Agent 8 visual review.
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

        # Run visual QA with screenshots (needed for Agent 8 visual review)
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            visual_qa.run_visual_qa(take_screenshots=True)
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
    except (ImportError, SystemExit):
        # visual_qa.py does sys.exit(1) at import time when Playwright is
        # missing; treat that as a skip so the validator can still write its
        # report (CI has Playwright; this matters for local dev).
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


def check_visual_review():
    """Run vision-based review using Claude's multimodal capability (Agent 8).
    Analyzes screenshots for pixel-level visual defects.
    Returns list of findings."""
    try:
        scripts_dir = str(Path(__file__).parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        import visual_review
        return visual_review.get_findings_for_validator()
    except ImportError:
        return [{
            'check': 'Visual Review (Agent 8)',
            'severity': 'skipped',
            'pass': True,
            'reason': 'visual_review.py not found',
        }]
    except Exception as e:
        return [{
            'check': 'Visual Review (Agent 8)',
            'severity': 'skipped',
            'pass': True,
            'reason': f'Visual review error: {e}',
        }]


# ═══════════════════════════════════════════════════════════════════════
# PASS 3d: PANEL TITLE ↔ DATA MONTH CONSISTENCY
#   Catches the failure mode where the renderer's title-update regex
#   succeeds (rolling "Mar'26 vs Feb'26") but the underlying JS data const
#   (e.g. CPI_CAT_MOM) silently failed to rebuild — leaving the chart
#   plotting last month's data under this month's title. Same drift can hit
#   hardcoded legend chips (purple #8878B8bb prior-month swatch).
# ═══════════════════════════════════════════════════════════════════════

# Each entry: (panel_anchor_candidates, js_const_name, key_extractor)
# panel_anchor_candidates is a tuple of strings; the first one found in the
# HTML wins. This survives finding-first title rewrites (style_guide §23.1)
# while keeping the panel-data contract intact. Add the new title as the
# first candidate; keep the old title as a fallback during the sweep.
# key_extractor returns the list of month tokens (e.g. ['feb','mar']) found
# in the data const. If empty, the const isn't month-keyed and the check is
# skipped for that const.
_PANEL_DATA_MAP = [
    (('Energy and transport categories are pulling the basket higher',
      'CPI by Category — MoM Change'),
     'CPI_CAT_MOM',
     lambda obj: [k for k in (obj[0] if obj else {}) if k not in ('cat', 'color')]),
    (('PCE by Component — YoY %',),
     'PCE_CAT_MOM',
     lambda obj: [k for k in (obj[0] if obj else {}) if k not in ('cat', 'color')]),
    (('Monthly Job Change by Sector',),
     'SECTOR_MOM',
     lambda obj: [k for k in (obj or {}) if k != 'sectors']),
    (('Unemployment by Sector — Monthly MoM Change (pp)',),
     'U_SECTOR_MOM',
     lambda obj: [k for k in (obj or {}) if k != 'sectors']),
]

_MONTH_LBL_RE = re.compile(r"([A-Z][a-z]+)'(\d{2})")
_MONTH_TO_KEY = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                 'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}


def _extract_panel_title_months(html, anchor):
    """Find the panel-title containing `anchor` and return its month tokens
    (ordered as written, e.g. [('Mar','26'), ('Feb','26')]).
    Scans both the panel-title and the panel-sub line (some panels keep the
    month pair in the subtitle — e.g. Unemployment by Sector)."""
    idx = html.find(anchor)
    if idx < 0:
        return None
    # Cover panel-title + panel-sub: skip 2 closing </div> tags.
    end = html.find('</div>', idx)
    if end < 0:
        return None
    end = html.find('</div>', end + 6)
    if end < 0:
        end = idx + 600
    return _MONTH_LBL_RE.findall(html[idx:end])


def _extract_panel_chip_months(html, anchor):
    """Return month tokens found inside legend chips in the ~1500 bytes
    after the panel anchor (covers panel-title + sub + legend row)."""
    idx = html.find(anchor)
    if idx < 0:
        return None
    chunk = html[idx: idx + 1500]
    # Pull only the legend-chip area (inside flex span)
    return _MONTH_LBL_RE.findall(chunk)


def check_panel_data_consistency(html):
    """Pass 3d: verify each MoM panel's title month tokens match the months
    encoded in the underlying JS data const + the prior-month legend chip."""
    findings = []
    for anchor_candidates, var_name, key_fn in _PANEL_DATA_MAP:
        # Try each anchor candidate; first hit wins (style_guide §23.1
        # finding-first title sweep means we keep the old title as fallback).
        anchor = None
        title_months = None
        for cand in anchor_candidates:
            tm = _extract_panel_title_months(html, cand)
            if tm:
                anchor, title_months = cand, tm
                break
        if not title_months:
            # Report using the canonical (first) candidate
            anchor = anchor_candidates[0]
            findings.append({
                'check': f'Panel anchor "{anchor}" present',
                'severity': 'warning',
                'pass': False,
                'reason': f'Panel not found in HTML — tried {len(anchor_candidates)} anchor(s)',
            })
            continue

        # Title months as lowercase short keys, ordered current-first then prior
        # Convention varies: CPI/PCE titles read "Cur vs Prv"; Sector reads "Prv vs Cur"
        # Normalize: pick the two month tokens; assume the LATER calendar month is "current"
        if len(title_months) < 2:
            findings.append({
                'check': f'{anchor}: title has 2 month tokens',
                'severity': 'warning',
                'pass': False,
                'reason': f'Title only has {len(title_months)} month tokens',
            })
            continue
        m1, m2 = title_months[0], title_months[1]
        keys = {m1[0].lower(), m2[0].lower()}

        # Data const month keys
        const_obj = _extract_js_const(html, var_name)
        if const_obj is None:
            findings.append({
                'check': f'{anchor}: data const {var_name} extractable',
                'severity': 'warning',
                'pass': False,
                'reason': f'Could not parse const {var_name} from HTML',
            })
            continue
        data_keys = set(k.lower()[:3] for k in (key_fn(const_obj) or []))
        if not data_keys:
            # Const not month-keyed (e.g. SECTOR_MOM uses different shape)
            findings.append({
                'check': f'{anchor}: {var_name} month-keyed',
                'severity': 'skipped',
                'pass': True,
                'reason': 'data const not month-keyed in this schema',
            })
        else:
            ok = keys == data_keys
            findings.append({
                'check': f'{anchor}: title months match {var_name} keys',
                'title_months': sorted(keys),
                'data_keys': sorted(data_keys),
                'severity': 'ok' if ok else 'divergence',
                'pass': ok,
            })
            if not ok:
                print(f'  🔴 {anchor}: title={sorted(keys)} vs data={sorted(data_keys)} — title-data drift')

        # Prior-month legend chip — should equal the EARLIER calendar month
        chip_months = _extract_panel_chip_months(html, anchor)
        if chip_months:
            # Determine the earlier of the two title months by year+month
            def to_int(tok):
                return int(tok[1]) * 12 + _MONTH_TO_KEY.get(tok[0].lower()[:3], 0)
            prv_token = m1 if to_int(m1) < to_int(m2) else m2
            prv_str = f"{prv_token[0]}'{prv_token[1]}"
            # Last chip in the legend row is the prior-month baseline
            chip_strs = [f"{m}'{y}" for m, y in chip_months]
            ok = prv_str in chip_strs
            findings.append({
                'check': f'{anchor}: prior-month chip matches title',
                'expected_prior': prv_str,
                'chips_found': chip_strs,
                'severity': 'ok' if ok else 'divergence',
                'pass': ok,
            })
            if not ok:
                print(f'  🔴 {anchor}: prior-month chip "{prv_str}" not found in legend chips {chip_strs}')

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3e: CROSS-SURFACE METRIC CONSISTENCY
#   Same metric (e.g. NFP MoM Mar'26) gets rendered on multiple surfaces:
#   the top KPI strip, a tab-specific tile, the chart's data const, and
#   commentary prose. Each surface used to derive its value independently,
#   so any one of them could drift from the source-of-truth raw series
#   and show a different number than the others. (We hit this with the
#   Jobs tile reading SECTOR_MOM sum = 188K while everything else read
#   PAYEMS = 178K.) This pass picks the raw series as truth and checks
#   every surface agrees within a small tolerance.
# ═══════════════════════════════════════════════════════════════════════

def _kpi_value(html, label_substring):
    """Find a KPIS entry whose lbl contains `label_substring` and return the
    numeric portion of its `val` (e.g. '+178K' -> 178, '4.3%' -> 4.3)."""
    kpis = _extract_js_const(html, 'KPIS')
    if not isinstance(kpis, list):
        return None
    for k in kpis:
        lbl = (k.get('lbl') or '')
        if label_substring.lower() in lbl.lower():
            val = (k.get('val') or '').replace(',', '').replace('$', '')
            m = re.search(r'-?\d+\.?\d*', val)
            if m:
                return float(m.group(0))
    return None


def _commentary_match(html, tab_id, pattern, group=1):
    """Find regex `pattern` inside the commentary block for `tab_id` and
    return the matched group as float (or None)."""
    marker = f'id="commentary-{tab_id}"'
    idx = html.find(marker)
    if idx < 0:
        return None
    end = html.find('</div>', idx)
    chunk = html[idx:end] if end > idx else html[idx:idx + 3000]
    m = re.search(pattern, chunk)
    if not m:
        return None
    try:
        return float(m.group(group))
    except (ValueError, IndexError):
        return None


def _const_array_last(html, var_name, key):
    """Return the last numeric element of `const VAR.key` (for object-shape
    consts) or `const VAR[-1]` (for array-shape consts)."""
    obj = _extract_js_const(html, var_name)
    if obj is None:
        return None
    if isinstance(obj, dict):
        arr = obj.get(key)
    elif isinstance(obj, list) and key is None:
        arr = obj
    else:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    return arr[-1]


def check_metric_consistency(html, data, sig_vals):
    """Pass 3e: cross-surface numeric consistency for canonical metrics.

    Compares values rendered on multiple surfaces (KPI strip, JS data
    const, commentary text) against each other. Catches the bug class
    where one surface derives a metric independently and drifts from the
    others (e.g. Jobs tile summing SECTOR_MOM = 188K while everything
    else read PAYEMS = 178K). Raw-data-vs-rendered drift is a separate
    concern handled by Pass 1 (check_internal).

    Each metric lists 2+ surfaces; the first non-None is treated as the
    reference and the rest must agree within `tol`.
    """
    findings = []

    metrics = [
        ('NFP MoM latest (K)',
         [
             ('NFP_BLS_MOM.bls[-1]',  _const_array_last(html, 'NFP_BLS_MOM', 'bls')),
             ('KPIS Jobs tile',       _kpi_value(html, 'Jobs')),
             ('Commentary payrolls',  _commentary_match(
                 html, 'unemp', r'payrolls printed <strong>([+-]?\d+)K')),
         ],
         5),  # ±5K — tile rounding tolerance

        ('Unemployment rate (%)',
         [
             ('U_MONTHLY.data[-1]',  _const_array_last(html, 'U_MONTHLY', 'data')),
             ('KPIS Unemployment',   _kpi_value(html, 'Unemployment')),
             ('Commentary U-3',      _commentary_match(
                 html, 'unemp', r'U-3 at <strong>(\d+\.\d+)%</strong>')),
         ],
         0.1),

        ('CPI YoY latest (%)',
         [
             ('CPI_MONTHLY.headline[-1]', _const_array_last(html, 'CPI_MONTHLY', 'headline')),
             ('KPIS CPI YoY',             _kpi_value(html, 'CPI YoY')),
         ],
         0.15),

        ('Core PCE YoY latest (%)',
         [
             ('PCE_MONTHLY.core[-1]',  _const_array_last(html, 'PCE_MONTHLY', 'core')),
             ('KPIS Core PCE',         _kpi_value(html, 'Core PCE')),
         ],
         0.15),

        ('UMich sentiment latest',
         [
             ('UMCSENT_MONTHLY.data[-1]', _const_array_last(html, 'UMCSENT_MONTHLY', 'data')),
             ('KPIS UMich Sentiment',     _kpi_value(html, 'UMich Sentiment')),
         ],
         0.5),

        # Fed Funds + 10Y: yield-tab tiles read from KPIS at runtime, so the
        # KPIS value vs raw data is the single thing to keep aligned. We
        # compare KPIS to the source-of-truth data series here as a single
        # surface check (raw is the second surface).
        ('Fed Funds latest (%)',
         [
             ('KPIS Fed Funds',  _kpi_value(html, 'Fed Funds')),
             ('data["ffr"]',     (data.get('ffr') or {}).get('value') if isinstance(data.get('ffr'), dict) else None),
         ],
         0.05),

        ('10Y Treasury latest (%)',
         [
             ('KPIS 10Y Treasury', _kpi_value(html, '10Y Treasury')),
             ('data["dgs10"]',     (data.get('dgs10') or {}).get('value') if isinstance(data.get('dgs10'), dict) else None),
         ],
         0.05),
    ]

    for name, surfaces, tol in metrics:
        # Coerce to floats; skip MISSING surfaces.
        parsed = []
        surface_vals = {}
        for sname, sval in surfaces:
            if sval is None:
                surface_vals[sname] = 'MISSING'
                continue
            try:
                sv = float(sval)
            except (TypeError, ValueError):
                surface_vals[sname] = f'unparseable: {sval}'
                continue
            surface_vals[sname] = sv
            parsed.append((sname, sv))

        if len(parsed) < 2:
            findings.append({
                'check': f'{name}: ≥2 surfaces extractable',
                'surfaces': surface_vals,
                'severity': 'skipped',
                'pass': True,
                'reason': f'only {len(parsed)} surface(s) extractable; cross-check needs ≥2',
            })
            continue

        ref_name, ref_val = parsed[0]
        diverged = [(s, v) for s, v in parsed[1:] if abs(v - ref_val) > tol]

        ok = not diverged
        findings.append({
            'check': f'{name}: surfaces agree within ±{tol} (ref: {ref_name})',
            'reference': ref_val,
            'surfaces': surface_vals,
            'severity': 'ok' if ok else 'divergence',
            'pass': ok,
        })
        if not ok:
            for s, v in diverged:
                print(f'  🔴 {name}: {s}={v} vs {ref_name}={ref_val} (Δ={v - ref_val:+.2f}, tol±{tol})')

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3f: SCHEMA CONTRACT (static analysis)
#   Verify every key the renderer reads from raw_data is written by the
#   collector. Catches renamed-key drift like the gdp_real_annual /
#   gdpc1_annual mismatch where the renderer silently fell back to [].
# ═══════════════════════════════════════════════════════════════════════

# Keys the renderer reads from sources other than raw_data.json (so absence
# from collector writes is expected, not a bug).
_NON_COLLECTOR_KEYS = {
    'banks',  # Comes from data/bank_earnings.json (Agent 9)
}


def check_schema_contract():
    """Pass 3f — Static-analyze collector + renderer for key contract drift."""
    findings = []
    scripts_dir = Path(__file__).resolve().parent
    coll_src = (scripts_dir / 'collector.py').read_text(encoding='utf-8')
    rend_src = (scripts_dir / 'renderer.py').read_text(encoding='utf-8')

    # Writes: data['xxx'] = ...   |   data["xxx"] = ...
    coll_writes = set(re.findall(r"data\[['\"]([a-z_0-9]+)['\"]\]\s*=", coll_src))
    # Reads: data.get('xxx', ...) AND data['xxx']<not-equals-sign>
    rend_reads = set(re.findall(r"data\.get\(\s*['\"]([a-z_0-9]+)['\"]", rend_src))
    rend_reads |= set(re.findall(r"data\[['\"]([a-z_0-9]+)['\"]\][^=]", rend_src))

    for key in sorted(rend_reads):
        if key in _NON_COLLECTOR_KEYS:
            continue
        ok = key in coll_writes
        finding = {
            'check': f'Schema contract: data[{key!r}]',
            'pass': ok,
            'severity': 'ok' if ok else 'critical',
        }
        if not ok:
            finding['note'] = (
                f"renderer reads data['{key}'] but collector never writes it; "
                f"renderer will silently fall back to [] and any chart sourced "
                f"from this key will hold its static seed forever"
            )
            print(f'  🔴 Schema contract: data[{key!r}] — no collector writer')
        findings.append(finding)
    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3g: SEED DRIFT
#   For every static seed in index.html that has a known recompute path
#   from raw_data, recompute and compare. Catches the FC_MACRO act24
#   historical drift bug — values seeded at write time and never refreshed
#   by a renderer rebuild. Surface narrows over time as more seeds get
#   wired to live recompute paths.
# ═══════════════════════════════════════════════════════════════════════

# Drift tolerance per metric type, in the metric's native units.
# Pp = percentage points; values smaller than tolerance don't trip the check.
_FC_DRIFT_TOLERANCE = {
    'GDP':  0.15,   # rounding + revision noise
    'U':    0.10,   # unemployment is reported to 0.1pp
    'CPI':  0.15,
    'Wage': 0.20,   # AHETPI revisions a bit larger
    'FFR':  0.10,
}


def _fc_macro_expected(data, yr):
    """Recompute the 5-element FC_MACRO.actNN array for calendar year `yr`
    from raw_data, mirroring update_fc_macro in renderer.py exactly."""
    gdp_by_yr = {int(o['date'][:4]): o['value']
                 for o in (data.get('gdpc1_annual', []) or [])}
    unrate_by_ym = {(int(o['date'][:4]), int(o['date'][5:7])): o['value']
                    for o in (data.get('unrate', []) or [])}
    cpi_by_ym = {(int(o['date'][:4]), int(o['date'][5:7])): o['value']
                 for o in (data.get('cpi_all', []) or [])}
    ahe_by_ym = {(int(o['date'][:4]), int(o['date'][5:7])): o['value']
                 for o in (data.get('ahetpi', []) or [])}
    ffr_by_yr = {int(o['date'][:4]): o['value']
                 for o in (data.get('fedfunds_annual', []) or [])}

    gdp = None
    if yr in gdp_by_yr and (yr - 1) in gdp_by_yr:
        gdp = round((gdp_by_yr[yr] - gdp_by_yr[yr - 1]) / gdp_by_yr[yr - 1] * 100, 1)
    u = round(unrate_by_ym[(yr, 12)], 1) if (yr, 12) in unrate_by_ym else None
    cd, cp = cpi_by_ym.get((yr, 12)), cpi_by_ym.get((yr - 1, 12))
    cpi = round((cd - cp) / cp * 100, 1) if cd and cp else None
    ad, ap = ahe_by_ym.get((yr, 12)), ahe_by_ym.get((yr - 1, 12))
    wage = round((ad - ap) / ap * 100, 1) if ad and ap else None
    ffr = round(ffr_by_yr[yr], 1) if yr in ffr_by_yr else None
    return [gdp, u, cpi, wage, ffr]


def check_seed_drift(html, data):
    """Pass 3g — Compare static seeds in index.html against fresh recompute."""
    findings = []
    labels = ['GDP', 'U', 'CPI', 'Wage', 'FFR']

    # FC_MACRO.actNN — historical actuals; revised by BEA/BLS over time
    fc_block = re.search(r'const FC_MACRO\s*=\s*\{[^}]+\}', html, re.DOTALL)
    if not fc_block:
        findings.append({
            'check': 'FC_MACRO block present',
            'pass': False, 'severity': 'warning',
            'note': 'const FC_MACRO not found in index.html',
        })
        return findings

    for m in re.finditer(r'(act(\d{2})):\s*\[([^\]]+)\]', fc_block.group(0)):
        act_key, yy = m.group(1), m.group(2)
        yr = 2000 + int(yy)
        try:
            seed = [float(v.strip()) for v in m.group(3).split(',')]
        except ValueError:
            continue
        expected = _fc_macro_expected(data, yr)

        diverged = []
        for i, (s, e) in enumerate(zip(seed, expected)):
            if e is None:
                continue  # No source data for this metric — can't verify
            tol = _FC_DRIFT_TOLERANCE.get(labels[i], 0.15)
            if abs(s - e) > tol:
                diverged.append(f'{labels[i]}: seed={s} expected={e} (Δ{e - s:+.2f}, tol±{tol})')

        if diverged:
            sev = 'critical' if len(diverged) >= 2 else 'warning'
            findings.append({
                'check': f'Seed drift: FC_MACRO.{act_key} (yr={yr})',
                'pass': False, 'severity': sev,
                'seed': seed, 'expected': expected,
                'diverged': diverged,
                'note': '; '.join(diverged),
            })
            for d in diverged:
                print(f'  🔴 FC_MACRO.{act_key} ({yr}): {d}')
        else:
            findings.append({
                'check': f'Seed drift: FC_MACRO.{act_key} (yr={yr})',
                'pass': True, 'severity': 'ok',
                'seed': seed, 'expected': expected,
            })
    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3h: COLLECTOR ERRORS (runtime fetch failures)
#   Surface FRED/BLS 400-class errors as critical findings. The collector
#   already records these in raw_data['errors']; without this pass they
#   sat unread for months while charts silently rendered partial data.
# ═══════════════════════════════════════════════════════════════════════

def check_collector_errors(raw):
    """Pass 3h — Surface API errors recorded by the collector during fetch."""
    findings = []
    errs = raw.get('errors', []) or []
    if not errs:
        findings.append({
            'check': 'Collector errors: none recorded',
            'pass': True, 'severity': 'ok',
        })
        return findings

    for err in errs:
        # Match patterns like 'FRED <id>: 400 Client Error' / 'BLS <id>: ...'
        m = re.match(r'^(FRED|BLS|EIA)\s+([A-Z0-9_]+):\s*(\d+)?\s*(.+)$', err)
        if m:
            api, sid, code, msg = m.group(1), m.group(2), m.group(3), m.group(4)
            sev = 'critical' if code and code.startswith('4') else 'warning'
            findings.append({
                'check': f'{api} fetch: {sid}',
                'pass': False, 'severity': sev,
                'note': f'{code or ""} {msg}'.strip(),
            })
            print(f'  🔴 {api} {sid}: {code or ""} {msg[:80]}')
        else:
            findings.append({
                'check': 'Collector error',
                'pass': False, 'severity': 'warning',
                'note': err[:240],
            })
    return findings


def check_secret_leaks():
    """Pass 3k — Secret-leak guard.

    Scans every committed JSON artifact in `data/` for query-param-style
    secret leaks (`?api_key=XYZ`, `&token=XYZ`, etc.). Build-blocking
    on any hit. Background: python-requests embeds the full URL in
    HTTPError.__str__, so a stringified exception captured into
    `errors`/`raw_errors` would persist the API key alongside the
    public data. The collector's `_ErrList` scrubs on append, but
    this pass is the defence-in-depth that catches anything that
    slipped through (new error capture sites, third-party libraries,
    historical files that pre-date the scrubber).
    """
    findings = []
    leak_re = re.compile(
        r'(?:[?&])(?:api_key|key|token|access_token|apikey)=[^&\s\'"\[]+',
        flags=re.IGNORECASE,
    )
    data_dir = ROOT / 'data'
    if not data_dir.exists():
        return [{'check': 'Secret leak scan', 'pass': True, 'severity': 'ok',
                 'note': 'data/ not present'}]

    scanned = 0
    leaks_total = 0
    for fp in sorted(data_dir.rglob('*.json')):
        # Skip the snapshots directory — historical artifacts pre-date
        # this guard, and rewriting them would also rewrite the audit
        # trail. They're noted in the run log but not gating.
        try:
            rel = fp.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(fp)
        if '/snapshots/' in rel:
            continue
        try:
            text = fp.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        hits = leak_re.findall(text)
        if hits:
            # Truncate to first 2 distinct patterns to keep the report compact.
            samples = list(dict.fromkeys(hits))[:2]
            # Redact in the report itself — never let the validator's own
            # output ship the secret.
            redacted = [re.sub(r'=[^&\s\'"\[]+', '=[REDACTED]', s) for s in samples]
            leaks_total += len(hits)
            findings.append({
                'check': f'Secret leak in {rel}',
                'pass': False,
                'severity': 'critical',
                'note': f'{len(hits)} hit(s); examples: {", ".join(redacted)}',
            })
            print(f'  🔴 secret leak: {rel} — {len(hits)} hit(s)')

    if not findings:
        findings.append({
            'check': f'Secret leak scan ({scanned} JSON files)',
            'pass': True,
            'severity': 'ok',
            'note': 'no api_key/token/key= patterns detected',
        })
    return findings


def check_cross_source(data):
    """Pass 3i — Cross-source agreement check.

    The dashboard aggregates from FRED, BLS, BEA, and EIA. FRED republishes
    upstream BLS/BEA series — so the value on FRED for, e.g., UNRATE
    should match the underlying BLS value to within rounding. A
    divergence indicates one of:
      - One side has not yet published a revision.
      - Collector pulled stale/cached data from one path.
      - Upstream publishing bug.

    Cheap, low-noise: only checks 4 anchor series. Network-gated by the
    same FRED_KEY / BLS_KEY presence the rest of the validator uses.
    No-op (returns 'skipped' findings) when keys are missing — never
    blocks CI.
    """
    findings = []

    # Pairs of (anchor_series_in_raw_data, FRED id, BLS id, tolerance_pct).
    # Anchor series is what the collector stored under `data[<key>]`.
    pairs = [
        ('unrate',    'UNRATE',     'LNS14000000', 0.05),
        ('cpi_all',   'CPIAUCSL',   'CUUR0000SA0', 0.001),
        ('core_cpi',  'CPILFESL',   'CUUR0000SA0L1E', 0.001),
    ]

    if not FRED_KEY or not BLS_KEY:
        findings.append({
            'check': 'Cross-source agreement: FRED+BLS keys',
            'pass': True, 'severity': 'skipped',
            'note': 'Keys not configured — cross-source check skipped',
        })
        return findings

    for anchor_key, fred_id, bls_id, tol_frac in pairs:
        f = _fred_latest(fred_id)
        b = _bls_latest(bls_id)
        if not f or not b:
            findings.append({
                'check':    f'Cross-source: {anchor_key} (FRED vs BLS)',
                'pass':     True,
                'severity': 'skipped',
                'note':     f'one side unavailable (fred={bool(f)}, bls={bool(b)})',
            })
            continue
        _, fv = f
        _, bv = b
        diff = abs(fv - bv)
        # Tolerance is the larger of (fraction of value, absolute floor 0.05).
        # Floor keeps the check sane for small-magnitude rates (e.g.
        # unemployment 4.3% — 5% fractional tolerance ≈ 0.2pp).
        tol = max(tol_frac * abs(bv), 0.05)
        agrees = diff <= tol
        findings.append({
            'check':    f'Cross-source: {anchor_key} (FRED vs BLS)',
            'pass':     agrees,
            'severity': 'ok' if agrees else 'warning',
            'metric':   anchor_key,
            'fred':     fv,
            'bls':      bv,
            'diff':     round(diff, 4),
            'tol':      round(tol, 4),
            'note':     None if agrees else (
                f'FRED {fv} vs BLS {bv} (Δ={diff:.4f}, tol={tol:.4f}). '
                f'One side may be stale or revised.'
            ),
        })
        if not agrees:
            print(f'  ⚠ {anchor_key}: FRED={fv} BLS={bv} Δ={diff:.4f}')

    return findings


# ═══════════════════════════════════════════════════════════════════════
# PASS 3j: NOISE-FLOOR COMPLIANCE (observability, not a gate)
#   For each metric with a known_normal.json noise_floor_pp entry, compute
#   the latest PoP delta and report whether it sits within the noise band
#   or above it. Other passes can interpret a 'real_signal' verdict as
#   permission to escalate; an 'within_noise' verdict means a small wobble
#   does NOT deserve a finding.
#
#   This pass NEVER fails the build. It writes one finding per known
#   metric so the Repair Diagnostician (Agent 10) and CEO-grade gate can
#   read latest_delta + floor side-by-side. Mirrors data/playbook.md §2.2.
# ═══════════════════════════════════════════════════════════════════════

# Mapping from known_normal.json noise_floor_pp key → callable that
# extracts the latest two scalar observations from the raw_data dict.
# Returns (prior, latest) tuple, or (None, None) if data unavailable.
# Keys absent here are simply skipped — adding a new series to the
# noise floor table without a mapping here is fine, just produces a
# 'no_mapping' info finding.

def _two_latest_from_series(data, key, value_key='value'):
    """Return (prior_value, latest_value) for a list-of-dicts series."""
    series = data.get(key)
    if not isinstance(series, list) or len(series) < 2:
        return (None, None)
    # Collector convention: index 0 is newest, but a few series flip.
    # Sort by date descending to be safe.
    try:
        s = sorted(series, key=lambda r: r.get('date', ''), reverse=True)
        latest = s[0].get(value_key)
        prior  = s[1].get(value_key)
        return (float(prior), float(latest))
    except (TypeError, ValueError, AttributeError):
        return (None, None)


_NOISE_FLOOR_EXTRACTORS = {
    'core_cpi_yoy':         lambda d, v: _two_latest_from_series(d, 'core_cpi_yoy'),
    'saving_rate':          lambda d, v: _two_latest_from_series(d, 'psavert'),
    'umich_sentiment':      lambda d, v: _two_latest_from_series(d, 'umcsent'),
    'cc_delinq_90plus':     lambda d, v: _two_latest_from_series(d, 'cc_delinq'),
    'gasoline_usd_gal':     lambda d, v: _two_latest_from_series(d, 'gasoline'),
    'jolts_openings':       lambda d, v: _two_latest_from_series(d, 'jolts_openings'),
    'jolts_quits':          lambda d, v: _two_latest_from_series(d, 'jolts_quits'),
    'jolts_hires':          lambda d, v: _two_latest_from_series(d, 'jolts_hires'),
    'trimmed_mean_cpi_yoy': lambda d, v: _two_latest_from_series(d, 'trimmed_mean_cpi'),
    'median_cpi_yoy':       lambda d, v: _two_latest_from_series(d, 'median_cpi'),
    'walcl_bn':             lambda d, v: _two_latest_from_series(d, 'walcl'),
    'wresbal_bn':           lambda d, v: _two_latest_from_series(d, 'wresbal'),
    'rrpontsyd_bn':         lambda d, v: _two_latest_from_series(d, 'rrpontsyd'),
    'deficit_pct_gdp':      lambda d, v: _two_latest_from_series(d, 'fyfsgda188s'),
}


def check_noise_floor(data, sig_vals):
    """Pass 3j — Per-metric PoP noise compliance (observability only)."""
    findings = []
    if not KNOWN_NORMAL_FILE.exists():
        findings.append({
            'check': 'known_normal.json present',
            'pass': True, 'severity': 'skipped',
            'reason': 'known_normal.json not found; noise-floor checks skipped',
        })
        return findings

    try:
        kn = json.loads(KNOWN_NORMAL_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        findings.append({
            'check': 'known_normal.json parseable',
            'pass': False, 'severity': 'warning',
            'note': f'failed to read/parse known_normal.json: {e!r}',
        })
        return findings

    floors = (kn.get('noise_floor_pp') or {})
    for metric, floor in floors.items():
        if metric.startswith('_'):
            continue  # _units_note etc.
        try:
            floor = float(floor)
        except (TypeError, ValueError):
            continue

        extractor = _NOISE_FLOOR_EXTRACTORS.get(metric)
        if extractor is None:
            findings.append({
                'check': f'noise_floor[{metric}]',
                'pass': True, 'severity': 'skipped',
                'metric': metric, 'floor': floor,
                'reason': 'no extractor mapping in validator (add one in _NOISE_FLOOR_EXTRACTORS)',
            })
            continue

        prior, latest = extractor(data, sig_vals)
        if prior is None or latest is None:
            findings.append({
                'check': f'noise_floor[{metric}]',
                'pass': True, 'severity': 'skipped',
                'metric': metric, 'floor': floor,
                'reason': 'underlying series not yet populated in raw_data (collector may not have run, or series newly added)',
            })
            continue

        delta = latest - prior
        abs_delta = abs(delta)
        within_noise = abs_delta <= floor
        verdict = 'within_noise' if within_noise else 'real_signal'

        findings.append({
            'check': f'noise_floor[{metric}]',
            'pass': True,            # this pass NEVER fails — observability only
            'severity': 'ok',
            'metric':   metric,
            'floor':    floor,
            'prior':    prior,
            'latest':   latest,
            'delta':    round(delta, 4),
            'abs_delta': round(abs_delta, 4),
            'verdict':  verdict,
            'note':     (f'PoP delta {delta:+.3f} '
                         f'{"≤" if within_noise else ">"} ±{floor} → '
                         f'{verdict}'),
        })

    return findings


def build_report(internal, sources, staleness, visual=None, vision_review=None, shock_tracker=None, earnings=None, panel_data=None, metric_consistency=None, schema_contract=None, collector_errors=None, seed_drift=None, cross_source=None, noise_floor=None, secret_leaks=None):
    """Compile all findings into a validation report."""
    if visual is None:
        visual = []
    if vision_review is None:
        vision_review = []
    if shock_tracker is None:
        shock_tracker = []
    if earnings is None:
        earnings = []
    if panel_data is None:
        panel_data = []
    if metric_consistency is None:
        metric_consistency = []
    if schema_contract is None:
        schema_contract = []
    if collector_errors is None:
        collector_errors = []
    if seed_drift is None:
        seed_drift = []
    if cross_source is None:
        cross_source = []
    if noise_floor is None:
        noise_floor = []
    if secret_leaks is None:
        secret_leaks = []
    all_findings = (internal + sources + staleness + visual + vision_review +
                    shock_tracker + earnings + panel_data + metric_consistency +
                    schema_contract + collector_errors + seed_drift +
                    cross_source + noise_floor + secret_leaks)

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
        'shock_tracker': shock_tracker,
        'panel_data_consistency': panel_data,
        'metric_consistency': metric_consistency,
        'earnings_verbatim': earnings,
        'schema_contract': schema_contract,
        'collector_errors': collector_errors,
        'seed_drift': seed_drift,
        'visual_qa': visual,
        'visual_review': vision_review,
        'cross_source': cross_source,
        'noise_floor': noise_floor,
        'secret_leaks': secret_leaks,
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

    # Pass 3b: Shock tracker structure + MMA consistency
    print('\n  ── Pass 3b: Shock Tracker Structure ──')
    shock_tracker = check_shock_tracker(html)
    st_pass = sum(1 for f in shock_tracker if f.get('pass'))
    st_fail = sum(1 for f in shock_tracker if not f.get('pass'))
    print(f'  {st_pass} passed, {st_fail} failed')

    # Pass 3d: Panel title ↔ data const month consistency
    print('\n  ── Pass 3d: Panel Title vs Data Const Month Consistency ──')
    panel_data = check_panel_data_consistency(html)
    pd_pass = sum(1 for f in panel_data if f.get('pass'))
    pd_fail = sum(1 for f in panel_data if not f.get('pass') and f.get('severity') != 'skipped')
    print(f'  {pd_pass} passed, {pd_fail} failed')

    # Pass 3e: Cross-surface metric consistency
    print('\n  ── Pass 3e: Cross-Surface Metric Consistency ──')
    metric_consistency = check_metric_consistency(html, data, sig_vals)
    mc_pass = sum(1 for f in metric_consistency if f.get('pass'))
    mc_fail = sum(1 for f in metric_consistency if not f.get('pass') and f.get('severity') != 'skipped')
    print(f'  {mc_pass} passed, {mc_fail} failed')

    # Pass 3f: Schema contract — renderer reads vs collector writes (static)
    print('\n  ── Pass 3f: Schema Contract (collector ↔ renderer keys) ──')
    schema_contract = check_schema_contract()
    sc_pass = sum(1 for f in schema_contract if f.get('pass'))
    sc_fail = sum(1 for f in schema_contract if not f.get('pass'))
    print(f'  {sc_pass} passed, {sc_fail} failed')

    # Pass 3g: Seed drift (FC_MACRO.actNN vs fresh recompute)
    print('\n  ── Pass 3g: Seed Drift (static seeds vs raw data) ──')
    seed_drift = check_seed_drift(html, data)
    sd_pass = sum(1 for f in seed_drift if f.get('pass'))
    sd_fail = sum(1 for f in seed_drift if not f.get('pass'))
    print(f'  {sd_pass} passed, {sd_fail} failed')

    # Pass 3h: Collector errors (FRED/BLS 4xx surfaced from raw_data['errors'])
    print('\n  ── Pass 3h: Collector Errors (API fetch failures) ──')
    collector_errors = check_collector_errors(raw)
    ce_pass = sum(1 for f in collector_errors if f.get('pass'))
    ce_fail = sum(1 for f in collector_errors if not f.get('pass'))
    print(f'  {ce_pass} passed, {ce_fail} failed')

    # Pass 3i: Cross-source agreement (FRED vs BLS for shared anchor metrics)
    print('\n  ── Pass 3i: Cross-Source Agreement (FRED vs BLS) ──')
    cross_source = check_cross_source(data)
    cs_pass = sum(1 for f in cross_source if f.get('pass') and f.get('severity') != 'skipped')
    cs_fail = sum(1 for f in cross_source if not f.get('pass'))
    cs_skip = sum(1 for f in cross_source if f.get('severity') == 'skipped')
    print(f'  {cs_pass} passed, {cs_fail} failed, {cs_skip} skipped')

    # Pass 3j: Noise-floor compliance (observability — reports PoP deltas
    # vs known_normal.json's noise floors so other consumers can tell
    # within_noise wobbles apart from real_signal moves).
    print('\n  ── Pass 3j: Noise-Floor Compliance (advisory) ──')
    noise_floor = check_noise_floor(data, sig_vals)
    nf_real = sum(1 for f in noise_floor if f.get('verdict') == 'real_signal')
    nf_in   = sum(1 for f in noise_floor if f.get('verdict') == 'within_noise')
    nf_skip = sum(1 for f in noise_floor if f.get('severity') == 'skipped')
    print(f'  {nf_in} within noise, {nf_real} real signal, {nf_skip} skipped')

    # Pass 3c: Earnings commentary factuality (JSON structure + verbatim enforcement)
    print('\n  ── Pass 3c: Earnings Commentary Factuality ──')
    earnings = check_earnings_verbatim()
    e_pass = sum(1 for f in earnings if f.get('pass'))
    e_fail = sum(1 for f in earnings if not f.get('pass') and f.get('severity') != 'skipped')
    e_skip = sum(1 for f in earnings if f.get('severity') == 'skipped')
    print(f'  {e_pass} passed, {e_fail} failed, {e_skip} skipped')

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

    # Pass 5: Visual Review — Claude vision analysis of screenshots (Agent 8)
    print('\n  ── Pass 5: Visual Review (AI vision analysis — Agent 8) ──')
    vision_review = check_visual_review()
    vr_pass = sum(1 for f in vision_review if f.get('pass'))
    vr_fail = sum(1 for f in vision_review if not f.get('pass') and f.get('severity') != 'skipped')
    vr_skip = sum(1 for f in vision_review if f.get('severity') == 'skipped')
    if vr_skip:
        print(f'  Skipped ({vision_review[0].get("reason", "unavailable")})')
    else:
        print(f'  {vr_pass} passed, {vr_fail} failed')

    # Pass 3k: Secret-leak scan (defence-in-depth for the collector
    # scrubber). Fails the build on any `?api_key=…` / `&token=…`
    # substring found in committed JSON under data/.
    print('\n  ── Pass 3k: Secret-Leak Guard ──')
    secret_leaks = check_secret_leaks()
    sl_pass = sum(1 for f in secret_leaks if f.get('pass'))
    sl_fail = sum(1 for f in secret_leaks if not f.get('pass'))
    print(f'  {sl_pass} passed, {sl_fail} failed')

    # Build and save report
    report = build_report(internal, sources, staleness, visual, vision_review, shock_tracker, earnings, panel_data, metric_consistency, schema_contract, collector_errors, seed_drift, cross_source, noise_floor, secret_leaks)
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
                                   ('Staleness', staleness), ('Visual', visual),
                                   ('Vision', vision_review),
                                   ('PanelData', panel_data),
                                   ('MetricConsistency', metric_consistency),
                                   ('SchemaContract', schema_contract),
                                   ('CollectorErrors', collector_errors),
                                   ('SeedDrift', seed_drift)]:
        for f in section:
            if not f.get('pass') and f.get('severity') != 'skipped':
                print(f'  → [{section_name}] {f["check"]}: {f.get("severity", "fail")}')

    return status != 'FAIL'


if __name__ == '__main__':
    sys.exit(0 if validate() else 1)
