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

# ── Secret scrubbing ──────────────────────────────────────────────────
# python-requests' HTTPError.__str__ embeds the full request URL, which
# includes query params — and our FRED/EIA fetches pass `api_key=…` as
# a query param. Stringifying the exception and appending it to `errors`
# would persist the key to data/raw_data.json and (via the analyzer)
# data/signals.json.raw_errors. Both files ship to the public repo on
# every weekly commit. To prevent this, wrap `errors` in a list whose
# `append` strips any `api_key=` (or `&key=` for EIA) query parameter
# from the string before storing. Belt-and-suspenders: callers don't
# need to remember to scrub at the call site.
import re as _re
_SECRET_RE = _re.compile(
    r'((?:[?&])(?:api_key|key|token|access_token|apikey)=)[^&\s\'"]+',
    flags=_re.IGNORECASE,
)

def _scrub_secrets(msg: str) -> str:
    """Replace any `?api_key=XYZ` / `&key=XYZ` query-param value with
    `[REDACTED]`. Idempotent — safe to call on already-scrubbed strings."""
    if not isinstance(msg, str):
        return msg
    return _SECRET_RE.sub(r'\1[REDACTED]', msg)

class _ErrList(list):
    """list whose `append` scrubs secrets from string entries.

    All existing `errors.append(f'... {e}')` call sites work unchanged;
    the api_key in a stringified exception URL is redacted before the
    value is stored in memory or written to disk.
    """
    def append(self, item):  # type: ignore[override]
        super().append(_scrub_secrets(str(item)) if isinstance(item, (str, Exception)) else item)

errors = _ErrList()


# ── B6.2: Per-observation provenance envelope ─────────────────────────
# Every obs dict carries:
#   date           — the observation's reporting date (legacy)
#   value          — float value (legacy)
#   source         — short attribution string, e.g. 'FRED:UNRATE',
#                    'ALFRED:UNRATE@2026-01-15', 'UMich:tbcics.csv',
#                    'EIA:RWTC'. Lets validator Pass 3i pin which API
#                    a given number came from when FRED and BLS publish
#                    overlapping series.
#   fetched_at     — ISO 8601 UTC of when collector recorded it.
# Optional:
#   status                 — 'preliminary' / 'final' (UMich)
#   carried_forward_from   — ISO 8601 UTC of a later run that reused
#                             this obs without refetching (so a stale
#                             obs is identifiable from the dict alone,
#                             not just by inspecting collected_at on
#                             the outer envelope).
# Back-compat: legacy {date,value} keys preserved; downstream code that
# only reads those two keys is unaffected.
def _envelope(date, value, source, **extra):
    obs = {'date': date, 'value': value, 'source': source,
           'fetched_at': datetime.datetime.utcnow().isoformat() + 'Z'}
    for k, v in extra.items():
        if v is not None:
            obs[k] = v
    return obs


def _carry_forward(prior_series, this_run_ts):
    """Stamp every dict in `prior_series` with carried_forward_from so
    a downstream consumer can tell a reused obs apart from a fresh one
    without cross-referencing the run's `collected_at` timestamp.
    Non-dict elements pass through unchanged (defensive — old data
    from before B6.2 may still be plain scalars in some edge cases)."""
    out = []
    for obs in prior_series:
        if isinstance(obs, dict):
            new = dict(obs)
            new['carried_forward_from'] = this_run_ts
            out.append(new)
        else:
            out.append(obs)
    return out


# ── FRED ──────────────────────────────────────────────────────────────

def fred_obs(series_id, limit=14, freq=None):
    """Return list of {date,value} newest first, no missing values.
    Retries up to 3 times with exponential backoff on 5xx and 429 (rate
    limit) errors. FRED's documented limit is 120 req/min per key; pre-flight
    + bulk fetch can briefly push past that, so we wait it out."""
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
            return [_envelope(o['date'], float(o['value']),
                              source=f'FRED:{series_id}')
                    for o in r.json().get('observations', []) if o['value'] != '.']
        except requests.exceptions.HTTPError as e:
            last_err = e
            if r.status_code == 429 and attempt < 3:
                # Rate limited — wait long enough to fall out of FRED's 60s window
                wait = 30 * (attempt + 1)  # 30s, 60s, 90s
                print(f'    ↻ FRED {series_id}: 429 rate limited, retry {attempt+1}/3 in {wait}s')
                time.sleep(wait)
                continue
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


