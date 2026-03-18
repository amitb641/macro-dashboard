#!/usr/bin/env python3
"""
Agent 1 — COLLECTOR
Pulls all macro series from FRED, BLS, EIA APIs.
Runs daily Mon–Fri at 7am ET via GitHub Actions.
No LLM. Output: data/raw_data.json

Daily series (refresh every run):
  FRED: yields, spreads, oil, mortgage
  EIA:  WTI + Brent daily spot

Weekly series (refresh Thursdays only):
  FRED: initial jobless claims (ICSA), continued claims (CCSA)

Monthly series (latest available):
  FRED: unemployment, CPI, PCE, wages, saving rate, housing, GDP
  BLS:  sector payrolls
"""

import os, json, datetime, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

FRED_KEY = os.environ.get('FRED_API_KEY', '')
BLS_KEY  = os.environ.get('BLS_API_KEY',  '')
EIA_KEY  = os.environ.get('EIA_API_KEY',  '')

ROOT     = Path(__file__).parent.parent
OUT_FILE = ROOT / 'data' / 'raw_data.json'

errors = []


# ── FRED ──────────────────────────────────────────────────────────────

def fred_obs(series_id, limit=14, freq=None):
    """Return list of {date,value} newest first, no missing values.
    Retries up to 3 times with exponential backoff on 5xx errors."""
    if not FRED_KEY:
        errors.append(f'FRED key missing — skipped {series_id}'); return []
    params = {'series_id': series_id, 'api_key': FRED_KEY,
              'file_type': 'json', 'sort_order': 'desc', 'limit': limit}
    if freq: params['frequency'] = freq
    last_err = None
    for attempt in range(4):  # 0, 1, 2, 3
        try:
            r = requests.get('https://api.stlouisfed.org/fred/series/observations',
                             params=params, timeout=15)
            r.raise_for_status()
            return [{'date': o['date'], 'value': float(o['value'])}
                    for o in r.json().get('observations', []) if o['value'] != '.']
        except requests.exceptions.HTTPError as e:
            last_err = e
            if r.status_code >= 500 and attempt < 3:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f'    ↻ FRED {series_id}: {r.status_code}, retry {attempt+1}/3 in {wait}s')
                time.sleep(wait)
                continue
            break
        except Exception as e:
            last_err = e; break
    errors.append(f'FRED {series_id}: {last_err}'); return []

def fv(sid, limit=14):
    d = fred_obs(sid, limit); return d[0] if d else None


# ── BLS ───────────────────────────────────────────────────────────────

def bls_fetch(series_ids):
    if not BLS_KEY: errors.append('BLS key missing'); return {}
    yr = datetime.date.today().year
    try:
        r = requests.post('https://api.bls.gov/publicAPI/v2/timeseries/data/', json={
            'seriesid': series_ids, 'startyear': str(yr - 2), 'endyear': str(yr),
            'registrationkey': BLS_KEY, 'annualaverage': True}, timeout=20)
        r.raise_for_status()
        body = r.json()
        if body.get('status') != 'REQUEST_SUCCEEDED':
            errors.append(f'BLS: {body.get("message","")}'); return {}
        return {s['seriesID']: s['data'] for s in body['Results']['series']}
    except Exception as e:
        errors.append(f'BLS: {e}'); return {}


# ── EIA ───────────────────────────────────────────────────────────────

def eia_spot(product, days=35):
    """EIA daily spot. product: RWTC=WTI, RBRTE=Brent. 35 days = current month + buffer."""
    if not EIA_KEY: return []
    url = (f'https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_KEY}'
           f'&frequency=daily&data[0]=value&facets[series][]={product}'
           f'&sort[0][column]=period&sort[0][direction]=desc&length={days}')
    try:
        r = requests.get(url, timeout=15); r.raise_for_status()
        return [{'date': d['period'], 'value': float(d['value'])}
                for d in r.json()['response']['data'] if d['value']]
    except Exception as e:
        errors.append(f'EIA {product}: {e}'); return []


# ── Build OIL_DAILY for current month ────────────────────────────────

def build_oil_daily(wti_series, brent_series):
    """
    Extract current-month daily sessions from EIA/FRED data.
    Returns dict with labels, wti, brent arrays for the chart.
    Keeps it clean: only current calendar month, max ~23 sessions.
    """
    today = datetime.date.today()
    month_start = today.replace(day=1)
    month_name = today.strftime('%B %Y')

    def filter_month(series):
        out = []
        for obs in reversed(series):  # oldest first
            d = datetime.date.fromisoformat(obs['date'])
            if d.year == today.year and d.month == today.month:
                out.append({'date': d, 'value': obs['value']})
        return out

    wti_m   = filter_month(wti_series)
    brent_m = filter_month(brent_series)

    # Align by date
    wti_by_date   = {o['date']: o['value'] for o in wti_m}
    brent_by_date = {o['date']: o['value'] for o in brent_m}
    all_dates = sorted(set(list(wti_by_date.keys()) + list(brent_by_date.keys())))

    labels = []
    wti_vals = []
    brent_vals = []

    for d in all_dates:
        # Short label: "Mar 3" — concise, no year needed (all same month)
        labels.append(d.strftime('%b %-d'))
        wti_vals.append(wti_by_date.get(d))
        brent_vals.append(brent_by_date.get(d))

    # Auto-generate move annotations: flag any day with |change| >= $2.50/bbl
    notes = []
    for i, wti in enumerate(wti_vals):
        if wti is None or i == 0:
            notes.append(None)
            continue
        prev = next((wti_vals[j] for j in range(i-1, -1, -1) if wti_vals[j] is not None), None)
        if prev is None:
            notes.append(None)
            continue
        chg = wti - prev
        if abs(chg) >= 2.50:
            direction = 'surge' if chg > 0 else 'drop'
            pct = abs(chg / prev * 100)
            notes.append(f'WTI {direction} ${abs(chg):.1f} ({pct:.1f}%) — pipeline updates this field with market headlines')
        else:
            notes.append(None)

    return {
        'labels':   labels,
        'wti':      wti_vals,
        'brent':    brent_vals,
        'notes':    notes,
        'month':    month_name,
        'updated':  datetime.datetime.utcnow().strftime('%b %d %H:%M UTC'),
        'sessions': len([v for v in wti_vals if v is not None]),
    }


# ══════════════════════════════════════════════════════════════════════