# ── ALFRED (vintage-pinned FRED) ──────────────────────────────────────
# See METHODOLOGY.md §5 for the vintage-pinning rationale.

def last_quarter_end(today=None):
    """End date of the previous quarter, as YYYY-MM-DD string.
    e.g. if today=2026-04-20 (Q2) → '2026-03-31'."""
    from calendar import monthrange
    today = today or datetime.date.today()
    quarter_of = (today.month - 1) // 3 + 1  # 1..4
    if quarter_of == 1:
        y, m = today.year - 1, 12
    else:
        y = today.year
        m = (quarter_of - 1) * 3  # 3, 6, 9
    return f'{y}-{m:02d}-{monthrange(y, m)[1]:02d}'


def fred_alfred_obs(series_id, vintage_date, limit=14, freq=None):
    """Pull AS-OF-vintage observations from ALFRED.
    Returns values exactly as they were published on `vintage_date` — no
    subsequent revisions. Falls back to [] on any failure so callers can
    degrade to unpinned data without breaking the pipeline.
    See https://alfred.stlouisfed.org/docs/api/alfred/"""
    if not FRED_KEY:
        errors.append(f'FRED key missing — ALFRED skipped {series_id}'); return []
    params = {'series_id': series_id, 'api_key': FRED_KEY,
              'file_type': 'json', 'sort_order': 'desc', 'limit': limit,
              'realtime_start': vintage_date, 'realtime_end': vintage_date}
    if freq: params['frequency'] = freq
    # Same retry-with-backoff as fred_obs(): the 8 back-to-back ALFRED
    # vintage pulls (GDPC1/GDP/CPIAUCSL/PAYEMS/AHETPI/PCEPI/PCEPILFE…)
    # can briefly push past FRED's 120 req/min limit, and the later
    # ones (e.g. PCEPILFE) were getting a 429 with no retry → surfaced
    # as a Pass 3h collector error every run. Wait out the 60s window.
    last_err = None
    for attempt in range(4):  # 0, 1, 2, 3
        try:
            r = requests.get('https://api.stlouisfed.org/fred/series/observations',
                             params=params, timeout=15)
            r.raise_for_status()
            return [_envelope(o['date'], float(o['value']),
                              source=f'ALFRED:{series_id}@{vintage_date}')
                    for o in r.json().get('observations', []) if o['value'] != '.']
        except requests.exceptions.HTTPError as e:
            last_err = e
            if r.status_code == 429 and attempt < 3:
                wait = 30 * (attempt + 1)  # 30s, 60s, 90s
                print(f'    ↻ ALFRED {series_id}@{vintage_date}: 429 rate limited, retry {attempt+1}/3 in {wait}s')
                time.sleep(wait)
                continue
            if r.status_code >= 500 and attempt < 3:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f'    ↻ ALFRED {series_id}@{vintage_date}: {r.status_code}, retry {attempt+1}/3 in {wait}s')
                time.sleep(wait)
                continue
            break
        except Exception as e:
            last_err = e; break
    errors.append(f'ALFRED {series_id}@{vintage_date}: {last_err}'); return []


# ── UMich Survey of Consumers (direct) ───────────────────────────────

_UMICH_MONTHS = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
                 'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}