def collect():
    print('[Agent 1 — Collector] Starting...')
    ts   = datetime.datetime.utcnow().isoformat() + 'Z'
    data = {}

    # ── Daily: rates, spreads, oil ────────────────────────────────────
    print('  [Daily] Rates + Yields...')
    data['ffr']         = fv('FEDFUNDS')
    data['dff']         = fv('DFF')
    data['dgs2']        = fv('DGS2')
    data['dgs5']        = fv('DGS5')
    data['dgs10']       = fv('DGS10')
    data['dgs30']       = fv('DGS30')
    data['dgs10_hist']  = fred_obs('DGS10', 60)
    data['dgs2_hist']   = fred_obs('DGS2',  60)

    print('  [Daily] Credit Spreads...')
    data['ig_oas']      = fv('BAMLC0A0CM')
    data['hy_oas']      = fv('BAMLH0A0HYM2')
    data['ig_hist']     = fred_obs('BAMLC0A0CM',   60)
    data['hy_hist']     = fred_obs('BAMLH0A0HYM2', 60)

    print('  [Daily] Oil (EIA + FRED fallback)...')
    wti_raw   = eia_spot('RWTC',  35)    # current month + buffer
    brent_raw = eia_spot('RBRTE', 35)
    if not wti_raw:   wti_raw   = fred_obs('DCOILWTICO',   35)
    if not brent_raw: brent_raw = fred_obs('DCOILBRENTEU', 35)
    data['wti_daily']    = wti_raw
    data['brent_daily']  = brent_raw
    data['oil_daily_chart'] = build_oil_daily(wti_raw, brent_raw)  # current month only

    print('  [Daily] Mortgage (weekly)...')
    data['mortgage30']  = fred_obs('MORTGAGE30US', 6)
    data['mortgage15']  = fred_obs('MORTGAGE15US', 6)

    # ── Monthly: labor, inflation, housing, GDP ───────────────────────
    # Pull 320 observations (~26 years) to build charts from 2000
    # ── Weekly: jobless claims (DOL releases Thursdays) ───────────────
    # Try carry-forward on non-Thursdays; always fetch fresh if no prior data
    prior_icsa, prior_ccsa = [], []
    if datetime.date.today().weekday() != 3:  # Not Thursday — try carry forward
        try:
            prior = json.loads(OUT_FILE.read_text()).get('data', {}) if OUT_FILE.exists() else {}
        except (json.JSONDecodeError, OSError):
            prior = {}
        prior_icsa = prior.get('icsa', [])
        prior_ccsa = prior.get('ccsa', [])

    if datetime.date.today().weekday() == 3 or not prior_icsa:
        # Thursday refresh OR no prior data — fetch fresh from FRED
        reason = 'Thursday refresh' if datetime.date.today().weekday() == 3 else 'no prior data'
        print(f'  [Weekly] Jobless Claims (fresh fetch — {reason})...')
        data['icsa']    = fred_obs('ICSA',       260)   # weekly initial claims ~5 years
        data['ccsa']    = fred_obs('CCSA',       260)   # weekly continued claims ~5 years
    else:
        print('  [Weekly] Jobless Claims (carry forward — not Thursday)')
        data['icsa']    = prior_icsa
        data['ccsa']    = prior_ccsa

    print('  [Monthly] Labor...')
    data['unrate']      = fred_obs('UNRATE',     320)
    data['u6rate']      = fred_obs('U6RATE',     14)
    data['payems']      = fred_obs('PAYEMS',     320)
    data['ahetpi']      = fred_obs('AHETPI',     320)
    data['jolts']       = fv('JTSJOL')
    data['umcsent']     = fred_obs('UMCSENT',    30)   # UMich Consumer Sentiment (monthly)
    data['bls_sectors'] = bls_fetch([
        'CES0000000001','CES2000000001','CES3000000001',
        'CES4000000001','CES6000000001','CES7000000001',
    ])

    print('  [Monthly] Inflation...')
    data['cpi_all']     = fred_obs('CPIAUCSL',  320)
    data['cpi_core']    = fred_obs('CPILFESL',  320)
    data['pce']         = fred_obs('PCEPI',     320)
    data['pce_core']    = fred_obs('PCEPILFE',  320)
    data['psavert']     = fred_obs('PSAVERT',   320)

    print('  [Monthly] Housing...')
    data['houst']       = fred_obs('HOUST',      320)
    data['houst1f']     = fred_obs('HOUST1F',    320)
    data['permit']      = fred_obs('PERMIT',     320)
    data['cs_hpi']      = fred_obs('CSUSHPISA',  320)

    print('  [Quarterly] GDP + Credit...')
    data['gdpc1']       = fred_obs('GDPC1',  12)
    data['gdp_growth']  = fred_obs('A191RL1Q225SBEA', 12)
    data['cc_delinq']   = fred_obs('DRCCLACBS',  12)
    data['mtg_delinq']  = fred_obs('DRSFRMACBS', 12)
    data['tdsp']        = fred_obs('TDSP',   30)   # Household Debt Service Ratio (% of disp. income)

    # ── Annual history for chart rebuilding (from 2000) ──────────────
    print('  [History] Annual chart series...')
    data['fedfunds_annual']   = fred_obs('FEDFUNDS', 30, freq='a')
    data['mortgage30_annual'] = fred_obs('MORTGAGE30US', 30, freq='a')
    data['ig_oas_annual']     = fred_obs('BAMLC0A0CM', 30, freq='a')
    data['hy_oas_annual']     = fred_obs('BAMLH0A0HYM2', 30, freq='a')
    data['wti_annual']        = fred_obs('DCOILWTICO', 30, freq='a')
    data['brent_annual']      = fred_obs('DCOILBRENTEU', 30, freq='a')
    data['gdpc1_annual']      = fred_obs('GDPC1', 30, freq='a')
    data['gdp_annual']        = fred_obs('GDP', 30, freq='a')
    data['umcsent_annual']    = fred_obs('UMCSENT', 30, freq='a')
    data['cpiengsl']          = fred_obs('CPIENGSL', 320)
    data['revolsl_annual']    = fred_obs('REVOLSL', 30, freq='a')
    data['nonrevsl_annual']   = fred_obs('NONREVSL', 30, freq='a')

    # Monthly oil for OIL_MONTHLY chart (from 2000)
    print('  [History] Monthly oil prices...')
    data['wti_monthly']       = fred_obs('DCOILWTICO', 320, freq='m')
    data['brent_monthly']     = fred_obs('DCOILBRENTEU', 320, freq='m')

    # ── Carry forward: fill failed series from prior run ─────────────
    try:
        prior = json.loads(OUT_FILE.read_text()).get('data', {}) if OUT_FILE.exists() else {}
    except (json.JSONDecodeError, OSError):
        prior = {}
    carried = 0
    for key in data:
        if not data[key] and key in prior and prior[key]:
            data[key] = prior[key]
            carried += 1
    if carried:
        print(f'  ℹ  Carried forward {carried} series from prior run')

    # ── Package ───────────────────────────────────────────────────────
    n_ok = sum(1 for v in data.values() if v)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        'collected_at': ts, 'series_count': n_ok,
        'error_count': len(errors), 'errors': errors, 'data': data,
    }, indent=2, default=str))

    print(f'[Agent 1] Done: {n_ok}/{len(data)} series, {len(errors)} errors')
    for e in errors: print(f'  ⚠  {e}')
    # Succeed if we have data for most series (allow some FRED failures)
    return n_ok >= len(data) * 0.6


if __name__ == '__main__':
    sys.exit(0 if collect() else 1)