def umich_fetch():
    """Fetch monthly Consumer Sentiment Index direct from UMich.

    Parses tbcics.csv (~13 months). Preliminary releases are marked in
    column 0 as e.g. 'April (P)' — we surface that as status='preliminary'
    so the dashboard can badge it. Publishing cadence is prelim mid-month,
    final end-of-month; FRED republishes final only with a ~1 month lag,
    so the direct source gives us ~2–6 weeks earlier visibility.
    """
    url = 'https://www.sca.isr.umich.edu/files/tbcics.csv'
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; MacroDashboard/1.0)'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        rows = []
        for line in r.text.splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 5 or not parts[0] or not parts[1].isdigit():
                continue
            raw = parts[0]
            is_prelim = '(P)' in raw
            month_name = raw.replace('(P)', '').strip()
            if month_name not in _UMICH_MONTHS:
                continue
            try:
                value = float(parts[4])
            except ValueError:
                continue
            date = f"{parts[1]}-{_UMICH_MONTHS[month_name]:02d}-01"
            rows.append(_envelope(date, value,
                                  source='UMich:tbcics.csv',
                                  status='preliminary' if is_prelim else 'final'))
        rows.sort(key=lambda r: r['date'], reverse=True)
        return rows
    except Exception as e:
        errors.append(f'UMich direct: {e}'); return []


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
        return [_envelope(d['period'], float(d['value']),
                          source=f'EIA:{product}')
                for d in r.json()['response']['data'] if d['value']]
    except Exception as e:
        errors.append(f'EIA {product}: {e}'); return []


# ── Build OIL_DAILY for current month ────────────────────────────────

def build_oil_daily(wti_series, brent_series):
    """
    Extract daily sessions from EIA/FRED data starting March 1 of the
    current year.  Tracks the full oil-price trajectory through the year.
    """
    today = datetime.date.today()
    start_date = datetime.date(today.year, 3, 1)

    def filter_from(series):
        out = []
        for obs in reversed(series):  # oldest first
            d = datetime.date.fromisoformat(obs['date'])
            if d >= start_date:
                out.append({'date': d, 'value': obs['value']})
        return out

    wti_m   = filter_from(wti_series)
    brent_m = filter_from(brent_series)

    # Align by date
    wti_by_date   = {o['date']: o['value'] for o in wti_m}
    brent_by_date = {o['date']: o['value'] for o in brent_m}
    all_dates = sorted(set(list(wti_by_date.keys()) + list(brent_by_date.keys())))

    labels = []
    wti_vals = []
    brent_vals = []

    for d in all_dates:
        labels.append(f"{d.strftime('%b')} {d.day}")  # portable (no %-d, glibc-only on Windows)
        wti_vals.append(wti_by_date.get(d) or (wti_vals[-1] if wti_vals else None))
        brent_vals.append(brent_by_date.get(d) or (brent_vals[-1] if brent_vals else None))

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
        'month':    f'Mar–{today.strftime("%b %Y")}',
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
    wti_raw   = eia_spot('RWTC',  60)    # ~2 months to cover from Mar 1
    brent_raw = eia_spot('RBRTE', 60)
    if not wti_raw:   wti_raw   = fred_obs('DCOILWTICO',   60)
    if not brent_raw: brent_raw = fred_obs('DCOILBRENTEU', 60)
    data['wti_daily']    = wti_raw
    data['brent_daily']  = brent_raw
    data['oil_daily_chart'] = build_oil_daily(wti_raw, brent_raw)  # Mar 1 onward

    print('  [Weekly] Gasoline + Mortgage...')
    data['gasoline']    = fred_obs('GASREGW', 30)     # Weekly retail gasoline $/gal (EIA via FRED)
    data['mortgage30']  = fred_obs('MORTGAGE30US', 70)   # ~14 months weekly for 12-month chart
    data['mortgage15']  = fred_obs('MORTGAGE15US', 70)

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
        data['icsa']    = _carry_forward(prior_icsa, ts)
        data['ccsa']    = _carry_forward(prior_ccsa, ts)

    print('  [Monthly] Labor...')
    data['unrate']      = fred_obs('UNRATE',     480)
    data['u6rate']      = fred_obs('U6RATE',     14)
    data['payems']      = fred_obs('PAYEMS',     480)
    data['ahetpi']      = fred_obs('AHETPI',     480)
    # ADP National Employment Report — Total Nonfarm Private, MoM change (SA, K).
    # FRED NPPTTL was discontinued 2022-05 after ADP methodology revamp.
    # Fetched so renderer can detect a future series revival; renderer applies an
    # 18-month recency filter — stale obs fall through to prior-state.json round-trip.
    data['adp_nppttl']  = fred_obs('NPPTTL',     24)
    # ADP live scrape — adpemploymentreport.com/ner_production.json returns the
    # latest monthly headline as structured JSON (no browser needed).
    # Gives one data point: current month. Historical months accumulate via
    # prior-state.json round-trip in the renderer.
    try:
        _adp_r = requests.get('https://adpemploymentreport.com/ner_production.json',
                              timeout=10, headers={'User-Agent': 'macro-dashboard/1.0'})
        _adp_r.raise_for_status()
        _adp_j = _adp_r.json()
        # metricValue is raw headcount e.g. "109,000" — divide by 1000 to get K
        _adp_val = round(int(_adp_j['reportOverview']['cards'][0]['metricValue'].replace(',', '')) / 1000)
        _adp_mon = _adp_j.get('reportMonth', '')   # e.g. "April"
        _adp_yr  = str(_adp_j.get('reportYear', ''))  # e.g. "2026"
        _adp_dt  = datetime.datetime.strptime(f'{_adp_mon} {_adp_yr}', '%B %Y')
        data['adp_latest'] = {
            'value': _adp_val,
            'label': _adp_dt.strftime("%b'%y"),  # "Apr'26"
            'month': _adp_mon,
            'year':  _adp_yr,
        }
        print(f'✅ ADP latest: {_adp_val:+,}K ({_adp_mon} {_adp_yr})')
    except Exception as _adp_err:
        data['adp_latest'] = None
        print(f'⚠️  ADP latest fetch failed: {_adp_err}')
    # Atlanta Fed Wage Growth Tracker — 3-Month MA, Unweighted Median, Hourly,
    # Overall. Measures wage growth for workers continuously employed over 12
    # months (controls for composition effects that bias AHETPI).
    # Used as the headline wage growth KPI; AHETPI retained for level charts
    # and sector breakdowns (Atlanta Fed has no sector decomposition).
    data['wage_growth_atl'] = fred_obs('FRBATLWGT3MMAUMHWGO', 60)
    # JOLTS suite — B3.1. JTSJOL stays as a single-value KPI; the *_hist
    # series feed a forthcoming JOLTS chart panel (24 obs = 2 yrs monthly).
    # V/U ratio is computed downstream from jolts_hist + unemploy_hist
    # (UNEMPLOY is the BLS unemployed-level series in thousands, NOT the
    # unemployment rate — UNRATE — that the dashboard already shows).
    data['jolts']       = fv('JTSJOL')                  # Job Openings (latest)
    data['jolts_hist']  = fred_obs('JTSJOL', 24)        # Job Openings — history
    data['quits']       = fred_obs('JTSQUL', 24)        # Quits Level
    data['hires']       = fred_obs('JTSHIL', 24)        # Hires Level
    data['unemploy_hist'] = fred_obs('UNEMPLOY', 24)    # Unemployed (level, for V/U)
    # UMich Consumer Sentiment: direct source gives prelim flag + fresher data;
    # FRED fills history older than the direct CSV's 13-month window (all final).
    umich_direct = umich_fetch()
    if umich_direct:
        fred_umcsent = fred_obs('UMCSENT', 30)
        umich_dates = {r['date'] for r in umich_direct}
        fred_extras = [{**f, 'status': 'final'} for f in fred_umcsent if f['date'] not in umich_dates]
        data['umcsent'] = sorted(umich_direct + fred_extras, key=lambda r: r['date'], reverse=True)
    else:
        data['umcsent'] = [{**r, 'status': 'final'} for r in fred_obs('UMCSENT', 30)]
    data['bls_sectors'] = bls_fetch([
        'CES0000000001',  # Total Nonfarm
        'CES1000000001',  # Mining & Energy (Mining and Logging)
        'CES2000000001',  # Construction
        'CES3000000001',  # Manufacturing
        'CES4200000001',  # Retail Trade
        'CES4300000001',  # Transportation & Warehousing
        'CES5000000001',  # Information (Tech)
        'CES5500000001',  # Financial Activities
        'CES6000000001',  # Professional & Business Services
        'CES6561000001',  # Education (Private)
        'CES6562000001',  # Healthcare
        'CES7000000001',  # Leisure & Hospitality
        'CES9091000001',  # Federal Government
        'CES9093000001',  # State & Local Government
    ])

    # Sector unemployment rates (BLS CPS) for U_SECTOR_MOM auto-rebuild.
    # NOTE: BLS does not publish seasonally-adjusted (LNS14) sector unemployment
    # rates by industry. LNU04 (not seasonally adjusted) is the only available
    # series. 11 sectors — Hotel/Lodging and Restaurants consolidated into
    # Leisure & Hospitality (LNU04032241).
    print('  [Monthly] Sector Unemployment (CPS)...')
    data['bls_unemp_sectors'] = bls_fetch([
        'LNU04032231',  # Construction
        'LNU04032232',  # Manufacturing
        'LNU04032235',  # Wholesale & Retail Trade
        'LNU04032236',  # Transport & Warehousing
        'LNU04032237',  # Information/Tech
        'LNU04032238',  # Financial Activities
        'LNU04032239',  # Prof. & Biz Services
        'LNU04032240',  # Healthcare & Education
        'LNU04032241',  # Leisure & Hospitality
        'LNU04032230',  # Agriculture & Mining
        'LNU04028615',  # Government
    ])

    print('  [Monthly] Inflation...')
    data['cpi_all']     = fred_obs('CPIAUCSL',  480)
    data['cpi_core']    = fred_obs('CPILFESL',  480)
    data['pce']         = fred_obs('PCEPI',     480)
    data['pce_core']    = fred_obs('PCEPILFE',  480)
    data['psavert']     = fred_obs('PSAVERT',   480)

    # CPI category detail for CPI_CAT_MOM auto-rebuild.
    # All categories need >=13 obs so renderer's _yoy_from_index can compute
    # latest YoY (current month + same month a year ago). 24 leaves headroom
    # for the shock tracker's pre-shock baselines.
    print('  [Monthly] CPI Categories (FRED)...')
    data['cpi_shelter']   = fred_obs('CUSR0000SAH1', 24)  # Shelter
    # 30 obs leaves margin above the 24 that the shock-tracker YoY+pre-shock
    # math requires (13 YoY + ~11 buffer); avoids borderline n=23 from FRED lag.
    data['cpi_food_away'] = fred_obs('CUSR0000SEFV', 30)  # Food Away from Home
    # 2026-07-23: was CUSR0000SETG ("Public Transportation" -- a narrow,
    # airfare-heavy basket) mislabeled as "Transportation Services" -- found
    # via a user question about a 16.9% YoY reading that turned out to be
    # real but for the wrong series (BLS's actual "Transportation services"
    # line was 3.4% YoY the same month). SAS4 is BLS/FRED's real
    # "Transportation Services" series, verified against BLS CPI Table 1.
    data['cpi_transport'] = fred_obs('CUSR0000SAS4', 30)  # Transportation Services
    data['cpi_medical']   = fred_obs('CUSR0000SAM2', 24)  # Medical Care Services
    data['cpi_food_home'] = fred_obs('CUSR0000SAF11',24)  # Food at Home
    data['cpi_new_veh']   = fred_obs('CUSR0000SETA01',24) # New Vehicles
    data['cpi_apparel']   = fred_obs('CPIAPPSL',     24)  # Apparel (SA)
    # cpi_energy bucket sources from cpiengsl above (CPIENGSL, 320 obs); no
    # separate fetch needed. The bad CUSR0000SA0E ID returned 400s for months.
    data['cpi_used_cars'] = fred_obs('CUSR0000SETA02',24) # Used Cars & Trucks

    # Inflation breadth — B3.3. Cleveland Fed publishes trimmed-mean and
    # weighted-median CPI as smoothed signals that drop the most volatile
    # 8% of categories per side and the volatility-weighted middle. These
    # consistently lead the Fed's preferred-measure narrative ahead of
    # headline CPI/PCE turns. Series are already in YoY% form (157SFRBCLE
    # publishes as 12-month percent change, no _yoy_from_index needed).
    # Supercore (services ex-shelter) has no clean FRED series and is
    # composed at runtime in the renderer when needed.
    # NTRI (New-Tenant Rent Index) is BLS-experimental and not yet on
    # FRED; deferred to a later batch when BLS promotes the series.
    data['cpi_trimmed']  = fred_obs('TRMMEANCPIM157SFRBCLE', 24)
    data['cpi_median']   = fred_obs('MEDCPIM157SFRBCLE',     24)

    # PCE top-level component price indexes (BEA Table 2.3.4 via FRED) for
    # PCE_CAT_MOM auto-rebuild. BEA only publishes monthly chain-type price
    # indexes at the top-aggregate level — services sub-categories (housing,
    # healthcare, recreation, etc.) are quarterly only. These 4 are the
    # canonical decomposition of headline PCE: Goods + Services + Food +
    # Energy goods & services. 24 obs so _yoy_from_index can compute YoY.
    print('  [Monthly] PCE Components (FRED)...')
    data['pce_goods']    = fred_obs('DGDSRG3M086SBEA', 24)  # Goods (aggregate)
    data['pce_services'] = fred_obs('DSERRG3M086SBEA', 24)  # Services (aggregate)
    data['pce_food']     = fred_obs('DFXARG3M086SBEA', 24)  # Food & Bev (off-premises)
    data['pce_energy']   = fred_obs('DNRGRG3M086SBEA', 24)  # Energy goods & services

    print('  [Monthly] Housing...')
    data['houst']       = fred_obs('HOUST',      480)
    data['houst1f']     = fred_obs('HOUST1F',    480)
    data['permit']      = fred_obs('PERMIT',     480)
    data['cs_hpi']      = fred_obs('CSUSHPISA',  480)

    print('  [Quarterly] GDP + Credit...')
    data['gdpc1']       = fred_obs('GDPC1',  12)
    data['gdp_growth']  = fred_obs('A191RL1Q225SBEA', 12)
    # Card 90+ DPD (DRCCLACBS) — quarterly Fed release. Pull ~27 yrs of
    # history (108 obs) so renderer.rebuild_treasury_data can populate the
    # TREASURY_DATA.card90 line from 2000 onward, not just the last 3 yrs.
    data['cc_delinq']   = fred_obs('DRCCLACBS',  108)
    data['mtg_delinq']  = fred_obs('DRSFRMACBS', 12)
    data['tdsp']        = fred_obs('TDSP',   30)   # Household Debt Service Ratio (% of disp. income)

    # Fed liquidity — B3.4. Four weekly H.4.1 series that jointly describe
    # the size and composition of the Fed's balance sheet and the system
    # cash that sits outside private bank reserves. Watch list:
    #   WALCL      Fed total assets (size of the balance sheet itself —
    #              flat-or-shrinking signals QT, rising signals QE)
    #   WRESBAL    Bank reserves at the Fed (the cash buffer that flows
    #              into repo when the Treasury issues bills — when this
    #              dips toward $3T, money-market plumbing gets tight)
    #   RRPONTSYD  Overnight reverse-repo facility take-up (the marginal
    #              parking lot for excess MMF cash; near-zero = MMF cash
    #              has been redeployed and won't backstop falling reserves)
    #   WTREGEN    Treasury General Account at the Fed (debt-ceiling and
    #              issuance dynamics drain/refill this; a falling TGA
    #              floods reserves into the system)
    # 104 obs ≈ 2 yrs of weekly data — enough for a regime-cycle chart.
    data['walcl']      = fred_obs('WALCL',      104)
    data['wresbal']    = fred_obs('WRESBAL',    104)
    data['rrpontsyd']  = fred_obs('RRPONTSYD',  104)
    data['tga']        = fred_obs('WTREGEN',    104)

    # Fiscal — B3.2. Only the deficit/GDP series is FRED-fetchable.
    # The other two leading-edge fiscal indicators the spec calls for —
    # Hutchins Fiscal Impulse Measure (Brookings) and CBO baseline (CBO
    # Budget Outlook tables) — are PDF-only publications without a
    # stable API. They get hand-curated into data/fiscal_overrides.json
    # by the same quarterly cadence as data/earnings_calendar.json once
    # the fiscal tab UI lands.
    #   FYFSGDA188S — Federal Surplus or Deficit [-] as % of GDP, annual
    # 30 obs covers 1995-onward so the chart can show full post-2000
    # fiscal regimes (Clinton surplus → GFC → Trump tax cuts → COVID
    # blowout → post-COVID structural deficit).
    data['deficit_gdp'] = fred_obs('FYFSGDA188S', 30)

    # ── Annual history for chart rebuilding (from 2000) ──────────────
    print('  [History] Annual chart series...')
    data['fedfunds_annual']   = fred_obs('FEDFUNDS', 40, freq='a')
    data['mortgage30_annual'] = fred_obs('MORTGAGE30US', 40, freq='a')
    data['dgs10_annual']      = fred_obs('DGS10', 40, freq='a')
    data['dgs2_annual']       = fred_obs('DGS2', 40, freq='a')
    # FRED's freq='a' aggregation only returns 2 obs for these daily series
    # (cause unclear — works fine for FEDFUNDS). Fetch monthly instead and
    # aggregate to annual averages locally in the renderer; gives full
    # 30-year history reliably.
    data['ig_oas_monthly']    = fred_obs('BAMLC0A0CM', 360, freq='m')
    data['hy_oas_monthly']    = fred_obs('BAMLH0A0HYM2', 360, freq='m')
    data['wti_annual']        = fred_obs('DCOILWTICO', 40, freq='a')
    data['brent_annual']      = fred_obs('DCOILBRENTEU', 40, freq='a')
    data['gdpc1_annual']      = fred_obs('GDPC1', 40, freq='a')
    data['gdp_annual']        = fred_obs('GDP', 40, freq='a')
    # Vintage-pinned copies for historical charts (see METHODOLOGY.md §5).
    # Pin rolls forward each quarter. All pinned series share the same pin
    # date so cross-series comparisons stay coherent within a pin cycle.
    _pin = last_quarter_end()
    data['gdpc1_annual_pinned'] = fred_alfred_obs('GDPC1',    _pin, 40,  freq='a')
    data['gdp_annual_pinned']   = fred_alfred_obs('GDP',      _pin, 40,  freq='a')
    # Monthly series feeding annual-aggregate charts (CPI_ANNUAL, JOBS_ANNUAL,
    # WAGE_ANNUAL). Monthly/YoY current-period KPIs continue reading unpinned
    # `cpi_all`, `payems`, `ahetpi` for freshness.
    data['cpi_all_pinned']      = fred_alfred_obs('CPIAUCSL', _pin, 480)
    data['payems_pinned']       = fred_alfred_obs('PAYEMS',   _pin, 480)
    data['ahetpi_pinned']       = fred_alfred_obs('AHETPI',   _pin, 480)
    data['pce_pinned']          = fred_alfred_obs('PCEPI',    _pin, 480)
    data['pce_core_pinned']     = fred_alfred_obs('PCEPILFE', _pin, 480)
    data['vintages'] = {
        'gdpc1_annual': {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'gdp_annual':   {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'cpi_all':      {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'payems':       {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'ahetpi':       {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'pce':          {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
        'pce_core':     {'pin_date': _pin, 'refresh_cadence': 'quarterly'},
    }
    data['umcsent_annual']    = fred_obs('UMCSENT', 40, freq='a')
    data['cpiengsl']          = fred_obs('CPIENGSL', 480)
    data['revolsl_annual']    = fred_obs('REVOLSL', 40, freq='a')
    data['nonrevsl_annual']   = fred_obs('NONREVSL', 40, freq='a')

    # Monthly oil for OIL_MONTHLY chart (from 2000)
    print('  [History] Monthly oil prices...')
    data['wti_monthly']       = fred_obs('DCOILWTICO', 480, freq='m')
    data['brent_monthly']     = fred_obs('DCOILBRENTEU', 480, freq='m')

    # ── Carry forward: fill failed series from prior run ─────────────
    try:
        prior = json.loads(OUT_FILE.read_text()).get('data', {}) if OUT_FILE.exists() else {}
    except (json.JSONDecodeError, OSError):
        prior = {}
    carried = 0
    for key in data:
        if not data[key] and key in prior and prior[key]:
            # Stamp carried_forward_from when reusing list-of-obs series;
            # leave scalar/dict shapes (e.g. single-value fv() results)
            # alone since those are handled by fv() at fetch time.
            if isinstance(prior[key], list):
                data[key] = _carry_forward(prior[key], ts)
            else:
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
