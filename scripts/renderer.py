#!/usr/bin/env python3
"""
Agent 4 — RENDERER  (renderer.py)
Reads raw_data.json + analysis.json.
Patches index.html: chart arrays, KPIs, tab commentary.
No LLM. Output: index.html (updated in-place).
"""

import os, re, json, datetime, math, sys
from pathlib import Path

# Tier 1 anti-clone: state-bundle writer. Renderer functions register
# their JSON payloads here instead of (or in addition to) inlining
# them as JS literals; render() calls flush() at the end. See
# scripts/_api_writer.py for the full rationale.
# Sibling-module import — works when renderer.py is invoked as
# `python scripts/renderer.py` (script dir is on sys.path) and when
# the test suite imports renderer from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _api_writer  # noqa: E402


ROOT      = Path(__file__).parent.parent
HTML_FILE = ROOT / 'index.html'
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SIG_FILE  = ROOT / 'data' / 'signals.json'
ANA_FILE  = ROOT / 'data' / 'analysis.json'
OVR_FILE  = ROOT / 'data' / 'overrides.json'
VAL_FILE  = ROOT / 'data' / 'validation_report.json'
BANK_FILE = ROOT / 'data' / 'bank_earnings.json'

applied  = []
errors   = []
warnings = []

# Structured record of every re.subn call that returned 0 replacements.
# Distinct from `errors`/`warnings` so the --strict gate can target ONLY
# silent-injection failures (the stability risk this list was added for).
# Each entry: f'{section}: pattern {pattern!r} matched 0 times'
zero_replacement_errors: list = []
# Counter for successful re.subn injections (count > 0) so the SUMMARY
# block at end of main() has a meaningful denominator.
subn_success_count = 0


def _record_subn_result(section, pattern, count):
    """Audit a re.subn outcome.

    Increments the global success counter when count > 0 and appends a
    structured entry to `zero_replacement_errors` when count == 0.
    `pattern` may be a compiled regex or a raw string — both are stringified
    so a maintainer can diff against the JSON shape currently in index.html.

    Note: this purely observes; it does NOT change patching behaviour. The
    existing applied/warnings/errors lists keep working unchanged so the
    weekly Saturday run is byte-identical in non-strict mode.
    """
    global subn_success_count
    if count and count > 0:
        subn_success_count += 1
        return
    try:
        pat_str = pattern.pattern if hasattr(pattern, 'pattern') else str(pattern)
    except Exception:
        pat_str = '<unprintable pattern>'
    zero_replacement_errors.append(f'{section}: pattern {pat_str!r} matched 0 times')

START_YEAR = 1990   # all annual/historical charts start from this year

# Single source of truth for the rolling-monthly trend window. Every chart
# that shows a "last N months" view (CPI, PCE, U-3, Wage, Saving, Sentiment,
# Housing, NFP-vs-ADP) rebuilds N entries from this constant. Bumping it
# auto-updates the panel titles too via _patch_trend_window_titles.
# Does NOT affect: NFP_BLS_MOM (24mo by design), shock-tracker windows
# (different methodology), Sahm Rule trailing 12-month low (Fed's rule).
MONTHLY_TREND_WINDOW = 13


# ── CHART HISTORY HELPERS ─────────────────────────────────────────────

def _annual_avg(monthly_series, start_year=START_YEAR):
    """Compute annual averages from monthly data (newest-first). Returns (labels, values)."""
    if not monthly_series or len(monthly_series) < 12:
        return [], []
    by_yr = {}
    for obs in monthly_series:
        yr = int(obs['date'][:4])
        if yr >= start_year:
            by_yr.setdefault(yr, []).append(obs['value'])
    today = datetime.date.today()
    labels, values = [], []
    for yr in sorted(by_yr):
        # Skip current year (partial) — monthly charts show current data
        if yr == today.year:
            continue
        # Require at least 6 months of data for a valid annual average
        if len(by_yr[yr]) >= 6:
            labels.append(str(yr))
            values.append(round(sum(by_yr[yr]) / len(by_yr[yr]), 1))
    return labels, values


def _dec_yoy(monthly_series, start_year=START_YEAR):
    """Compute Dec-to-Dec YoY% from monthly index data. Returns (labels, values)."""
    if not monthly_series or len(monthly_series) < 24:
        return [], []
    by_ym = {}
    for obs in monthly_series:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        by_ym[(yr, mo)] = obs['value']
    labels, values = [], []
    today = datetime.date.today()
    for yr in sorted(set(y for y, m in by_ym if y >= start_year and y < today.year)):
        cur = by_ym.get((yr, 12))
        prev = by_ym.get((yr - 1, 12))
        if cur is not None and prev is not None and prev != 0:
            labels.append(str(yr))
            values.append(round((cur - prev) / prev * 100, 1))
    return labels, values


def _latest_yoy(monthly_series):
    """Compute latest-month YoY% from monthly index data.
    Matches by calendar month 12 months prior (not by index position),
    so gaps in monthly data (e.g. gov't shutdown) don't shift the comparison.
    """
    if not monthly_series or len(monthly_series) < 13:
        return None, None
    latest = monthly_series[0]
    v0 = latest['value']
    d0 = datetime.datetime.strptime(latest['date'], '%Y-%m-%d')
    # Find the observation from exactly 12 months ago
    target_yr = d0.year - 1
    target_mo = d0.month
    v12 = None
    for obs in monthly_series:
        od = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
        if od.year == target_yr and od.month == target_mo:
            v12 = obs['value']
            break
    if v12 is None or v12 == 0:
        return None, None
    yoy = round((v0 - v12) / v12 * 100, 1)
    lbl = d0.strftime("%b'%y")
    return lbl, yoy


def _monthly_yoy_series(monthly_series, n_months=None):
    """Compute YoY% for the last n_months from monthly index data (newest-first).
    Returns (labels, values) where labels are "Mon'YY" strings.
    Default = MONTHLY_TREND_WINDOW — gives a full year-over-year visual span
    (latest plus same month a year ago) on the rolling trend charts."""
    if n_months is None:
        n_months = MONTHLY_TREND_WINDOW
    if not monthly_series or len(monthly_series) < 13 + n_months:
        return [], []
    # Build date→value lookup
    by_ym = {}
    for obs in monthly_series:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        by_ym[(yr, mo)] = obs['value']
    # Compute YoY for most recent n_months (series is newest-first)
    labels, values = [], []
    for i in range(n_months):
        obs = monthly_series[i]
        d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
        yr_ago_val = by_ym.get((d.year - 1, d.month))
        if yr_ago_val and yr_ago_val != 0:
            yoy = round((obs['value'] - yr_ago_val) / yr_ago_val * 100, 1)
            labels.append(d.strftime("%b'%y"))
            values.append(yoy)
    # Reverse to oldest-first for chart display
    labels.reverse()
    values.reverse()
    return labels, values


def _monthly_avg_by_month(weekly_series, n_months=None):
    """Compute monthly averages from weekly data (newest-first).
    Returns (labels, avg_values) for the last n_months complete months.
    Default n_months = MONTHLY_TREND_WINDOW."""
    if n_months is None:
        n_months = MONTHLY_TREND_WINDOW
    if not weekly_series:
        return [], []
    from collections import defaultdict
    by_ym = defaultdict(list)
    for obs in weekly_series:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        by_ym[(yr, mo)].append(obs['value'])
    # Sort by date, take last n_months+1 (skip current partial month)
    today = datetime.date.today()
    sorted_ym = sorted(by_ym.keys())
    # Exclude current month (may be partial)
    sorted_ym = [(y, m) for y, m in sorted_ym if (y, m) < (today.year, today.month)]
    recent = sorted_ym[-n_months:] if len(sorted_ym) >= n_months else sorted_ym
    labels, values = [], []
    for yr, mo in recent:
        d = datetime.date(yr, mo, 1)
        avg = round(sum(by_ym[(yr, mo)]) / len(by_ym[(yr, mo)]), 2)
        labels.append(d.strftime("%b'%y"))
        values.append(avg)
    return labels, values


def _annual_from_freq(annual_series, start_year=START_YEAR, precision=1, scale=1):
    """Extract annual data from FRED freq='a' series. Returns (labels, values)."""
    if not annual_series:
        return [], []
    labels, values = [], []
    today = datetime.date.today()
    for obs in sorted(annual_series, key=lambda x: x['date']):
        yr = int(obs['date'][:4])
        if yr >= start_year and yr < today.year:
            labels.append(str(yr))
            values.append(round(obs['value'] * scale, precision))
    return labels, values


def _annual_avg_from_monthly(monthly_series, start_year=START_YEAR, precision=1, scale=1):
    """Aggregate a monthly FRED series to annual averages. Returns (labels, values).
    Used when FRED's freq='a' aggregation is unreliable (e.g. BAML OAS series)."""
    if not monthly_series:
        return [], []
    today = datetime.date.today()
    by_year = {}
    for obs in monthly_series:
        yr = int(obs['date'][:4])
        if yr >= start_year and yr < today.year:
            by_year.setdefault(yr, []).append(obs['value'])
    labels, values = [], []
    for yr in sorted(by_year):
        avg = sum(by_year[yr]) / len(by_year[yr])
        labels.append(str(yr))
        values.append(round(avg * scale, precision))
    return labels, values


def _inject_const(html, var_name, obj):
    """Replace const VAR_NAME = {...}; in HTML with new data."""
    new_json = json.dumps(obj, separators=(', ', ':'))
    # Match from 'const VAR_NAME = {' to next '};'
    pattern = rf'const {var_name}\s*=\s*\{{[\s\S]*?\}};'
    new_decl = f'const {var_name} = {new_json};'
    # Use lambda to avoid regex interpreting \u escapes in replacement
    new_html, n = re.subn(pattern, lambda m: new_decl, html, count=1)
    _record_subn_result(f'_inject_const[{var_name}]', pattern, n)
    if n:
        pts = len(obj.get('labels', []))
        applied.append(f'{var_name} rebuilt ({pts} pts from {START_YEAR})')
        return new_html
    else:
        warnings.append(f'_inject_const: {var_name} not matched')
        return html


def _month_lbl(date_str):
    """Convert 'YYYY-MM-DD' to "Feb'26" style label."""
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")


def _patch_trend_window_titles(html):
    """Roll panel titles + JS comments to match MONTHLY_TREND_WINDOW.
    Single source of truth: bumping MONTHLY_TREND_WINDOW automatically updates
    every chart's title text on the next render. Patterns are explicit per
    panel to avoid clobbering legitimate non-chart-window references like the
    Sahm Rule's 'trailing 12-month low' or the NY Fed's '12-month-ahead'
    recession probability."""
    n = MONTHLY_TREND_WINDOW
    # Panel titles using "X-Month Trend"
    for prefix in [r'Monthly Unemployment Rate — ',
                   r'Monthly CPI — Headline vs Core YoY % \(',
                   r'Monthly Wage Growth — Nominal vs Real YoY % \(']:
        html = re.sub(rf'({prefix})\d+(-Month Trend)',
                      lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    # Housing — "(X-Month)" w/o "Trend"
    html = re.sub(r'(Monthly Housing Trend — Case-Shiller YoY % &amp; 30yr Mortgage Rate \()\d+(-Month\))',
                  lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    # "Last X Months" panel titles (Saving Rate, Consumer Sentiment)
    for prefix in [r'Personal Saving Rate — Last ',
                   r'Consumer Sentiment — Last ']:
        html = re.sub(rf'({prefix})\d+( Months)',
                      lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    # PCE panel-sub: "Last X months · BEA · Fed's preferred..."
    html = re.sub(r'(panel-sub">Last )\d+( months · BEA · Fed)',
                  lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    # JS comments
    html = re.sub(r'(// Saving rate — monthly \(last )\d+( months, bar chart\))',
                  lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    html = re.sub(r'(// UMich Consumer Sentiment — monthly \(last )\d+( months, bar chart\))',
                  lambda m: f'{m.group(1)}{n}{m.group(2)}', html)
    return html


def rebuild_charts(html, data):
    """Rebuild all chart arrays from collected historical data (from START_YEAR)."""
    today = datetime.date.today()
    # Roll panel titles to match the current trend window first — so titles
    # and rebuilt data consts can never disagree.
    html = _patch_trend_window_titles(html)

    # ── U_ANNUAL (annual averages only — monthly shown in U_MONTHLY) ──
    unrate = data.get('unrate', [])
    if len(unrate) >= 60:
        labels, values = _annual_avg(unrate)
        if labels:
            html = _inject_const(html, 'U_ANNUAL', {'labels': labels, 'data': values})

    # ── CPI_ANNUAL (Dec-to-Dec only — monthly shown in CPI_MONTHLY) ───
    # Prefer vintage-pinned series for the historical annual aggregate; the
    # current-period monthly/YoY values elsewhere continue to read live data.
    cpi_all = data.get('cpi_all_pinned') or data.get('cpi_all', [])
    if len(cpi_all) >= 60:
        labels, values = _dec_yoy(cpi_all)
        # Compute 3-month moving average of monthly YoY rates
        avg3m = []
        if len(cpi_all) >= 15:
            # cpi_all is newest-first; compute monthly YoY for recent months
            # Build date→value lookup for year-ago matching (handles data gaps)
            _cpi_by_ym = {}
            for obs in cpi_all:
                _d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
                _cpi_by_ym[(_d.year, _d.month)] = obs['value']
            monthly_yoy = []
            for i in range(min(len(cpi_all), 36)):
                cur_v = cpi_all[i]['value']
                _d = datetime.datetime.strptime(cpi_all[i]['date'], '%Y-%m-%d')
                yr_ago = _cpi_by_ym.get((_d.year - 1, _d.month))
                if yr_ago and yr_ago != 0:
                    monthly_yoy.append(round((cur_v - yr_ago) / yr_ago * 100, 2))
                else:
                    monthly_yoy.append(None)
            # 3M avg of the 3 most recent monthly YoY rates
            valid = [v for v in monthly_yoy[:3] if v is not None]
            if valid:
                avg3m = [round(sum(valid) / len(valid), 1)]
        if labels:
            html = _inject_const(html, 'CPI_ANNUAL', {
                'labels': labels, 'data': values,
                'avg3m': avg3m[0] if avg3m else None})

    # ── PCE_ANNUAL ────────────────────────────────────────────────────
    # Pinned inputs: headline + core PCE (Fed's preferred inflation gauge).
    # BEA does annual revisions + occasional methodology updates that restate
    # multi-year history; pin stabilizes the long chart against those.
    pce = data.get('pce_pinned') or data.get('pce', [])
    pce_core = data.get('pce_core_pinned') or data.get('pce_core', [])
    if len(pce) >= 60 and len(pce_core) >= 60:
        h_labels, h_values = _dec_yoy(pce)
        c_labels, c_values = _dec_yoy(pce_core)
        # Align both series to same label set
        common_labels = [l for l in h_labels if l in c_labels]
        headline = [h_values[h_labels.index(l)] for l in common_labels]
        core = [c_values[c_labels.index(l)] for l in common_labels]
        # Annual only — monthly shown in PCE_MONTHLY
        if common_labels:
            html = _inject_const(html, 'PCE_ANNUAL', {
                'labels': common_labels, 'headline': headline, 'core': core})

    # ── WAGE_ANNUAL ───────────────────────────────────────────────────
    # Primary source: Atlanta Fed Wage Growth Tracker 3MMA (FRBATLWGT3MMAUMHWGO).
    # Each monthly observation is already a YoY %, so annual-rate = the
    # December reading of that year (3MMA measured at end-Q4 ≈ the year's
    # headline wage-growth rate). Fallback: AHETPI Dec-to-Dec YoY (vintage-
    # pinned) — keeps long-history continuity if the new series hasn't been
    # collected yet.
    atl_wgt = data.get('wage_growth_atl', [])
    ahetpi = data.get('ahetpi_pinned') or data.get('ahetpi', [])
    c_labels_all, c_values_all = (_dec_yoy(cpi_all) if len(cpi_all) >= 60 else ([], []))
    labels, nominal, real = [], [], []
    if atl_wgt and len(atl_wgt) >= 12 and c_labels_all:
        # Group Atlanta Fed monthly values by year and pick each year's
        # December reading (or latest month if Dec not yet available).
        by_year = {}
        for obs in atl_wgt:
            y, m = obs['date'][:4], int(obs['date'][5:7])
            # Prefer December; else keep the latest month seen for that year
            if y not in by_year or by_year[y][0] < m:
                by_year[y] = (m, obs['value'])
        for y in sorted(by_year.keys()):
            if y in c_labels_all:
                n = round(by_year[y][1], 1)
                c = c_values_all[c_labels_all.index(y)]
                labels.append(y)
                nominal.append(n)
                real.append(round(n - c, 1))
    elif len(ahetpi) >= 60 and c_labels_all:
        # Fallback: AHETPI Dec-YoY
        w_labels, w_values = _dec_yoy(ahetpi)
        for l in w_labels:
            if l in c_labels_all:
                n = w_values[w_labels.index(l)]
                c = c_values_all[c_labels_all.index(l)]
                labels.append(l)
                nominal.append(n)
                real.append(round(n - c, 1))
    # Annual only — monthly shown in WAGE_MONTHLY
    if labels:
        html = _inject_const(html, 'WAGE_ANNUAL', {
            'labels': labels, 'nominal': nominal, 'real': real})

    # ── JOBS_ANNUAL ───────────────────────────────────────────────────
    # Pinned for historical stability against BLS annual benchmark revisions
    # (the 2025 benchmark rewrote ~862K jobs across 2024; pin prevents that
    # from silently restating numbers on the 25yr payrolls chart).
    payems = data.get('payems_pinned') or data.get('payems', [])
    if len(payems) >= 60:
        by_ym = {}
        for obs in payems:
            yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
            by_ym[(yr, mo)] = obs['value']
        labels, values = [], []
        for yr in sorted(set(y for y, m in by_ym if y >= START_YEAR and y < today.year)):
            dec_cur = by_ym.get((yr, 12))
            dec_prev = by_ym.get((yr - 1, 12))
            if dec_cur is not None and dec_prev is not None:
                labels.append(str(yr))
                values.append(round(dec_cur - dec_prev))
        if labels:
            html = _inject_const(html, 'JOBS_ANNUAL', {
                'labels': labels, 'data': values})

    # ── CLAIMS_WEEKLY ────────────────────────────────────────────────
    icsa = data.get('icsa', [])
    ccsa = data.get('ccsa', [])
    if len(icsa) >= 52:
        # Weekly data newest-first; reverse to oldest-first
        icsa_sorted = sorted(icsa, key=lambda x: x['date'])
        ccsa_sorted = sorted(ccsa, key=lambda x: x['date']) if ccsa else []
        ccsa_by_date = {o['date']: o['value'] for o in ccsa_sorted}
        labels, initial, continued = [], [], []
        prev_month = None
        for obs in icsa_sorted:
            yr = int(obs['date'][:4])
            if yr >= 2020:  # Show from 2020 to capture COVID spike + recovery
                d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
                cur_month = (d.year, d.month)
                # Label: "Jan'20" for first week of each month, blank otherwise
                if cur_month != prev_month:
                    labels.append(d.strftime("%b'%y"))
                else:
                    labels.append('')
                prev_month = cur_month
                initial.append(round(obs['value']))
                cc_val = ccsa_by_date.get(obs['date'])
                continued.append(round(cc_val) if cc_val is not None else None)
        # Ensure last data point always has a visible label showing the latest week's date
        if labels:
            d = datetime.datetime.strptime(icsa_sorted[-1]['date'], '%Y-%m-%d')
            # `%-d` (no zero-pad) is Linux/macOS-only — Windows raises
            # ValueError("Invalid format string"). Build the day manually so
            # both platforms produce e.g. "8 Mar'26" identically.
            labels[-1] = f'{d.day} ' + d.strftime("%b'%y")
        if labels:
            html = _inject_const(html, 'CLAIMS_WEEKLY', {
                'labels': labels, 'initial': initial, 'continued': continued})

    # ── SAVING_ANNUAL (annual averages from START_YEAR) ───────────────
    psavert = data.get('psavert', [])
    if len(psavert) >= 60:
        labels, values = _annual_avg(psavert)
        if labels:
            html = _inject_const(html, 'SAVING_ANNUAL', {'labels': labels, 'data': values})

    # ── SAVING_MONTHLY (last 13 months) ──────────────────────────────
    if len(psavert) >= MONTHLY_TREND_WINDOW:
        monthly = sorted(psavert[:MONTHLY_TREND_WINDOW], key=lambda x: x['date'])  # oldest-first for chart
        m_labels = [_month_lbl(o['date']) for o in monthly]
        m_values = [round(o['value'], 1) for o in monthly]
        html = _inject_const(html, 'SAVING_MONTHLY', {'labels': m_labels, 'data': m_values})

    # ── UMCSENT_MONTHLY (last 13 months) ────────────────────────────
    # statuses[] parallels data[]: 'preliminary' (UMich (P) flag) or 'final'.
    # Chart uses the last entry's status to render a PRELIM badge.
    umcsent = data.get('umcsent', [])
    if len(umcsent) >= MONTHLY_TREND_WINDOW:
        monthly = sorted(umcsent[:MONTHLY_TREND_WINDOW], key=lambda x: x['date'])  # oldest-first for chart
        m_labels = [_month_lbl(o['date']) for o in monthly]
        m_values = [round(o['value'], 1) for o in monthly]
        m_statuses = [o.get('status', 'final') for o in monthly]
        html = _inject_const(html, 'UMCSENT_MONTHLY',
                             {'labels': m_labels, 'data': m_values, 'statuses': m_statuses})

    # ── GDP_TOTAL_DATA ────────────────────────────────────────────────
    # Prefer vintage-pinned real + nominal GDP for historical stability (see
    # METHODOLOGY.md §5). Both share the same pin date so the real/nominal
    # deflator math doesn't drift. Falls back to live-revised on either line
    # if its pinned fetch failed — chart never goes blank.
    gdpc1_pinned = data.get('gdpc1_annual_pinned', []) or []
    gdp_pinned   = data.get('gdp_annual_pinned',   []) or []
    gdpc1_a = gdpc1_pinned or data.get('gdpc1_annual', [])
    gdp_a   = gdp_pinned   or data.get('gdp_annual',   [])
    vintage_info = (data.get('vintages') or {}).get('gdpc1_annual') or {}
    gdp_vintage = {
        'pinned': bool(gdpc1_pinned and gdp_pinned),
        'pin_date': vintage_info.get('pin_date'),
        'refresh': vintage_info.get('refresh_cadence'),
    }
    html = _inject_const(html, 'GDP_VINTAGE_INFO', gdp_vintage)
    if gdpc1_a and gdp_a:
        r_labels, r_values = _annual_from_freq(gdpc1_a, precision=1, scale=0.001)
        n_labels, n_values = _annual_from_freq(gdp_a, precision=1, scale=0.001)
        common = [l for l in r_labels if l in n_labels]
        real = [r_values[r_labels.index(l)] for l in common]
        nominal = [n_values[n_labels.index(l)] for l in common]
        if common:
            html = _inject_const(html, 'GDP_TOTAL_DATA', {
                'labels': common, 'nominal': nominal, 'real': real})

    # ── FFR_DATA ──────────────────────────────────────────────────────
    ffr_a = data.get('fedfunds_annual', [])
    if ffr_a:
        labels, values = _annual_from_freq(ffr_a, precision=2)
        # Add forecast dots (null for historical, values for forecasts)
        dots = [None] * len(labels)
        # Append last actual year's dot
        if values:
            dots[-1] = values[-1]
        # Keep existing forecast entries
        for fc_label, fc_val in [('GS 26F', 3.25), ('JPM 26F', 3.75), ('MS 26F', 3.25)]:
            labels.append(fc_label)
            values.append(None)
            dots.append(fc_val)
        if labels:
            html = _inject_const(html, 'FFR_DATA', {
                'labels': labels, 'actual': values, 'dots': dots})

    # ── MORTGAGE_DATA ─────────────────────────────────────────────────
    mtg_a = data.get('mortgage30_annual', [])
    if mtg_a and ffr_a:
        m_labels, m_values = _annual_from_freq(mtg_a, precision=2)
        f_labels, f_values = _annual_from_freq(ffr_a, precision=2)
        common = [l for l in m_labels if l in f_labels]
        rate30 = [m_values[m_labels.index(l)] for l in common]
        ffr = [f_values[f_labels.index(l)] for l in common]
        # Add forecast (dynamic year)
        _fc_yr = str(datetime.date.today().year + 1) + 'F'
        if common and common[-1] != _fc_yr:
            common.append(_fc_yr)
            rate30.append(6.0)
            ffr.append(3.75)
        if common:
            html = _inject_const(html, 'MORTGAGE_DATA', {
                'labels': common, 'rate30': rate30, 'ffr': ffr})

    # ── STARTS_DATA ───────────────────────────────────────────────────
    houst = data.get('houst', [])
    houst1f = data.get('houst1f', [])
    if len(houst) >= 60 and len(houst1f) >= 60:
        t_labels, t_values = _annual_avg(houst)
        s_labels, s_values = _annual_avg(houst1f)
        common = [l for l in t_labels if l in s_labels]
        sf = [round(s_values[s_labels.index(l)]) for l in common]
        mf = [round(t_values[t_labels.index(l)] - s_values[s_labels.index(l)]) for l in common]
        if common:
            html = _inject_const(html, 'STARTS_DATA', {
                'labels': common, 'sf': sf, 'mf': mf})

    # ── HPI_DATA ──────────────────────────────────────────────────────
    cs_hpi = data.get('cs_hpi', [])
    if len(cs_hpi) >= 60:
        # Use annual averages of monthly Case-Shiller index
        labels, values = _annual_avg(cs_hpi)
        cs = [round(v) for v in values]
        # Approximate FHFA as CS * 1.03 (close historical ratio)
        fhfa = [round(v * 1.03) for v in values]
        if labels:
            html = _inject_const(html, 'HPI_DATA', {
                'labels': labels, 'cs': cs, 'fhfa': fhfa})

    # ── CPI_MONTHLY (rolling 12-month YoY from index data) ────────────
    cpi_all_m = data.get('cpi_all', [])
    cpi_core_m = data.get('cpi_core', [])
    if len(cpi_all_m) >= 25 and len(cpi_core_m) >= 25:
        h_labels, h_values = _monthly_yoy_series(cpi_all_m, MONTHLY_TREND_WINDOW)
        c_labels, c_values = _monthly_yoy_series(cpi_core_m, MONTHLY_TREND_WINDOW)
        # Align to same labels (they should match)
        if h_labels and h_labels == c_labels:
            html = _inject_const(html, 'CPI_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values})
        elif h_labels:
            html = _inject_const(html, 'CPI_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values[:len(h_values)]})

    # ── PCE_MONTHLY (rolling 12-month YoY from index data) ────────────
    pce_m = data.get('pce', [])
    pce_core_m = data.get('pce_core', [])
    if len(pce_m) >= 25 and len(pce_core_m) >= 25:
        h_labels, h_values = _monthly_yoy_series(pce_m, MONTHLY_TREND_WINDOW)
        c_labels, c_values = _monthly_yoy_series(pce_core_m, MONTHLY_TREND_WINDOW)
        if h_labels and h_labels == c_labels:
            html = _inject_const(html, 'PCE_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values})
        elif h_labels:
            html = _inject_const(html, 'PCE_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values[:len(h_values)]})

    # ── WAGE_MONTHLY (last 13 months) ───────────────────────────────
    # Source: Atlanta Fed Wage Growth Tracker 3MMA (FRBATLWGT3MMAUMHWGO);
    # value is already a YoY %. Real = nominal − CPI YoY for the same month.
    atl_wgt_m = data.get('wage_growth_atl', [])
    cpi_all_m = data.get('cpi_all', [])
    if len(atl_wgt_m) >= MONTHLY_TREND_WINDOW and len(cpi_all_m) >= MONTHLY_TREND_WINDOW + 12:
        cpi_by_ym = {(int(o['date'][:4]), int(o['date'][5:7])): o['value']
                     for o in cpi_all_m}
        labels_w, nom_w, real_w = [], [], []
        for obs in reversed(atl_wgt_m[:MONTHLY_TREND_WINDOW]):  # newest-first → reverse to oldest-first
            d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
            nom = round(obs['value'], 1)
            cpi_now = cpi_by_ym.get((d.year, d.month))
            cpi_prev = cpi_by_ym.get((d.year - 1, d.month))
            real = round(nom - (cpi_now - cpi_prev) / cpi_prev * 100, 1) \
                   if cpi_now and cpi_prev else None
            labels_w.append(d.strftime("%b'%y"))
            nom_w.append(nom)
            real_w.append(real)
        if labels_w:
            html = _inject_const(html, 'WAGE_MONTHLY', {
                'labels': labels_w, 'nominal': nom_w, 'real': real_w})

    # ── U_MONTHLY (rolling 13-month unemployment rate) ────────────────
    unrate_m = data.get('unrate', [])
    if len(unrate_m) >= MONTHLY_TREND_WINDOW:
        # Unemployment rate is already a rate, not an index — no YoY needed
        labels_u, values_u = [], []
        for i in range(min(MONTHLY_TREND_WINDOW, len(unrate_m))):
            obs = unrate_m[i]
            d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
            labels_u.append(d.strftime("%b'%y"))
            values_u.append(round(obs['value'], 1))
        labels_u.reverse()
        values_u.reverse()
        if labels_u:
            html = _inject_const(html, 'U_MONTHLY', {
                'labels': labels_u, 'data': values_u})

    # ── HOUSING_MONTHLY (Case-Shiller YoY + monthly mortgage avg) ─────
    cs_hpi_m = data.get('cs_hpi', [])
    mortgage30_m = data.get('mortgage30', [])
    if len(cs_hpi_m) >= 25:
        cs_labels, cs_values = _monthly_yoy_series(cs_hpi_m, MONTHLY_TREND_WINDOW)
        # Get monthly-averaged mortgage rates
        mtg_labels, mtg_values = _monthly_avg_by_month(mortgage30_m, MONTHLY_TREND_WINDOW)
        # Align to Case-Shiller labels (CS has pub lag, mortgage is more current)
        if cs_labels:
            # Use CS labels as base; fill mortgage where available
            mtg_by_lbl = dict(zip(mtg_labels, mtg_values))
            # If CS is shorter than mortgage, extend with mortgage-only months
            extra_mtg_labels = [l for l in mtg_labels if l not in cs_labels]
            combined_labels = cs_labels + extra_mtg_labels
            combined_cs = cs_values + [cs_values[-1]] * len(extra_mtg_labels)
            combined_mtg = [mtg_by_lbl.get(l, None) for l in cs_labels] + \
                           [mtg_by_lbl[l] for l in extra_mtg_labels]
            # Filter out entries where mortgage is None (alignment gap)
            all_labels, all_cs, all_mtg = [], [], []
            for lb, cs, mt in zip(combined_labels, combined_cs, combined_mtg):
                if mt is not None:
                    all_labels.append(lb)
                    all_cs.append(cs)
                    all_mtg.append(mt)
            html = _inject_const(html, 'HOUSING_MONTHLY', {
                'labels': all_labels,
                'caseShiller': all_cs,
                'mortgage30': all_mtg})

    # ── SPREADS_DATA ──────────────────────────────────────────────────
    # OAS series are stored in FRED as percent (0.81 = 81 bps); chart uses
    # basis points throughout, so scale=100 on annual aggregation matches
    # the analyzer's *100 conversion for the latest scalar.
    ig_m = data.get('ig_oas_monthly', [])
    hy_m = data.get('hy_oas_monthly', [])
    if ig_m and hy_m:
        i_labels, i_values = _annual_avg_from_monthly(ig_m, precision=0, scale=100)
        h_labels, h_values = _annual_avg_from_monthly(hy_m, precision=0, scale=100)
        common = [l for l in i_labels if l in h_labels]
        ig = [int(i_values[i_labels.index(l)]) for l in common]
        hy = [int(h_values[h_labels.index(l)]) for l in common]
        ig_latest = data.get('ig_oas')
        hy_latest = data.get('hy_oas')
        if ig_latest and hy_latest:
            common.append(today.strftime("%b'%y"))
            ig.append(round(ig_latest.get('value', 0) * 100))
            hy.append(round(hy_latest.get('value', 0) * 100))
        if common:
            html = _inject_const(html, 'SPREADS_DATA', {
                'labels': common, 'ig': ig, 'hy': hy})

    # ── OIL_ANNUAL ────────────────────────────────────────────────────
    # All annual charts share the global START_YEAR — oil's "35-year history"
    # title now flows from the constant, no hardcoded year override needed.
    wti_a = data.get('wti_annual', [])
    brent_a = data.get('brent_annual', [])
    if wti_a and brent_a:
        w_labels, w_values = _annual_from_freq(wti_a, precision=1)
        b_labels, b_values = _annual_from_freq(brent_a, precision=1)
        common = [l for l in w_labels if l in b_labels]
        wti = [w_values[w_labels.index(l)] for l in common]
        brent = [b_values[b_labels.index(l)] for l in common]
        if common:
            html = _inject_const(html, 'OIL_ANNUAL', {
                'labels': common, 'wti': wti, 'brent': brent})

    # ── OIL_MONTHLY ───────────────────────────────────────────────────
    wti_m = data.get('wti_monthly', [])
    brent_m = data.get('brent_monthly', [])
    if wti_m and brent_m:
        # Build monthly chart from FRED monthly data
        wti_by_ym = {}
        for obs in wti_m:
            yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
            if yr >= START_YEAR:
                wti_by_ym[(yr, mo)] = obs['value']
        brent_by_ym = {}
        for obs in brent_m:
            yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
            if yr >= START_YEAR:
                brent_by_ym[(yr, mo)] = obs['value']
        # Only include months where both have data, exclude current partial month
        prior_end = today.replace(day=1) - datetime.timedelta(days=1)
        all_ym = sorted(set(wti_by_ym.keys()) & set(brent_by_ym.keys()))
        all_ym = [(y, m) for y, m in all_ym if (y, m) <= (prior_end.year, prior_end.month)]
        labels, wti_vals, brent_vals = [], [], []
        for yr, mo in all_ym:
            d = datetime.date(yr, mo, 1)
            # Label: "Jan'00" for first month of year, short month otherwise
            if mo == 1:
                labels.append(d.strftime("%b'%y"))
            else:
                labels.append(d.strftime('%b'))
            wti_vals.append(round(wti_by_ym[(yr, mo)], 1))
            brent_vals.append(round(brent_by_ym[(yr, mo)], 1))
        if labels:
            html = _inject_const(html, 'OIL_MONTHLY', {
                'labels': labels, 'wti': wti_vals, 'brent': brent_vals})

    # ── OIL_VS_CPI ────────────────────────────────────────────────────
    cpiengsl = data.get('cpiengsl', [])
    if wti_a and len(cpiengsl) >= 60:
        w_labels, w_values = _annual_from_freq(wti_a, precision=0)
        e_labels, e_values = _dec_yoy(cpiengsl)
        common = [l for l in w_labels if l in e_labels]
        wti = [w_values[w_labels.index(l)] for l in common]
        cpi_energy = [e_values[e_labels.index(l)] for l in common]
        if common:
            html = _inject_const(html, 'OIL_VS_CPI', {
                'labels': common, 'wti': wti, 'cpiEnergy': cpi_energy})

    # ── OIL_VS_SENTIMENT ──────────────────────────────────────────────
    umcsent_a = data.get('umcsent_annual', [])
    if wti_a and umcsent_a:
        w_labels, w_values = _annual_from_freq(wti_a, precision=0)
        s_labels, s_values = _annual_from_freq(umcsent_a, precision=1)
        common = [l for l in w_labels if l in s_labels]
        wti = [w_values[w_labels.index(l)] for l in common]
        sentiment = [s_values[s_labels.index(l)] for l in common]
        if common:
            html = _inject_const(html, 'OIL_VS_SENTIMENT', {
                'labels': common, 'wti': wti, 'sentiment': sentiment})

    # ── OIL_VS_HY ─────────────────────────────────────────────────────
    # hy_oas_monthly is in percent; chart wants basis points (scale=100).
    if wti_a and hy_m:
        w_labels, w_values = _annual_from_freq(wti_a, precision=0)
        h_labels, h_values = _annual_avg_from_monthly(hy_m, precision=0, scale=100)
        common = [l for l in w_labels if l in h_labels]
        wti = [w_values[w_labels.index(l)] for l in common]
        hy_spreads = [int(h_values[h_labels.index(l)]) for l in common]
        if common:
            html = _inject_const(html, 'OIL_VS_HY', {
                'labels': common, 'wti': wti, 'hySpreads': hy_spreads})

    # ── CREDIT_GROWTH ─────────────────────────────────────────────────
    revolsl_a = data.get('revolsl_annual', [])
    nonrevsl_a = data.get('nonrevsl_annual', [])
    if revolsl_a and nonrevsl_a:
        r_vals = sorted(revolsl_a, key=lambda x: x['date'])
        n_vals = sorted(nonrevsl_a, key=lambda x: x['date'])
        r_by_yr = {int(o['date'][:4]): o['value'] for o in r_vals if int(o['date'][:4]) >= START_YEAR - 1}
        n_by_yr = {int(o['date'][:4]): o['value'] for o in n_vals if int(o['date'][:4]) >= START_YEAR - 1}
        labels, rev, nonrev = [], [], []
        for yr in sorted(set(r_by_yr) & set(n_by_yr)):
            if yr < START_YEAR or yr >= today.year:
                continue
            r_prev, n_prev = r_by_yr.get(yr - 1), n_by_yr.get(yr - 1)
            if r_prev and n_prev and r_prev != 0 and n_prev != 0:
                labels.append(str(yr))
                rev.append(round((r_by_yr[yr] - r_prev) / r_prev * 100, 1))
                nonrev.append(round((n_by_yr[yr] - n_prev) / n_prev * 100, 1))
        if labels:
            html = _inject_const(html, 'CREDIT_GROWTH', {
                'labels': labels, 'revolving': rev, 'nonrevolving': nonrev})

    # ── TDSP_HIST ────────────────────────────────────────────────────
    tdsp = data.get('tdsp', [])
    if tdsp and len(tdsp) >= 4:
        labels_t, values_t = [], []
        for obs in sorted(tdsp, key=lambda x: x['date']):
            yr = int(obs['date'][:4])
            if yr >= START_YEAR:
                qlbl = datetime.datetime.strptime(obs['date'], '%Y-%m-%d').strftime("%Y Q") + \
                       str((int(obs['date'][5:7]) - 1) // 3 + 1)
                labels_t.append(qlbl)
                values_t.append(round(obs['value'], 1))
        if labels_t:
            html = _inject_const(html, 'TDSP_HIST', {
                'labels': labels_t, 'data': values_t})

    # ── NFP_VS_ADP — BLS auto, ADP now auto via FRED NPPTTL ─────────
    # ADP source: FRED NPPTTL (Total Nonfarm Private, MoM change, SA, K).
    # NPPTTL is already a change series — values are monthly changes directly.
    # Fallback chain: NPPTTL (recent only) → prior state.json → inline HTML bootstrap (first run).
    # FRED NPPTTL discontinued 2022-05 — filter to obs within 18 months so stale
    # data does not crowd out the prior-state.json round-trip fallback.
    payems = data.get('payems', [])
    _nppttl_cutoff = (datetime.datetime.today() - datetime.timedelta(days=548)).strftime('%Y-%m-%d')
    adp_raw = [o for o in data.get('adp_nppttl', []) if o.get('date', '') >= _nppttl_cutoff]
    if payems and len(payems) >= 25:
        # Compute MoM changes for last 24 months (newest-first in source)
        months = list(reversed(payems[:25]))  # oldest-first, 25 obs → 24 MoM changes
        nfp_labels, nfp_bls = [], []
        for i in range(1, len(months)):
            lbl = datetime.datetime.strptime(months[i]['date'], '%Y-%m-%d').strftime("%b'%y")
            chg = round(months[i]['value'] - months[i-1]['value'])
            nfp_labels.append(lbl)
            nfp_bls.append(chg)
        if nfp_labels:
            # Update NFP_BLS_MOM (24-month history)
            payload = {'labels': nfp_labels, 'bls': nfp_bls}
            _api_writer.register('NFP_BLS_MOM', payload)
            pattern = r'(?:const|let|var)\s+NFP_BLS_MOM\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
            new_html, n = re.subn(pattern, 'let NFP_BLS_MOM = null;', html, count=1)
            _record_subn_result('NFP_BLS_MOM', pattern, n)
            if n:
                applied.append(f'NFP_BLS_MOM registered to state.json ({len(nfp_labels)} months); inline zeroed')
                html = new_html

            bls_12 = nfp_bls[-MONTHLY_TREND_WINDOW:]
            lbl_12 = nfp_labels[-MONTHLY_TREND_WINDOW:]

            # Manually-verified ADP monthly changes (K) from ADP press releases.
            # Patches None slots after the fallback chain resolves — update when
            # new reports publish. Source: https://mediacenter.adp.com
            _ADP_VERIFIED = {
                "Mar'26": 62,   # Released 2026-04-01
                "Apr'26": 109,  # Released 2026-05-06
            }

            # Build ADP array — preference order:
            # 1. FRED NPPTTL (auto, current) — index values directly (already MoM changes)
            # 2. Prior state.json (round-trip, one run behind)
            # 3. Bootstrap inline HTML scrape (first run only)
            adp_arr = None
            if adp_raw and len(adp_raw) >= 1:
                adp_by_lbl = {
                    datetime.datetime.strptime(o['date'], '%Y-%m-%d').strftime("%b'%y"): round(o['value'])
                    for o in adp_raw
                }
                adp_arr = [adp_by_lbl.get(l) for l in lbl_12]  # None where ADP not yet published
                applied.append(f'NFP_VS_ADP — ADP auto-NPPTTL ({sum(1 for v in adp_arr if v is not None)}/{len(adp_arr)} months)')
            else:
                prior_nva = _api_writer.read_prior('NFP_VS_ADP')
                if isinstance(prior_nva, dict) and isinstance(prior_nva.get('adp'), list):
                    adp_arr = prior_nva['adp']
                else:
                    # Bootstrap: scrape inline HTML (first run only — Tier 1 migrated to null)
                    adp_match = re.search(r'(?:const|let|var)\s+NFP_VS_ADP\s*=\s*\{[^}]*adp:\s*\[([^\]]*)\]', html)
                    if adp_match:
                        try:
                            adp_arr = json.loads('[' + adp_match.group(1).strip() + ']')
                        except json.JSONDecodeError:
                            adp_arr = None

            # Final fallback: NPPTTL discontinued 2022-05, prior state.json
            # missing, and inline placeholder is now `null` — all three
            # fallbacks exhausted. Initialize to Nones so _ADP_VERIFIED
            # patches and adp_latest can still write the most recent months.
            # Without this, NFP_VS_ADP is never registered → buildJobsTab()
            # null-guard fires → all 4 charts blank with zero error signal.
            if adp_arr is None:
                adp_arr = [None] * len(lbl_12)
                applied.append('NFP_VS_ADP — cold-start bootstrap (NPPTTL stale/missing; using _ADP_VERIFIED + adp_latest)')

            if adp_arr is not None:
                # Patch None slots with manually-verified bootstrap values
                adp_arr = [_ADP_VERIFIED.get(l, v) for l, v in zip(lbl_12, adp_arr)]
                # Apply live-scraped ADP value (adpemploymentreport.com/ner_production.json)
                # — overwrites any prior value for the current month with ground truth.
                adp_latest = data.get('adp_latest')
                if isinstance(adp_latest, dict) and adp_latest.get('label') in lbl_12:
                    _al_lbl = adp_latest['label']
                    _al_val = adp_latest['value']
                    adp_arr = [_al_val if l == _al_lbl else v for l, v in zip(lbl_12, adp_arr)]
                    applied.append(f'NFP_VS_ADP — ADP live ({_al_lbl}={_al_val:+}K from adpemploymentreport.com)')
                adp_aligned = adp_arr[-MONTHLY_TREND_WINDOW:] if not adp_raw else adp_arr
                payload_nva = {'labels': lbl_12, 'bls': bls_12, 'adp': adp_aligned}
                _api_writer.register('NFP_VS_ADP', payload_nva)
                pattern_vs = r'(?:const|let|var)\s+NFP_VS_ADP\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
                new_html2, n2 = re.subn(pattern_vs, 'let NFP_VS_ADP = null;', html, count=1)
                _record_subn_result('NFP_VS_ADP', pattern_vs, n2)
                if n2:
                    applied.append(f'NFP_VS_ADP registered to state.json ({len(bls_12)} months); inline zeroed')
                    html = new_html2

    # ── SECTOR_MOM (auto-rebuild from BLS sector data) ────────────
    bls_sectors = data.get('bls_sectors', {})
    # Map BLS CES series IDs to SECTOR_MOM sector names
    _SECTOR_CES = {
        'CES6562000001': 'Healthcare',
        'CES4200000001': 'Retail Trade',
        'CES9093000001': 'State & Local Govt',
        'CES6561000001': 'Education (Pvt)',
        'CES2000000001': 'Construction',
        'CES5500000001': 'Financial Activities',
        'CES1000000001': 'Mining & Energy',
        'CES5000000001': 'Information (Tech)',
        'CES4300000001': 'Transport & Warehousing',
        'CES7000000001': 'Leisure & Hospitality',
        'CES3000000001': 'Manufacturing',
        'CES6000000001': 'Prof. & Biz Services',
        'CES9091000001': 'Federal Government',
    }
    if bls_sectors:
        # Build MoM changes by sector for last 2 months
        sector_mom_data = {}
        for ces_id, sector_name in _SECTOR_CES.items():
            series = bls_sectors.get(ces_id, [])
            if len(series) >= 2:
                # BLS data is newest-first
                cur_val = round(float(series[0]['value']))
                prev_val = round(float(series[1]['value']))
                cur_period = series[0]['periodName'][:3].lower() + series[0]['year'][2:]
                prev_period = series[1]['periodName'][:3].lower() + series[1]['year'][2:]
                sector_mom_data[sector_name] = {
                    'cur_key': cur_period,
                    'prev_key': prev_period,
                    'cur_chg': cur_val - prev_val,
                }
                # Also compute prev MoM if 3+ observations
                if len(series) >= 3:
                    prev2_val = round(float(series[2]['value']))
                    sector_mom_data[sector_name]['prev_chg'] = prev_val - prev2_val

        # Build the SECTOR_MOM payload from BLS data + a sector-ordering
        # source. Order comes from prior state.json (round-trip); on a
        # cold run with no prior state, we bootstrap-scrape inline HTML.
        if sector_mom_data:
            sector_names = []
            prior_sm = _api_writer.read_prior('SECTOR_MOM')
            if isinstance(prior_sm, dict) and isinstance(prior_sm.get('sectors'), list):
                sector_names = list(prior_sm['sectors'])
            else:
                sectors_match = re.search(
                    r'(?:const|let|var)\s+SECTOR_MOM\s*=\s*\{[^}]*sectors:\s*\[([^\]]*)\]', html)
                if sectors_match:
                    import ast
                    try:
                        sector_names = ast.literal_eval('[' + sectors_match.group(1) + ']')
                    except Exception:
                        sector_names = []
            # Cold-start fallback: when both round-trip (no prior state.json
            # entry for SECTOR_MOM) and inline-scrape (placeholder is now
            # `let SECTOR_MOM = null;` so the regex above matches nothing)
            # come up empty, default to the canonical sector ordering from
            # the _SECTOR_CES dict. The dict's insertion order matches the
            # historical inline-literal ordering, so chart layout doesn't
            # shift on the first post-migration run.
            if not sector_names:
                sector_names = list(_SECTOR_CES.values())

            if sector_names:
                # Determine month keys from BLS data
                any_sector = next(iter(sector_mom_data.values()))
                cur_key = any_sector['cur_key']
                prev_key = any_sector.get('prev_key', cur_key)

                cur_vals = []
                prev_vals = []
                updated_count = 0
                for s in sector_names:
                    if s in sector_mom_data:
                        cur_vals.append(sector_mom_data[s]['cur_chg'])
                        prev_vals.append(sector_mom_data[s].get('prev_chg', 0))
                        updated_count += 1
                    else:
                        cur_vals.append(0)
                        prev_vals.append(0)

                if updated_count >= 10:  # Only rebuild if we have most sectors
                    payload_sm = {
                        'sectors': sector_names,
                        prev_key:  prev_vals,
                        cur_key:   cur_vals,
                    }
                    _api_writer.register('SECTOR_MOM', payload_sm)
                    pattern_sm = r'(?:const|let|var)\s+SECTOR_MOM\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
                    new_html3, n3 = re.subn(pattern_sm, 'let SECTOR_MOM = null;', html, count=1)
                    _record_subn_result('SECTOR_MOM', pattern_sm, n3)
                    if n3:
                        applied.append(f'SECTOR_MOM registered to state.json ({updated_count} sectors, {prev_key} & {cur_key}); inline zeroed')
                        html = new_html3

    # ── JOBS_SECTORS annual totals (auto-update latest year from BLS) ──
    if bls_sectors:
        today = datetime.date.today()
        prev_yr = today.year - 1
        yr_key = f'j{str(prev_yr)[2:]}'  # e.g. "j25" for 2025
        _SECTOR_JS_MAP = {
            'CES6562000001': 'Healthcare & Social Asst.',
            'CES7000000001': 'Leisure & Hospitality',
            'CES6000000001': 'Prof. & Biz Services',
            'CES9091000001': '→ Federal Government',
            'CES9093000001': '→ State & Local',
            'CES2000000001': 'Construction',
            'CES6561000001': 'Education (Private)',
            'CES5500000001': 'Financial Activities',
            'CES4200000001': 'Retail Trade',
            'CES4300000001': 'Transport & Warehousing',
            'CES3000000001': 'Manufacturing',
            'CES5000000001': 'Information (Tech)',
            'CES1000000001': 'Mining & Energy',
        }
        updated_sectors = 0
        for ces_id, sector_name in _SECTOR_JS_MAP.items():
            series = bls_sectors.get(ces_id, [])
            # Find Dec of prev_yr and Dec of year before that for annual change
            dec_cur, dec_prev = None, None
            for obs in series:
                yr = int(obs['year']) if 'year' in obs else int(obs['date'][:4])
                mo_name = obs.get('periodName', '')
                mo = int(obs['date'][5:7]) if 'date' in obs else (12 if mo_name == 'December' else 0)
                if yr == prev_yr and mo == 12:
                    dec_cur = round(float(obs['value']))
                elif yr == prev_yr - 1 and mo == 12:
                    dec_prev = round(float(obs['value']))
            if dec_cur is not None and dec_prev is not None:
                annual_chg = dec_cur - dec_prev
                # Update the specific sector's latest year value in JOBS_SECTORS
                esc_name = re.escape(sector_name)
                pat = rf'(\{{s:"{esc_name}"[^}}]*{re.escape(yr_key)}:)\s*-?\d+'
                new_html4, n4 = re.subn(pat, rf'\g<1>{annual_chg}', html, count=1)
                # NB: per-sector — a 0-match means this sector's JOBS_SECTORS
                # entry has drifted shape (or sector name changed). Each one
                # is its own failure record so the maintainer sees which.
                _record_subn_result(f'JOBS_SECTORS[{sector_name}].{yr_key}', pat, n4)
                if n4:
                    updated_sectors += 1
                    html = new_html4
        if updated_sectors:
            applied.append(f'JOBS_SECTORS.{yr_key} updated ({updated_sectors} sectors)')

    # ── FC_MACRO actuals (auto-update from FRED data) ─────────────────
    # FC_MACRO.actNN = [Real GDP %, Unemployment %, CPI %, Wage Growth %, FFR %]
    # Patches every actNN key found in the declaration so historical revisions
    # (BEA/BLS commonly revise prior-year prints) flow through automatically.
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

    def _fc_actuals_for_year(yr):
        """Return [GDP%, U%, CPI%, Wage%, FFR%] for calendar year `yr`, with
        None for any metric that lacks the required source data."""
        # Real GDP YoY % from chained-2017 dollar levels
        gdp = None
        if yr in gdp_by_yr and (yr - 1) in gdp_by_yr:
            gdp = round((gdp_by_yr[yr] - gdp_by_yr[yr - 1]) / gdp_by_yr[yr - 1] * 100, 1)
        # Unemployment rate, Dec of yr
        u = round(unrate_by_ym[(yr, 12)], 1) if (yr, 12) in unrate_by_ym else None
        # CPI Dec-over-Dec YoY
        cpi_dec, cpi_prev = cpi_by_ym.get((yr, 12)), cpi_by_ym.get((yr - 1, 12))
        cpi = round((cpi_dec - cpi_prev) / cpi_prev * 100, 1) if cpi_dec and cpi_prev else None
        # Wage growth, AHETPI Dec-over-Dec YoY
        ahe_dec, ahe_prev = ahe_by_ym.get((yr, 12)), ahe_by_ym.get((yr - 1, 12))
        wage = round((ahe_dec - ahe_prev) / ahe_prev * 100, 1) if ahe_dec and ahe_prev else None
        # FFR annual average
        ffr = round(ffr_by_yr[yr], 1) if yr in ffr_by_yr else None
        return [gdp, u, cpi, wage, ffr]

    # ── FC_MACRO capture + register to state.json (Tier 1 wave 3d) ─────
    # Strategy: load the parent object from read_prior() first (round-trip
    # against last run's state.json), fall back to inline-HTML scrape (only
    # works on the very first cold-start before placeholder takes over),
    # then fall back to hardcoded defaults so renderer never trips even on
    # a brand-new checkout. Then patch each actNN via _fc_actuals_for_year
    # using existing values as the per-metric backfill source, register
    # the full payload, and zero the inline declaration.
    _FC_DEFAULTS = {
        'labels': ["Real GDP %", "Unemployment %", "CPI Inflation %",
                   "Wage Growth %", "Fed Funds Rate %"],
        'act24': [2.8, 4.1, 2.9, 4.0, 5.1],
        'act25': [2.1, 4.4, 2.7, 3.8, 4.2],
        'f26':   [2.2, 4.4, 2.9, 3.2, 3.9],
    }
    fc_payload = None
    prior_fc = _api_writer.read_prior('FC_MACRO')
    if isinstance(prior_fc, dict) and isinstance(prior_fc.get('labels'), list):
        fc_payload = {k: list(v) if isinstance(v, list) else v
                      for k, v in prior_fc.items()}
    else:
        fc_block_re = re.search(r'const\s+FC_MACRO\s*=\s*\{([^}]+)\}', html, re.DOTALL)
        if fc_block_re:
            fc_block = fc_block_re.group(1)
            labels_m = re.search(r'labels:\s*\[([^\]]+)\]', fc_block)
            if labels_m:
                import ast
                try:
                    fc_payload = {'labels': ast.literal_eval('[' + labels_m.group(1) + ']')}
                    for am in re.finditer(r'(act\d{2}|f\d{2}):\s*\[([^\]]+)\]', fc_block):
                        fc_payload[am.group(1)] = [float(v.strip()) for v in am.group(2).split(',')]
                except Exception:
                    fc_payload = None
    if not fc_payload:
        fc_payload = {k: (list(v) if isinstance(v, list) else v)
                      for k, v in _FC_DEFAULTS.items()}

    # Patch every actNN entry from FRED, preserving per-metric existing
    # values where the source data is insufficient.
    patched_keys = []
    for key in list(fc_payload.keys()):
        m = re.fullmatch(r'act(\d{2})', key)
        if not m:
            continue
        yr = 2000 + int(m.group(1))
        new_vals = _fc_actuals_for_year(yr)
        if sum(v is not None for v in new_vals) < 3:
            continue  # not enough data — leave seed alone
        existing_vals = fc_payload[key]
        final_vals = [new_vals[i] if i < len(new_vals) and new_vals[i] is not None
                      else (existing_vals[i] if i < len(existing_vals) else None)
                      for i in range(max(len(new_vals), len(existing_vals)))]
        if final_vals != existing_vals:
            fc_payload[key] = final_vals
            patched_keys.append(f'{key}={final_vals}')

    _api_writer.register('FC_MACRO', fc_payload)
    pattern_fc = r'(?:const|let|var)\s+FC_MACRO\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html5, n5 = re.subn(pattern_fc, 'let FC_MACRO = null;', html, count=1)
    _record_subn_result('FC_MACRO', pattern_fc, n5)
    if n5:
        suffix = f' (patched {", ".join(patched_keys)})' if patched_keys else ''
        applied.append(f'FC_MACRO registered to state.json{suffix}; inline zeroed')
        html = new_html5

    # ── Oil tile values (auto-update from OIL_ANNUAL data) ────────────
    wti_a = data.get('wti_annual', [])
    brent_a = data.get('brent_annual', [])
    prev_yr = datetime.date.today().year - 1
    wti_prev_avg = None
    brent_prev_avg = None
    for obs in (wti_a if isinstance(wti_a, list) else []):
        if int(obs['date'][:4]) == prev_yr:
            wti_prev_avg = round(obs['value'], 1)
    for obs in (brent_a if isinstance(brent_a, list) else []):
        if int(obs['date'][:4]) == prev_yr:
            brent_prev_avg = round(obs['value'], 1)
    if wti_prev_avg is not None:
        # Update "Full Year YYYY Avg" tile value
        pat_wti_tile = rf'(lbl:"Full Year {prev_yr} Avg"[^}}]*val:")(\$[\d.]+)(")'
        new_html6, n6 = re.subn(pat_wti_tile, rf'\g<1>${wti_prev_avg}\3', html, count=1)
        _record_subn_result(f'Oil tile WTI {prev_yr} avg', pat_wti_tile, n6)
        if n6:
            applied.append(f'Oil tile WTI {prev_yr} avg → ${wti_prev_avg}')
            html = new_html6
    if brent_prev_avg is not None:
        pat_brent_tile = rf'(lbl:"Brent {prev_yr} Avg"[^}}]*val:")(\$[\d.]+)(")'
        new_html7, n7 = re.subn(pat_brent_tile, rf'\g<1>${brent_prev_avg}\3', html, count=1)
        _record_subn_result(f'Oil tile Brent {prev_yr} avg', pat_brent_tile, n7)
        if n7:
            applied.append(f'Oil tile Brent {prev_yr} avg → ${brent_prev_avg}')
            html = new_html7

    # ── Category MoM auto-rebuilders ─────────────────────────────────
    html = rebuild_u_sector_mom(html, data)
    html = rebuild_cpi_cat_mom(html, data)
    html = rebuild_pce_cat_mom(html, data)
    html = rebuild_treasury_data(html, data)
    html = rebuild_oil_prod_spread(html, data)
    html = rebuild_fed_liquidity_data(html, data)
    html = rebuild_jolts_data(html, data)
    html = rebuild_cpi_breadth(html, data)
    html = rebuild_fiscal_data(html, data)

    return html


# ── HELPERS ───────────────────────────────────────────────────────────

def patch_array_last(html, js_key, new_val, precision=2, scope_var=None):
    fmt = str(round(new_val, precision)) if new_val is not None else 'null'
    # If scope_var is given, only patch within that variable's declaration
    if scope_var:
        var_pat = rf'((?:const|let|var)\s+{re.escape(scope_var)}\s*=\s*)'
        m = re.search(var_pat, html)
        if not m:
            errors.append(f'patch_array_last: scope var {scope_var} not found')
            return html
        start = m.start()
        end = html.find(';', start)
        if end < 0: end = len(html)
        chunk = html[start:end + 1]
        pattern = rf'("?{re.escape(js_key)}"?:\s*\[[^\]]*,\s*)[\d\.\-]+((\s*)\])'
        new_chunk, n = re.subn(pattern, rf'\g<1>{fmt}\g<3>]', chunk, count=1, flags=re.DOTALL)
        if not n:
            pattern2 = rf'("?{re.escape(js_key)}"?:\s*\[[^\]]*,\s*)[\d\.\-]+(\s*,\s*(?:null\s*,?\s*)*\])'
            new_chunk, n = re.subn(pattern2, rf'\g<1>{fmt}\2', chunk, count=1, flags=re.DOTALL)
        # Record AFTER fallback so a primary miss that the fallback recovers
        # doesn't pollute zero_replacement_errors. Only persistent misses count.
        _record_subn_result(f'patch_array_last[{scope_var}.{js_key}]', pattern, n)
        if n:
            applied.append(f'{scope_var}.{js_key}[-1]={fmt}')
            return html[:start] + new_chunk + html[end + 1:]
        else:
            errors.append(f'patch_array_last: {js_key} not found in {scope_var}')
            return html
    # Match both unquoted JS keys (key: [...]) and quoted JSON keys ("key":[...])
    # First try: replace last numeric value before ]
    pattern = rf'("?{re.escape(js_key)}"?:\s*\[[^\]]*,\s*)[\d\.\-]+((\s*)\])'
    new_html, n = re.subn(pattern, rf'\g<1>{fmt}\g<3>]', html, count=1, flags=re.DOTALL)
    if not n:
        # Second try: last numeric value before trailing nulls and ]
        pattern2 = rf'("?{re.escape(js_key)}"?:\s*\[[^\]]*,\s*)[\d\.\-]+(\s*,\s*(?:null\s*,?\s*)*\])'
        new_html, n = re.subn(pattern2, rf'\g<1>{fmt}\2', html, count=1, flags=re.DOTALL)
    _record_subn_result(f'patch_array_last[{js_key}]', pattern, n)
    if n: applied.append(f'{js_key}[-1]={fmt}')
    else: errors.append(f'patch_array_last: {js_key} not found')
    return new_html


def patch_kpi(html, label, val, sub=None):
    # Pre-check: static {lbl:"…", val:"…"} KPI literals have largely migrated
    # to JS-driven construction (e.g. {lbl:"Real GDP "+yr, val:…} or
    # {lbl:"30yr Mortgage May'26"+_hLbl, val:_hMortLatest+"%"}). The regex
    # below requires BOTH a quoted lbl and a quoted val — if either is a JS
    # expression (string concatenation, identifier), it can't be patched.
    # When the static `{lbl:"<label>" … val:"` shape isn't present, skip
    # entirely so the zero-replacement audit doesn't flag it. Data still
    # flows via patch_array_last → JS runtime computation on the live tile.
    _precheck_pat = re.compile(rf'\{{lbl:"{re.escape(label)}"[^}}]*val:"')
    if not _precheck_pat.search(html):
        warnings.append(f'patch_kpi: "{label}" not in static KPI list (JS-driven label, skipped)')
        return html
    pat = rf'(\{{lbl:"{re.escape(label)}"[^}}]*?val:")[^"]*(")'
    new_html, n = re.subn(pat, rf'\g<1>{val}\2', html)
    _record_subn_result(f'patch_kpi[{label}].val', pat, n)
    if n:
        applied.append(f'kpi.{label}={val}')
        if sub:
            pat2 = rf'(lbl:"{re.escape(label)}"[^}}]*?sub:")[^"]*(")'
            new_html, n2 = re.subn(pat2, rf'\g<1>{sub}\2', new_html)
            _record_subn_result(f'patch_kpi[{label}].sub', pat2, n2)
    else:
        errors.append(f'patch_kpi: "{label}" not found')
    return new_html


def patch_kpi_full(html, old_label, new_label, val, sub=None):
    """Update both the label text AND value of a KPI card in one pass.

    NOTE: as of the JS-driven KPI refactor, most call sites operate on
    legacy static labels that no longer exist in the HTML. When neither
    the exact nor fuzzy base appears anywhere in the HTML, skip silently
    (data flows through patch_array_last → JS runtime computation).
    """
    base = re.split(r'\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})', old_label)[0].strip()
    # Pre-check: if neither the exact label nor any base-prefix variant
    # exists in the HTML, this is a legacy JS-driven KPI — skip both the
    # rename regex and the value patch so the zero-replacement audit
    # doesn't flag it as a silent injection failure.
    exact_present = f'{{lbl:"{old_label}"' in html
    base_present = bool(base) and len(base) > 3 and f'{{lbl:"{base}' in html
    if not exact_present and not base_present:
        warnings.append(
            f'patch_kpi_full: "{old_label}" not in static KPI list '
            f'(JS-driven label, skipped)')
        return html
    # Extract base prefix (e.g. "Core PCE" from "Core PCE Dec 2025")
    # Try exact match first, then fuzzy match on base prefix
    pat = rf'(\{{lbl:"){re.escape(old_label)}(")'
    new_html, n = re.subn(pat, rf'\g<1>{new_label}\2', html)
    if not n:
        # Fuzzy: match any label starting with the same base words
        # e.g. "Core PCE Dec 2025" base = "Core PCE" matches "Core PCE Dec'25"
        if base and len(base) > 3:
            fuzzy_pat = rf'(\{{lbl:"){re.escape(base)}[^"]*(")'
            new_html, n = re.subn(fuzzy_pat, rf'\g<1>{new_label}\2', html, count=1)
    # Record once at the end — fuzzy fallback may rescue the exact-miss, so
    # we only count terminal failures.
    _record_subn_result(f'patch_kpi_full[{old_label}->{new_label}]', pat, n)
    if n:
        applied.append(f'kpi.rename → "{new_label}"')
    # Then patch the value using the new label
    return patch_kpi(new_html, new_label, val, sub)


def patch_commentary(html, tab_id, text):
    marker = f'id="commentary-{tab_id}"'
    if marker not in html: return html
    pat = rf'({re.escape(marker)}[^>]*>)(.*?)(</div>)'
    new_html, n = re.subn(pat, rf'\g<1>{text}\g<3>', html, count=1, flags=re.DOTALL)
    _record_subn_result(f'patch_commentary[{tab_id}]', pat, n)
    if n: applied.append(f'commentary.{tab_id}')
    return new_html


def _patch_panel_legend_chips(html, panel_anchor, cur_label, prv_label):
    """Update the three month-token legend chips inside a single MoM panel.

    Scopes replacements to the ~1500 bytes after the anchor (a substring
    that uniquely identifies the panel title) so we don't bleed into other
    panels. Updates both the "<cur> accelerating/cooling/improved/worsened"
    chips and the prior-month baseline chip (purple swatch #8878B8bb).

    `panel_anchor` accepts either a single string OR a tuple of strings.
    Tuples are tried in order, first hit wins — same precedent as
    validator._PANEL_DATA_MAP. Pass (new_title, legacy_title) so that
    finding-first sweeps stay backwards-compatible during the transition.
    """
    anchors = (panel_anchor,) if isinstance(panel_anchor, str) else tuple(panel_anchor)
    idx = -1
    matched = None
    for a in anchors:
        idx = html.find(a)
        if idx >= 0:
            matched = a
            break
    if idx < 0:
        warnings.append(f'_patch_panel_legend_chips: none of {anchors!r} found')
        return html
    end = idx + 1500
    chunk = html[idx:end]
    # Current-month chips — phrasings vary by panel
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= accelerating)", cur_label, chunk)
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= cooling)", cur_label, chunk)
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= rate rose)", cur_label, chunk)
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= rate fell)", cur_label, chunk)
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= improved vs)", cur_label, chunk)
    chunk = re.sub(r"[A-Z][a-z]+'\d+(?= worsened vs)", cur_label, chunk)
    # Prior-month baseline chip (purple swatch with no trailing word)
    chunk = re.sub(
        r"(background:#8878B8bb;display:inline-block\"></span>)[A-Z][a-z]+'\d+",
        rf"\g<1>{prv_label}", chunk, count=1)
    return html[:idx] + chunk + html[end:]


def patch_var_last_label(html, var_name, new_label):
    idx = html.find(f'const {var_name} =')
    if idx < 0: idx = html.find(f'let {var_name} =')
    if idx < 0: errors.append(f'patch_var_last_label: {var_name} not found'); return html
    # Use larger chunk to handle both compact JSON and formatted JS
    chunk = html[idx: idx + 2000]
    # Match both "labels": [...] (JSON) and labels: [...] (JS)
    new_chunk = re.sub(
        r'("?labels"?:\s*\[[^\]]*,\s*)"[^"]*"(\s*\])',
        rf'\1"{new_label}"\2', chunk, count=1, flags=re.DOTALL
    )
    if new_chunk == chunk:
        # Check if the label is already correct (not an error)
        if f'"{new_label}"]' in chunk or f"'{new_label}']" in chunk:
            applied.append(f'{var_name}.labels[-1] already={new_label}')
        else:
            errors.append(f'labels not found in {var_name}')
    else:
        applied.append(f'{var_name}.labels[-1]={new_label}')
    return html[:idx] + new_chunk + html[idx + 2000:]




def month_label(date_str):
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")


def inject_oil_daily(html, oil_daily):
    new_data = json.dumps(oil_daily, separators=(',', ':'))
    # Match both single-line {...}; and multi-line {...\n};
    oil_daily_pat = r'(const OIL_DAILY\s*=\s*)\{[^;]*\}(\s*;)'
    new_html, n = re.subn(
        oil_daily_pat,
        lambda m: m.group(1) + new_data + m.group(2),
        html, count=1, flags=re.DOTALL
    )
    _record_subn_result('OIL_DAILY', oil_daily_pat, n)
    if n:
        applied.append('OIL_DAILY (%d sessions, %s)' % (
            oil_daily.get('sessions', 0), oil_daily.get('month', '')))
    else:
        errors.append('inject_oil_daily: OIL_DAILY const not found')

    # Also patch the static panel title so it reflects the current month.
    # The finding-first sweep replaced the templated "<Month> <Year> — Daily
    # Closes (Live)" title with a static "Oil Supply Shock Tracker — Daily
    # Closes" (month moved to the panel-meta strip). If the legacy "(Live)"
    # sentinel isn't in the HTML, skip silently rather than logging a
    # zero-replacement audit failure.
    month = oil_daily.get('month', '')
    if month:
        if 'Daily Closes (Live)' not in new_html:
            warnings.append(
                'inject_oil_daily: panel title pattern not found '
                '(finding-first sweep moved month to panel-meta strip); skipped')
        else:
            panel_title_pat = r'(<div class="panel-title">)\w+ \d{4} — Daily Closes \(Live\)(</div>)'
            new_html, m = re.subn(
                panel_title_pat,
                lambda x: x.group(1) + month + ' — Daily Closes (Live)' + x.group(2),
                new_html, count=1
            )
            _record_subn_result('oil panel title', panel_title_pat, m)
            if m:
                applied.append('oil panel title → %s' % month)

    return new_html


# ── CATEGORY MoM AUTO-REBUILDERS ─────────────────────────────────────

def _yoy_from_index(series, n=2):
    """Compute YoY % for the latest n months from a CPI/PCE index series."""
    if not series or len(series) < 13:
        return []
    results = []
    for i in range(n):
        cur = series[i]
        cur_date = cur['date']
        target = f"{int(cur_date[:4])-1}{cur_date[4:]}"
        ya = next((o for o in series if o['date'] == target), None)
        if ya and ya['value']:
            yoy = round((cur['value'] - ya['value']) / ya['value'] * 100, 1)
            # Include 2-digit year so the chart's JS can render "Feb'26" without
            # hardcoding the year. Pass 3d already truncates to the first 3 chars.
            month_key = datetime.datetime.strptime(cur_date, '%Y-%m-%d').strftime('%b%y').lower()
            results.append({'month_key': month_key, 'yoy': yoy, 'date': cur_date})
    return results


def rebuild_u_sector_mom(html, data):
    """Rebuild U_SECTOR_MOM from BLS CPS sector unemployment data."""
    bls_unemp = data.get('bls_unemp_sectors', {})
    if not bls_unemp:
        warnings.append('U_SECTOR_MOM rebuild SKIPPED — bls_unemp_sectors missing from raw data')
        return html

    # BLS does not publish SA sector unemployment rates.
    # LNU04 (not seasonally adjusted) is the only available CPS series.
    # 11 sectors — Hotel/Lodging and Restaurants consolidated into Leisure & Hospitality.
    SECTOR_MAP = {
        'LNU04032231': 'Construction',
        'LNU04032232': 'Manufacturing',
        'LNU04032235': 'Wholesale & Retail Trade',
        'LNU04032236': 'Transport & Warehousing',
        'LNU04032237': 'Information/Tech',
        'LNU04032238': 'Financial Activities',
        'LNU04032239': 'Prof. & Biz Services',
        'LNU04032240': 'Healthcare & Education',
        'LNU04032241': 'Leisure & Hospitality',
        'LNU04032230': 'Agriculture & Mining',
        'LNU04028615': 'Government',
    }
    sector_names = list(SECTOR_MAP.values())

    # Extract latest 2 months from BLS data
    sector_data = {}
    for sid, sector_name in SECTOR_MAP.items():
        series = bls_unemp.get(sid, [])
        if len(series) >= 2:
            cur = series[0]
            prv = series[1]
            cur_key = cur['period'].lower().replace('m', '')
            cur_key = datetime.datetime.strptime(cur_key, '%m').strftime('%b').lower() + cur['year'][2:]
            prv_key = prv['period'].lower().replace('m', '')
            prv_key = datetime.datetime.strptime(prv_key, '%m').strftime('%b').lower() + prv['year'][2:]
            sector_data[sector_name] = {
                'cur_key': cur_key, 'prv_key': prv_key,
                'cur_val': float(cur['value']), 'prv_val': float(prv['value'])
            }

    if len(sector_data) >= 10:
        any_s = next(iter(sector_data.values()))
        cur_k = any_s['cur_key']
        prv_k = any_s['prv_key']
        cur_vals = [sector_data.get(s, {}).get('cur_val', 0) for s in sector_names]
        prv_vals = [sector_data.get(s, {}).get('prv_val', 0) for s in sector_names]

        # Tier 1 anti-clone: register payload to state.json, zero out inline literal.
        payload = {
            'sectors': sector_names,
            prv_k: prv_vals,
            cur_k: cur_vals,
        }
        _api_writer.register('U_SECTOR_MOM', payload)
        pattern = r'(?:const|let|var)\s+U_SECTOR_MOM\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
        new_html, n = re.subn(pattern, 'let U_SECTOR_MOM = null;', html, count=1)
        _record_subn_result('U_SECTOR_MOM', pattern, n)
        if n:
            applied.append(f'U_SECTOR_MOM registered to state.json ({len(sector_data)} sectors, {prv_k}/{cur_k}); inline zeroed')
            html = new_html

            # Patch static panel subtitle + legend HTML labels so they
            # always match the latest data month even before hydration.
            def _ulbl(k):
                import re as _re
                m2 = _re.match(r'^([a-z]{3})(\d{2})$', k)
                return (m2.group(1).capitalize() + "'" + m2.group(2)) if m2 else k
            cur_l = _ulbl(cur_k)
            prv_l = _ulbl(prv_k)
            _month_pat = r"[A-Z][a-z]+'?\d*"
            html = re.sub(
                r"(BLS CPS \xb7 )" + _month_pat + r" vs " + _month_pat,
                lambda m: m.group(1) + cur_l + ' vs ' + prv_l,
                html, count=1)
            html = re.sub(
                r">" + _month_pat + r" rate rose<",
                lambda m: '>' + cur_l + ' rate rose<', html, count=1)
            html = re.sub(
                r">" + _month_pat + r" rate fell<",
                lambda m: '>' + cur_l + ' rate fell<', html, count=1)
            html = re.sub(
                r'(background:#8878B8bb;display:inline-block"></span>)' + _month_pat + r'</span>',
                lambda m: m.group(1) + prv_l + '</span>', html, count=1)

    else:
        warnings.append(
            f'U_SECTOR_MOM rebuild SKIPPED — only {len(sector_data)}/11 sectors '
            f'had >=2 obs (need >=10). Chart will display stale data.'
        )

    return html


def rebuild_cpi_cat_mom(html, data):
    """Rebuild CPI_CAT_MOM from FRED CPI category index series."""
    CPI_CATS = [
        ('Shelter / Housing',   'cpi_shelter',   '#8878B8'),
        ('Food Away from Home', 'cpi_food_away', '#1A9E5A'),
        ('Transportation Svcs', 'cpi_transport', '#CC5DE8'),
        ('Medical Care Svcs',   'cpi_medical',   '#FF6B9D'),
        ('Core CPI (ex F&E)',   'cpi_core',      '#F76707'),
        ('Food at Home',        'cpi_food_home', '#51CF66'),
        ('New Vehicles',        'cpi_new_veh',   '#4DABF7'),
        ('Apparel',             'cpi_apparel',   '#FCC419'),
        ('Energy (all)',        'cpiengsl',      '#FFB84C'),
        ('Used Cars & Trucks',  'cpi_used_cars', '#00C9A7'),
    ]

    entries = []
    short = []
    for cat_name, data_key, color in CPI_CATS:
        series = data.get(data_key, [])
        yoys = _yoy_from_index(series, 2)
        if len(yoys) >= 2:
            entries.append({
                'cat': cat_name,
                yoys[1]['month_key']: yoys[1]['yoy'],  # prior month
                yoys[0]['month_key']: yoys[0]['yoy'],  # current month
                'color': color,
            })
        else:
            short.append(f'{data_key}(n={len(series)})')

    if len(entries) >= 8:
        # Tier 1 anti-clone: register to state.json, replace inline with null placeholder.
        _api_writer.register('CPI_CAT_MOM', entries)
        pattern = r'(?:const|let|var)\s+CPI_CAT_MOM\s*=\s*(?:\[[\s\S]*?\]|null)\s*;'
        new_html, n = re.subn(pattern, 'let CPI_CAT_MOM = null;', html, count=1)
        _record_subn_result('CPI_CAT_MOM', pattern, n)
        if n:
            keys = [k for k in entries[0] if k not in ('cat', 'color')]
            applied.append(f'CPI_CAT_MOM registered to state.json ({len(entries)} cats, {"/".join(keys)}); inline zeroed')
            html = new_html
    else:
        warnings.append(
            f'CPI_CAT_MOM rebuild SKIPPED — only {len(entries)}/10 cats had '
            f'>=13 obs for YoY (need >=8). Insufficient: {", ".join(short)}. '
            f'Chart will display stale Jan/Feb data while title auto-updates.'
        )

    return html


def rebuild_pce_cat_mom(html, data):
    """Rebuild PCE_CAT_MOM from the 4 top-level PCE component price-index
    series (Goods/Services/Food/Energy). BEA publishes these monthly; the
    detailed sub-category splits are quarterly only, which is why the chart
    used to silently skip — six of the prior IDs had no monthly equivalent."""
    PCE_CATS = [
        ('Goods',    'pce_goods'),
        ('Services', 'pce_services'),
        ('Food',     'pce_food'),
        ('Energy',   'pce_energy'),
    ]

    entries = []
    short = []
    for cat_name, data_key in PCE_CATS:
        series = data.get(data_key, [])
        yoys = _yoy_from_index(series, 2)
        if len(yoys) >= 2:
            entries.append({
                'cat': cat_name,
                yoys[1]['month_key']: yoys[1]['yoy'],
                yoys[0]['month_key']: yoys[0]['yoy'],
            })
        else:
            short.append(f'{data_key}(n={len(series)})')

    if len(entries) == len(PCE_CATS):
        # Tier 1 anti-clone: register to state.json, replace inline with null placeholder.
        _api_writer.register('PCE_CAT_MOM', entries)
        pattern = r'(?:const|let|var)\s+PCE_CAT_MOM\s*=\s*(?:\[[\s\S]*?\]|null)\s*;'
        new_html, n = re.subn(pattern, 'let PCE_CAT_MOM = null;', html, count=1)
        _record_subn_result('PCE_CAT_MOM', pattern, n)
        if n:
            keys = [k for k in entries[0] if k != 'cat']
            applied.append(f'PCE_CAT_MOM registered to state.json ({len(entries)} cats, {"/".join(keys)}); inline zeroed')
            html = new_html
    else:
        warnings.append(
            f'PCE_CAT_MOM rebuild SKIPPED — only {len(entries)}/{len(PCE_CATS)} '
            f'components had >=13 obs for YoY. Insufficient: {", ".join(short)}.'
        )

    return html


def rebuild_treasury_data(html, data):
    """Rebuild TREASURY_DATA with annual DGS10/DGS2 averages + latest daily."""
    dgs10_ann = data.get('dgs10_annual', [])
    dgs2_ann = data.get('dgs2_annual', [])
    if not dgs10_ann or not dgs2_ann:
        warnings.append('TREASURY_DATA rebuild SKIPPED — dgs10_annual/dgs2_annual missing')
        return html

    today = datetime.date.today()
    t10_labels, t10_vals = _annual_from_freq(dgs10_ann, precision=2)
    t2_labels, t2_vals = _annual_from_freq(dgs2_ann, precision=2)

    if not t10_labels:
        warnings.append('TREASURY_DATA rebuild SKIPPED — _annual_from_freq returned empty for DGS10')
        return html

    # Align to common years
    common = [l for l in t10_labels if l in t2_labels]
    dgs10 = [t10_vals[t10_labels.index(l)] for l in common]
    dgs2 = [t2_vals[t2_labels.index(l)] for l in common]
    spread = [round(a - b, 2) for a, b in zip(dgs10, dgs2)]

    # Add latest daily value
    dgs10_latest = data.get('dgs10')
    dgs2_latest = data.get('dgs2')
    if dgs10_latest and dgs2_latest:
        t10_val = dgs10_latest['value'] if isinstance(dgs10_latest, dict) else dgs10_latest
        t2_val = dgs2_latest['value'] if isinstance(dgs2_latest, dict) else dgs2_latest
        latest_lbl = month_label(datetime.date.today().strftime('%Y-%m-01'))
        common.append(latest_lbl)
        dgs10.append(round(t10_val, 2))
        dgs2.append(round(t2_val, 2))
        spread.append(round(t10_val - t2_val, 2))

    # Card 90+ DPD — compute annual averages from quarterly DRCCLACBS series
    # so the red line in the Treasury/Card chart actually renders. Previously
    # this field was preserved-from-HTML, which meant it stayed all-null after
    # the seed HTML shipped with nulls.
    cc_q = data.get('cc_delinq', [])
    by_yr = {}
    for obs in cc_q:
        yr = int(obs['date'][:4])
        by_yr.setdefault(yr, []).append(obs['value'])
    # Annual avg where we have at least 2 quarters; otherwise null (line breaks
    # cleanly rather than drawing through fabricated data).
    card90_by_yr = {str(yr): round(sum(vs) / len(vs), 2)
                    for yr, vs in by_yr.items() if len(vs) >= 2}
    latest_cc = cc_q[0]['value'] if cc_q else None
    card90 = []
    for lbl in common:
        if lbl in card90_by_yr:
            card90.append(card90_by_yr[lbl])
        elif '\'' in lbl and latest_cc is not None:
            # latest-month label (e.g. "Apr'26") — use most recent quarterly reading
            card90.append(round(latest_cc, 2))
        else:
            card90.append(None)

    obj = {'labels': common, 'dgs10': dgs10, 'dgs2': dgs2, 'spread': spread, 'card90': card90}
    # Tier 1 anti-clone: register payload to state.json, zero out inline literal.
    _api_writer.register('TREASURY_DATA', obj)
    pattern = r'(?:const|let|var)\s+TREASURY_DATA\s*=\s*(?:\{[^;]*\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let TREASURY_DATA = null;', html, count=1)
    _record_subn_result('TREASURY_DATA', pattern, n)
    if n:
        applied.append(f'TREASURY_DATA registered to state.json ({len(common)} points, latest {common[-1]}); inline zeroed')
        html = new_html
    return html


def rebuild_oil_prod_spread(html, data):
    """Rebuild OIL_SPREAD from existing annual WTI/Brent data."""
    wti_a = data.get('wti_annual', [])
    brent_a = data.get('brent_annual', [])
    if not wti_a or not brent_a:
        warnings.append('OIL_SPREAD rebuild SKIPPED — wti_annual/brent_annual missing')
        return html

    # OIL_SPREAD intentionally uses a shorter window than the global
    # START_YEAR — the WTI–Brent spread is structurally narrow before
    # ~2011 (pre-shale-boom) and including those years would compress
    # the recent regime visually. Hardcoded 2015 by design.
    w_labels, w_vals = _annual_from_freq(wti_a, start_year=2015, precision=1)
    b_labels, b_vals = _annual_from_freq(brent_a, start_year=2015, precision=1)
    common = [l for l in w_labels if l in b_labels]
    if not common:
        warnings.append('OIL_SPREAD rebuild SKIPPED — no overlapping years between WTI and Brent annual data')
        return html

    wti = [w_vals[w_labels.index(l)] for l in common]
    brent = [b_vals[b_labels.index(l)] for l in common]
    spread = [round(w - b, 1) for w, b in zip(wti, brent)]

    obj = {'labels': common, 'spread': spread}
    # Tier 1 anti-clone: register payload to state.json, zero out inline literal.
    _api_writer.register('OIL_SPREAD', obj)
    pattern = r'(?:const|let|var)\s+OIL_SPREAD\s*=\s*(?:\{[^;]*\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let OIL_SPREAD = null;', html, count=1)
    _record_subn_result('OIL_SPREAD', pattern, n)
    if n:
        applied.append(f'OIL_SPREAD registered to state.json ({len(common)} years); inline zeroed')
        html = new_html
    return html


def rebuild_fiscal_data(html, data):
    """Rebuild FISCAL_DATA (B3.2) from FYFSGDA188S (federal deficit / GDP, FY).

    Source: FRED FYFSGDA188S — fiscal-year Federal Surplus or Deficit as %
    of GDP. Annual series, OMB / Treasury original. Negative values = deficit.

    Output schema:
      labels: ['1965', '1966', ...]  — fiscal years from earliest obs onwards
      deficit_pct: [-1.2, -0.5, ...] — % of GDP per year
      latest_pct:  -6.4              — most recent FY value (number, not list)
      avg_post1965: -3.4             — simple mean from 1965 onwards (number)

    Hutchins fiscal impulse + CBO baseline are deferred to manual curation
    (data/fiscal_overrides.json) — not touched here. SKIP if deficit_gdp
    series is missing or empty.
    """
    series = data.get('deficit_gdp', [])
    if not series:
        warnings.append('FISCAL_DATA rebuild SKIPPED — deficit_gdp missing')
        return html

    by_date = {}
    for o in series:
        if isinstance(o, dict):
            d, v = o.get('date'), o.get('value')
        else:
            continue
        if d is None or v is None:
            continue
        by_date[d] = float(v)
    if not by_date:
        warnings.append('FISCAL_DATA rebuild SKIPPED — no usable rows in deficit_gdp')
        return html

    dates = sorted(by_date)
    labels = [d[:4] for d in dates]            # FY year only ("1965")
    vals = [round(by_date[d], 2) for d in dates]
    latest_pct = vals[-1]
    # Post-1965 average — defensive: index lookup may not find '1965' if the
    # series starts later, so fall back to the whole window.
    try:
        i65 = labels.index('1965')
        post65 = vals[i65:]
    except ValueError:
        post65 = vals
    avg_post1965 = round(sum(post65) / len(post65), 2) if post65 else None

    obj = {
        'labels': labels,
        'deficit_pct': vals,
        'latest_pct': latest_pct,
        'avg_post1965': avg_post1965,
    }
    _api_writer.register('FISCAL_DATA', obj)
    pattern = r'(?:const|let|var)\s+FISCAL_DATA\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let FISCAL_DATA = null;', html, count=1)
    _record_subn_result('FISCAL_DATA', pattern, n)
    if n:
        applied.append(f'FISCAL_DATA registered to state.json ({len(labels)} FY rows, latest FY{labels[-1]} {latest_pct:+.2f}%, post-1965 avg {avg_post1965:+.2f}%); inline zeroed')
        html = new_html
    else:
        warnings.append('FISCAL_DATA rebuild: const pattern not matched (HTML may already be on a newer schema)')
    return html


def rebuild_cpi_breadth(html, data):
    """Rebuild CPI_BREADTH (B3.3) — trimmed-mean / median CPI vs headline.

    Sources (collector.py):
      * cpi_trimmed (TRMMEANCPIM157SFRBCLE) — Cleveland Fed 16% trimmed-mean,
        raw 1-month percent change. Despite the M157 suffix in the FRED series
        ID, the published values are NOT annualised (empirically ~0.2-0.4%/mo).
        We annualise here to match headline.
      * cpi_median (MEDCPIM157SFRBCLE) — Cleveland Fed median, raw 1-month
        percent change. Same annualisation transform applied.
      * cpi_all (CPIAUCSL) — BLS headline CPI level. We compute MoM annualised
        as `((cur/prev)**12 - 1) * 100` to make all three lines comparable
        (annualised rate, not 12-month YoY).

    All three series align on monthly dates; we trim to the last 24 months
    of overlap. Missing trimmed/median → SKIP (we don't render headline alone).
    """
    trimmed = data.get('cpi_trimmed', [])
    median  = data.get('cpi_median', [])
    cpi_lvl = data.get('cpi_all', [])

    if not (trimmed and median and cpi_lvl):
        warnings.append('CPI_BREADTH rebuild SKIPPED — one or more of cpi_trimmed/cpi_median/cpi_all missing')
        return html

    def _by_date(series):
        out = {}
        for o in series:
            if isinstance(o, dict):
                d, v = o.get('date'), o.get('value')
            else:
                continue
            if d is None or v is None:
                continue
            out[d] = float(v)
        return out

    t = _by_date(trimmed)
    m = _by_date(median)
    c = _by_date(cpi_lvl)

    # Build headline MoM annualised from CPIAUCSL levels.
    c_dates = sorted(c)
    headline_mom = {}
    for i in range(1, len(c_dates)):
        prev, cur = c_dates[i-1], c_dates[i]
        if c[prev] > 0:
            headline_mom[cur] = ((c[cur] / c[prev]) ** 12 - 1) * 100.0

    common = sorted(set(t) & set(m) & set(headline_mom))
    if not common:
        warnings.append('CPI_BREADTH rebuild SKIPPED — no overlap across trimmed/median/headline-MoM')
        return html
    common = common[-24:]

    # Compound-annualise trimmed/median from raw MoM % so all three series
    # plot on the same y-axis. Headline is already annualised above.
    def _annualise(v):
        return ((1.0 + v / 100.0) ** 12 - 1.0) * 100.0

    labels = [month_label(d) for d in common]
    obj = {
        'labels': labels,
        'headline_mom_ann': [round(headline_mom[d], 2) for d in common],
        'trimmed':          [round(_annualise(t[d]), 2) for d in common],
        'median':           [round(_annualise(m[d]), 2) for d in common],
    }
    _api_writer.register('CPI_BREADTH', obj)
    pattern = r'(?:const|let|var)\s+CPI_BREADTH\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let CPI_BREADTH = null;', html, count=1)
    _record_subn_result('CPI_BREADTH', pattern, n)
    if n:
        applied.append(f'CPI_BREADTH registered to state.json ({len(common)} months, latest {common[-1]}, '
                       f'headline {obj["headline_mom_ann"][-1]:+.1f}% · trimmed {obj["trimmed"][-1]:+.1f}% · median {obj["median"][-1]:+.1f}%); inline zeroed')
        html = new_html
    else:
        warnings.append('CPI_BREADTH rebuild: const pattern not matched (HTML may already be on a newer schema)')
    return html


def rebuild_jolts_data(html, data):
    """Rebuild JOLTS_DATA (B3.1) from labour-market churn series.

    Sources (collector.py): jolts_hist (JTSJOL, openings), quits (JTSQUL),
    hires (JTSHIL), unemploy_hist (UNEMPLOY) — all BLS monthly, level in
    thousands SA, fetched as 24 obs. V/U ratio is computed in renderer
    (openings ÷ unemployed, in level terms — both are in thousands, so the
    quotient is dimensionless).

    Output schema: {labels, openings, hires, quits, vu} where labels are
    month strings ("Apr'26") and arrays are aligned by date. Missing any of
    the four series triggers SKIP rather than partial render.
    """
    openings = data.get('jolts_hist', [])
    quits    = data.get('quits', [])
    hires    = data.get('hires', [])
    unemp    = data.get('unemploy_hist', [])

    if not (openings and quits and hires and unemp):
        warnings.append('JOLTS_DATA rebuild SKIPPED — one or more of jolts_hist/quits/hires/unemploy_hist missing')
        return html

    def _by_date(series):
        out = {}
        for o in series:
            if isinstance(o, dict):
                d, v = o.get('date'), o.get('value')
            else:
                continue
            if d is None or v is None:
                continue
            out[d] = float(v)
        return out

    o = _by_date(openings)
    q = _by_date(quits)
    h = _by_date(hires)
    u = _by_date(unemp)

    common = sorted(set(o) & set(q) & set(h) & set(u))
    if not common:
        warnings.append('JOLTS_DATA rebuild SKIPPED — no overlapping dates across JOLTS + UNEMPLOY')
        return html

    # Keep at most the last 24 dates to match the panel's stated 24-month window.
    common = common[-24:]

    labels   = [month_label(d) for d in common]
    openings_arr = [round(o[d], 0) for d in common]
    quits_arr    = [round(q[d], 0) for d in common]
    hires_arr    = [round(h[d], 0) for d in common]
    # V/U: openings / unemployed. Guard against zero (theoretically impossible
    # for UNEMPLOY but defensive).
    vu = [round(o[d] / u[d], 2) if u[d] else None for d in common]

    obj = {
        'labels': labels,
        'openings': openings_arr,
        'quits': quits_arr,
        'hires': hires_arr,
        'vu': vu,
    }
    _api_writer.register('JOLTS_DATA', obj)
    pattern = r'(?:const|let|var)\s+JOLTS_DATA\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let JOLTS_DATA = null;', html, count=1)
    _record_subn_result('JOLTS_DATA', pattern, n)
    if n:
        applied.append(f'JOLTS_DATA registered to state.json ({len(common)} months, latest {common[-1]}, V/U {vu[-1]}); inline zeroed')
        html = new_html
    else:
        warnings.append('JOLTS_DATA rebuild: const pattern not matched (HTML may already be on a newer schema)')
    return html


def rebuild_fed_liquidity_data(html, data):
    """Rebuild FED_LIQUIDITY_DATA (B3.4) from weekly H.4.1 series.

    Sources (collector.py): walcl, wresbal, rrpontsyd, tga — all FRED weekly,
    units = $millions, fetched as 104 obs (~2 years). We convert to $bn for
    chart readability and align all four series on the common set of dates.

    Behaviour notes:
      * If any of the four series is missing, the rebuild SKIPS rather than
        rendering a partial chart — observability/playbook §X consistency.
      * Dates are kept as ISO YYYY-MM-DD on the wire; chart-side `maxTicksLimit`
        thins them for display so we don't pre-truncate here.
      * Provenance envelopes ({date,value,source,fetched_at}, B6.2) are
        unwrapped via the standard `o['value'] if isinstance(o, dict)` guard.
    """
    walcl   = data.get('walcl', [])
    wresbal = data.get('wresbal', [])
    rrp     = data.get('rrpontsyd', [])
    tga     = data.get('tga', [])

    if not (walcl and wresbal and rrp and tga):
        warnings.append('FED_LIQUIDITY_DATA rebuild SKIPPED — one or more of walcl/wresbal/rrpontsyd/tga missing')
        return html

    def _by_date(series):
        out = {}
        for o in series:
            if isinstance(o, dict):
                d, v = o.get('date'), o.get('value')
            else:
                continue
            if d is None or v is None:
                continue
            out[d] = float(v)
        return out

    a = _by_date(walcl)
    b = _by_date(wresbal)
    c = _by_date(rrp)
    d_ = _by_date(tga)

    common_dates = sorted(set(a) & set(b) & set(c) & set(d_))
    if not common_dates:
        warnings.append('FED_LIQUIDITY_DATA rebuild SKIPPED — no overlapping dates across the four series')
        return html

    # FRED H.4.1 values arrive in $millions; divide by 1000 → $bn.
    def _bn(v): return round(v / 1000.0, 1)

    obj = {
        'labels':    common_dates,
        'walcl':     [_bn(a[d]) for d in common_dates],
        'wresbal':   [_bn(b[d]) for d in common_dates],
        'rrpontsyd': [_bn(c[d]) for d in common_dates],
        'tga':       [_bn(d_[d]) for d in common_dates],
    }
    _api_writer.register('FED_LIQUIDITY_DATA', obj)
    pattern = r'(?:const|let|var)\s+FED_LIQUIDITY_DATA\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html, n = re.subn(pattern, 'let FED_LIQUIDITY_DATA = null;', html, count=1)
    _record_subn_result('FED_LIQUIDITY_DATA', pattern, n)
    if n:
        applied.append(f'FED_LIQUIDITY_DATA registered to state.json ({len(common_dates)} weeks, latest {common_dates[-1]}); inline zeroed')
        html = new_html
    else:
        warnings.append('FED_LIQUIDITY_DATA rebuild: const pattern not matched (HTML may already be on a newer schema)')
    return html


# ── SECTION RENDERERS ─────────────────────────────────────────────────

def render_rates(html, data, vals, tabs):
    ffr   = vals.get('ffr')
    dgs10 = vals.get('dgs10')
    dgs2  = vals.get('dgs2')
    spr   = vals.get('spread_10_2_bp')

    ffr_s   = data.get('ffr')
    dgs10_s = data.get('dgs10')
    if ffr is not None and ffr_s:
        html = patch_array_last(html, 'actual', ffr, 2)
        ffr_lbl = f"Fed Funds Rate ({month_label(ffr_s['date'])})"
        html = patch_kpi_full(html, "Fed Funds Rate (Jan '26)", ffr_lbl, f'{ffr:.2f}%')

    if dgs10 is not None and dgs10_s:
        t10_lbl = f"10Y Treasury {month_label(dgs10_s['date'])}"
        html = patch_kpi_full(html, '10Y Treasury Feb 2026', t10_lbl, f'{dgs10:.2f}%',
                         f"2Y: {dgs2:.2f}% · Spread: {spr:+d}bp" if dgs2 and spr else None)

    txt = tabs.get('yield', '')
    if txt: html = patch_commentary(html, 'yield', txt)
    return html


def render_spreads(html, data, vals, tabs):
    ig = vals.get('ig_oas')
    hy = vals.get('hy_oas')

    if ig is not None:
        html = patch_array_last(html, 'ig', round(ig), 0)
        # IG/HY OAS not in KPI strip — skip patch_kpi

    if hy is not None:
        html = patch_array_last(html, 'hy', round(hy), 0)

    if ig is not None:
        label = datetime.date.today().strftime("%b'%y")
        html = re.sub(
            r'(SPREADS_DATA\s*=\s*\{[^}]*?"?labels"?:\s*\[[^\]]*,\s*)"[^"]+"',
            rf'\1"{label}"', html, count=1, flags=re.DOTALL
        )

    txt = tabs.get('credit', '')
    if txt: html = patch_commentary(html, 'credit', txt)
    return html


def render_labor(html, data, vals, tabs):
    unrate = vals.get('unrate')
    u6     = vals.get('u6rate')
    nfp    = vals.get('nfp_mom')
    wages  = vals.get('wages_yoy')

    if unrate is not None:
        html = patch_array_last(html, 'data', unrate, 1, scope_var='U_MONTHLY')
        unemp_date = data.get('unrate', [{}])[0].get('date','') if data.get('unrate') else ''
        u_lbl = f"Unemployment {month_label(unemp_date)}" if unemp_date else 'Unemployment'
        html = patch_kpi_full(html, 'Unemployment 2025', u_lbl, f'{unrate:.1f}%')

    if u6 is not None:
        u6_date = data.get('u6rate', [{}])[0].get('date','') if data.get('u6rate') else ''
        u6_lbl = f"U-6 Broad Rate {month_label(u6_date)}" if u6_date else 'U-6 Broad Rate'
        html = patch_kpi_full(html, "U-6 Broad Rate Dec '25", u6_lbl, f'{u6:.1f}%')

    if nfp is not None:
        payems_s = data.get('payems')
        jobs_date = payems_s[0].get('date','') if payems_s else ''
        jobs_lbl = f"{month_label(jobs_date)} Jobs" if jobs_date else 'NFP Jobs'
        html = patch_kpi_full(html, 'Jan 2026 Jobs', jobs_lbl, f'{nfp:+.0f}K')

    if wages is not None:
        html = patch_array_last(html, 'nominal', wages, 1, scope_var='WAGE_MONTHLY')
        # Prefer Atlanta Fed WGT date when available; AHETPI fallback otherwise.
        atl = data.get('wage_growth_atl') or []
        fallback = data.get('ahetpi') or []
        wages_date = (atl[0] if atl else (fallback[0] if fallback else {})).get('date', '')
        wages_lbl = f"Nominal Wage Growth {month_label(wages_date)}" if wages_date else 'Nominal Wage Growth'
        html = patch_kpi_full(html, 'Nominal Wage Growth 2025', wages_lbl, f'{wages:+.1f}%')

    icsa_val = vals.get('icsa')
    if icsa_val is not None:
        icsa_s = data.get('icsa', [])
        icsa_date = icsa_s[0].get('date', '') if icsa_s else ''
        icsa_lbl = f"Initial Claims {month_label(icsa_date)}" if icsa_date else 'Initial Claims'
        html = patch_kpi_full(html, 'Initial Claims', icsa_lbl, f'{icsa_val/1000:.0f}K')

    # ── Auto-update Unemployment tab month references ──────────────
    # The Unemployment-by-Sector chart panel title/chips are gated on
    # rebuild_u_sector_mom succeeding (so the panel never advertises a
    # newer month than the data const carries). Commentary updates below
    # use unrate dates directly — they're not coupled to the sector chart.
    u_rebuilt = any(s.startswith('U_SECTOR_MOM rebuilt') for s in applied)
    unrate_s = data.get('unrate', [])
    if unrate_s and len(unrate_s) >= 2:
        u_cur_d = unrate_s[0].get('date', '')
        u_prv_d = unrate_s[1].get('date', '')
        if u_cur_d and u_prv_d:
            u_cur = month_label(u_cur_d)
            u_prv = month_label(u_prv_d)
            u_prv_short = u_prv.split("'")[0]
            if u_rebuilt:
                html = re.sub(
                    r"(Change in unemployment rate vs prior month · BLS CPS · )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+",
                    rf"\g<1>{u_cur} vs {u_prv}", html, count=1)
                # Tuple anchor — finding-first title first, legacy second (style_guide §23.1).
                html = _patch_panel_legend_chips(
                    html,
                    ('Unemployment is rising broadly across sectors',
                     'Unemployment by Sector — Monthly MoM Change (pp)'),
                    u_cur, u_prv)
                applied.append(f'Unemployment tab month refs updated to {u_prv}/{u_cur}')

            # ── Auto-patch commentary values when Agent 3 doesn't refresh ──
            u_cur_val = unrate_s[0].get('value')
            u_prv_val = unrate_s[1].get('value')
            u_cur_full = datetime.datetime.strptime(u_cur_d, '%Y-%m-%d').strftime('%b %Y')  # "Mar 2026"
            u_prv_full = datetime.datetime.strptime(u_prv_d, '%Y-%m-%d').strftime('%b %Y')  # "Feb 2026"
            if u_cur_val is not None and u_prv_val is not None:
                # Update "U-3 at <strong>X.X%</strong> (Mon YYYY)" in commentary
                html = re.sub(
                    r'(U-3 at <strong>)\d+\.\d+%</strong> \([A-Z][a-z]+ \d{4}\)',
                    rf'\g<1>{u_cur_val}%</strong> ({u_cur_full})',
                    html, count=1)
                # Update "up from X.X% in Mon" / "down from X.X% in Mon"
                direction = 'up' if u_cur_val > u_prv_val else 'down'
                html = re.sub(
                    r'(up|down) from \d+\.\d+% in [A-Z][a-z]+',
                    f'{direction} from {u_prv_val}% in {u_prv_full.split()[0]}',
                    html, count=1)
                applied.append(f'Commentary U-3 updated to {u_cur_val}% ({u_cur_full})')

            # Update NFP in commentary (e.g. "Feb payrolls printed <strong>-92K</strong>")
            if payems_s and len(payems_s) >= 2:
                nfp_change = round(payems_s[0]['value'] - payems_s[1]['value'])
                nfp_sign = '+' if nfp_change >= 0 else ''
                nfp_lbl = month_label(payems_s[0]['date']).split("'")[0]  # "Mar"
                # Replace "Mon payrolls printed <strong>XK</strong> — stale narrative."
                # Truncate up to next sentence boundary to remove stale context
                html = re.sub(
                    r'[A-Z][a-z]+ payrolls printed <strong>[^<]+</strong>[^<]*?(?=<strong>)',
                    f'{nfp_lbl} payrolls printed <strong>{nfp_sign}{nfp_change}K</strong>. ',
                    html, count=1)
                applied.append(f'Commentary NFP updated to {nfp_sign}{nfp_change}K ({nfp_lbl})')

            # Update weekly claims in commentary (e.g. "205K (Mar'26)")
            if icsa_s:
                icsa_v = round(float(icsa_s[0].get('value', 0)))
                # ICSA is in raw units (e.g. 205000), convert to K
                icsa_k = round(icsa_v / 1000) if icsa_v > 1000 else icsa_v
                icsa_d = icsa_s[0].get('date', '')
                if icsa_d:
                    icsa_ml = month_label(icsa_d)
                    html = re.sub(
                        r'at \d+K \([A-Z][a-z]+\'\d+\)',
                        f'at {icsa_k}K ({icsa_ml})',
                        html, count=1)

    # ── Auto-update Jobs tab month references ────────────────────────
    # The Jobs tab has hardcoded month names in titles, legends, and tiles.
    # Sector-chart updates are gated on SECTOR_MOM having been rebuilt this
    # run (rebuild_charts emits 'SECTOR_MOM rebuilt'). The Jobs metric tile
    # header rolls from PAYEMS unconditionally — it's not bound to the chart.
    sector_rebuilt = any(s.startswith('SECTOR_MOM rebuilt') for s in applied)
    payems_s = data.get('payems', [])
    if payems_s and len(payems_s) >= 2:
        cur_date = payems_s[0].get('date', '')
        prev_date = payems_s[1].get('date', '')
        if cur_date and prev_date:
            cur_lbl = month_label(cur_date)    # e.g. "Mar'26"
            prev_lbl = month_label(prev_date)  # e.g. "Feb'26"
            cur_upper = cur_lbl.upper()        # e.g. "MAR'26"

            if sector_rebuilt:
                # Update sector chart title and subtitle
                html = re.sub(
                    r'Monthly Job Change by Sector — [A-Z][a-z]+\'\d+ vs [A-Z][a-z]+\'\d+ \(thousands\)',
                    f"Monthly Job Change by Sector — {prev_lbl} vs {cur_lbl} (thousands)",
                    html, count=1)
                # Panel-sub now carries the month pair (Prv vs Cur · sorted by Cur)
                # to satisfy validator Pass 3d after finding-first title sweep.
                html = re.sub(
                    r"(BLS CES major sector breakdown · MoM net payroll change · )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+( · sorted by )[A-Z][a-z]+'\d+",
                    rf"\g<1>{prev_lbl} vs {cur_lbl}\g<2>{cur_lbl}", html, count=1)
                # Legacy-form fallback (in case any panel still uses the pre-sweep subtitle)
                html = re.sub(
                    r'(BLS CES major sector breakdown · month-over-month net payroll change · sorted by )[A-Z][a-z]+\'\d+',
                    rf'\g<1>{cur_lbl}', html, count=1)

                # Update sector legend labels (current-month + prior-month chips).
                # Tuple anchor — finding-first title first, legacy panel-sub fallback second.
                html = _patch_panel_legend_chips(
                    html,
                    ('Hiring is now concentrated in healthcare and leisure',
                     'Monthly Job Change by Sector'),
                    cur_lbl, prev_lbl)
                # The "improved/worsened vs Mon" trailing word is short month name
                short_prv = prev_lbl.split("'")[0]
                html = re.sub(
                    r"(improved vs )[A-Z][a-z]+", rf"\g<1>{short_prv}", html, count=1)
                html = re.sub(
                    r"(worsened vs )[A-Z][a-z]+", rf"\g<1>{short_prv}", html, count=1)

            # Update Jobs metric tile header
            html = re.sub(
                r"""FEB'26 JOBS""",
                f"{cur_upper} JOBS", html, count=1)

            # Update the metric tile value and subtitle
            if nfp is not None:
                html = re.sub(
                    r'(<div[^>]*class="panel-title[^"]*"[^>]*>📋 Jobs Market Commentary)',
                    r'\1', html, count=1)

            applied.append(f'Jobs tab month refs updated to {prev_lbl}/{cur_lbl}')

    for tab in ('jobs', 'unemp', 'wages'):
        txt = tabs.get(tab, '')
        if txt: html = patch_commentary(html, tab, txt)
    return html


def render_inflation(html, data, vals, tabs):
    cpi      = vals.get('cpi_yoy')
    core_cpi = vals.get('core_cpi_yoy')
    pce      = vals.get('pce_yoy')
    core_pce = vals.get('core_pce_yoy')
    save     = vals.get('saving_rate')

    if cpi is not None:
        html = patch_array_last(html, 'headline', cpi, 1, scope_var='CPI_MONTHLY')
        cpi_s2 = data.get('cpi_all')
        cpi_date = cpi_s2[0].get('date','') if cpi_s2 else ''
        cpi_lbl = f"CPI All Items {month_label(cpi_date)}" if cpi_date else 'CPI All Items'
        html = patch_kpi_full(html, 'CPI All Items 2025', cpi_lbl, f'{cpi:+.1f}%')

    if core_cpi is not None:
        html = patch_array_last(html, 'core', core_cpi, 1, scope_var='CPI_MONTHLY')

    if pce is not None:
        html = patch_array_last(html, 'headline', pce, 1, scope_var='PCE_MONTHLY')

    # Core PCE tile is fully dynamic — reads from PCE_MONTHLY.core at runtime
    # No patch_kpi needed; renderer updates the JS constant via patch_array_last above

    if save is not None:
        html = patch_array_last(html, 'data', save, 1, scope_var='SAVING_MONTHLY')

    # ── Auto-update CPI tab month references ────────────────────────
    # Gated on rebuild_cpi_cat_mom succeeding, so title and data always roll
    # together. If the rebuild was skipped (insufficient obs), title stays put
    # so it can't drift past the data const.
    cpi_rebuilt = any(s.startswith('CPI_CAT_MOM rebuilt') for s in applied)
    cpi_s = data.get('cpi_all', [])
    if cpi_rebuilt and cpi_s and len(cpi_s) >= 2:
        cpi_cur = cpi_s[0].get('date', '')
        cpi_prev = cpi_s[1].get('date', '')
        if cpi_cur and cpi_prev:
            c_cur = month_label(cpi_cur)
            c_prv = month_label(cpi_prev)
            c_prv_short = c_prv.split("'")[0]
            html = re.sub(
                r"CPI by Category — MoM Change \([A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+\)",
                f"CPI by Category — MoM Change ({c_cur} vs {c_prv})", html, count=1)
            html = re.sub(
                r"(YoY % by category · )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+( · sorted by )[A-Z][a-z]+'\d+",
                rf"\g<1>{c_cur} vs {c_prv}\g<2>{c_cur}", html, count=1)
            # Scope chip updates to the CPI by Category panel only — tuple anchor:
            # finding-first title first, legacy "CPI by Category" panel-sub as fallback.
            html = _patch_panel_legend_chips(
                html,
                ('Energy and transport categories are pulling the basket higher',
                 'CPI by Category'),
                c_cur, c_prv)
            html = re.sub(
                r"(Monthly YoY % change by category\. )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+",
                rf"\g<1>{c_cur} vs {c_prv}", html, count=1)
            applied.append(f'CPI tab month refs updated to {c_prv}/{c_cur}')

    # ── Auto-update PCE tab month references ────────────────────────
    # Gated on rebuild_pce_cat_mom succeeding so title and PCE_CAT_MOM
    # data const always roll together.
    pce_rebuilt = any(s.startswith('PCE_CAT_MOM rebuilt') for s in applied)
    pce_s = data.get('pce', [])
    if pce_rebuilt and pce_s and len(pce_s) >= 2:
        p_cur_d = pce_s[0].get('date', '')
        p_prv_d = pce_s[1].get('date', '')
        if p_cur_d and p_prv_d:
            p_cur = month_label(p_cur_d)
            p_prv = month_label(p_prv_d)
            html = re.sub(
                r"PCE by Component — YoY % \([A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+\)",
                f"PCE by Component — YoY % ({p_cur} vs {p_prv})", html, count=1)
            # Panel-sub now carries the month pair (Cur vs Prv · sorted by Cur)
            # post style_guide §23.1 sweep. Legacy single-token form kept as fallback.
            html = re.sub(
                r"(PCE chain-type price index by component · )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+( · sorted by )[A-Z][a-z]+'\d+",
                rf"\g<1>{p_cur} vs {p_prv}\g<2>{p_cur}", html, count=1)
            html = re.sub(
                r"(PCE chain-type price index by component · sorted by )[A-Z][a-z]+'\d+",
                rf"\g<1>{p_cur}", html, count=1)
            # Tuple anchor — finding-first title first, legacy panel-title as fallback.
            html = _patch_panel_legend_chips(
                html,
                ('Energy and housing components are pulling the PCE basket higher',
                 'PCE by Component — YoY %'),
                p_cur, p_prv)
            applied.append(f'PCE tab month refs updated to {p_prv}/{p_cur}')

    # ── Auto-patch PCE commentary numbers ────────────────────────────
    # Mirrors the U-3/NFP commentary patches in render_labor — keeps the
    # static prose current when Agent 3 (briefing) hasn't refreshed it.
    pce_core_s = data.get('pce_core', [])
    if pce_core_s and len(pce_core_s) >= 14:
        yoy_cur, yoy_prev = None, None
        # Reuse the same calendar-month YoY logic as rebuild_kpi_strip
        def _find_yoy(series, idx):
            if len(series) <= idx: return None
            d = datetime.datetime.strptime(series[idx]['date'], '%Y-%m-%d')
            for o in series:
                od = datetime.datetime.strptime(o['date'], '%Y-%m-%d')
                if od.year == d.year - 1 and od.month == d.month and o['value']:
                    return round((series[idx]['value'] - o['value']) / o['value'] * 100, 1)
            return None
        yoy_cur = _find_yoy(pce_core_s, 0)
        yoy_prev = _find_yoy(pce_core_s, 1)
        cur_full = datetime.datetime.strptime(pce_core_s[0]['date'], '%Y-%m-%d').strftime("%b'%y")
        prv_full = datetime.datetime.strptime(pce_core_s[1]['date'], '%Y-%m-%d').strftime("%b'%y")
        if yoy_cur is not None and yoy_prev is not None:
            direction = 'up' if yoy_cur > yoy_prev else 'down'
            # "Core PCE re-accelerated to <strong>+X.X% YoY</strong> (Mon'YY), up from +X.X% in Mon'YY"
            html = re.sub(
                r"(Core PCE [a-z\-]+ to <strong>)\+\d+\.\d+% YoY</strong> \([A-Z][a-z]+'\d+\), (?:up|down) from \+\d+\.\d+% in [A-Z][a-z]+'\d+",
                rf"\g<1>+{yoy_cur:.1f}% YoY</strong> ({cur_full}), {direction} from +{yoy_prev:.1f}% in {prv_full}",
                html, count=1)
            applied.append(f'Commentary Core PCE updated to +{yoy_cur:.1f}% ({cur_full})')

    psv = data.get('psavert', [])
    if psv and len(psv) >= 2:
        sav_cur = round(float(psv[0]['value']), 1)
        sav_prev = round(float(psv[1]['value']), 1)
        sav_cur_lbl = datetime.datetime.strptime(psv[0]['date'], '%Y-%m-%d').strftime("%b'%y")
        sav_prv_short = datetime.datetime.strptime(psv[1]['date'], '%Y-%m-%d').strftime("%b")
        direction = 'up' if sav_cur > sav_prev else 'down'
        # "Saving rate X.X%</strong> (Mon'YY) — ticking up/down from Mon's X.X%"
        # The finding-first commentary sweep replaced this templated phrasing
        # with a finding-first title ("Saving rate at 3.6% — consumers …"). If
        # the legacy sentinel `</strong> — ticking` isn't in the HTML, skip
        # silently rather than logging a zero-replacement audit failure.
        if '</strong> — ticking' not in html:
            warnings.append(
                'Commentary saving rate: legacy "</strong> — ticking" '
                'phrasing not in HTML (finding-first sweep removed it); '
                'skipped')
        else:
            sav_pat = r"(Saving rate )\d+\.\d+%</strong> \([A-Z][a-z]+'\d+\) — ticking (?:up|down) from [A-Z][a-z]+'s \d+\.\d+%"
            new_h, n = re.subn(
                sav_pat,
                rf"\g<1>{sav_cur}%</strong> ({sav_cur_lbl}) — ticking {direction} from {sav_prv_short}'s {sav_prev}%",
                html, count=1)
            _record_subn_result('Commentary saving rate', sav_pat, n)
            if n:
                html = new_h
                applied.append(f'Commentary saving rate updated to {sav_cur}% ({sav_cur_lbl})')

    for tab in ('cpi', 'pce'):
        txt = tabs.get(tab, '')
        if txt: html = patch_commentary(html, tab, txt)
    return html


def render_housing(html, data, vals, tabs):
    mtg    = vals.get('mortgage30')
    starts = vals.get('housing_starts')

    if mtg is not None:
        mtg_s = data.get('mortgage30')
        mtg_date = mtg_s[0].get('date','') if mtg_s else ''
        mtg_lbl = f"30yr Mortgage {month_label(mtg_date)}" if mtg_date else '30yr Mortgage'
        html = patch_kpi_full(html, '30yr Mortgage 2025', mtg_lbl, f'{mtg:.2f}%')
        html = patch_array_last(html, 'rate30', mtg, 2)

    if starts is not None:
        html = patch_array_last(html, 'sf', round(starts), 0)

    txt = tabs.get('housing', '')
    if txt: html = patch_commentary(html, 'housing', txt)
    return html


def render_oil(html, data, vals, tabs):
    wti   = vals.get('wti')
    brent = vals.get('brent')

    if wti is not None:
        # Auto-generate WTI sub-line from current month's daily data
        oil_chart = data.get('oil_daily_chart', {})
        wti_vals  = [v for v in oil_chart.get('wti', []) if v is not None]
        mon_label = oil_chart.get('month', '')
        if len(wti_vals) >= 2:
            mon_high = max(wti_vals)
            mon_low  = min(wti_vals)
            mon_open = wti_vals[0]
            mtd_chg  = wti - mon_open
            mtd_pct  = mtd_chg / mon_open * 100
            sign     = '+' if mtd_chg >= 0 else ''
            wti_sub  = (f'{sign}{mtd_chg:.1f} ({sign}{mtd_pct:.1f}%) MTD'
                        f' · Range ${mon_low:.0f}–${mon_high:.0f} · {mon_label}')
        else:
            wti_sub = None
        html = patch_kpi(html, 'WTI — Latest', f'${wti:.1f}', wti_sub)
        html = patch_array_last(html, 'wti', round(wti, 1), 1, scope_var='OIL_MONTHLY')

    if brent is not None:
        brent_sub = f'Spread: ${brent - wti:.1f}' if wti is not None else None
        html = patch_kpi(html, 'Brent — Latest', f'${brent:.1f}', brent_sub)
        html = patch_array_last(html, 'brent', round(brent, 1), 1, scope_var='OIL_MONTHLY')

    oil_daily = data.get('oil_daily_chart')
    if oil_daily:
        html = inject_oil_daily(html, oil_daily)

    # ── Auto-update SHOCK_TRACKER with latest values ────────────────
    html = update_shock_tracker(html, data, vals)

    txt = tabs.get('oil', '')
    if txt: html = patch_commentary(html, 'oil', txt)
    return html


def update_shock_tracker(html, data, vals):
    """Update SHOCK_TRACKER with latest values from signals and raw data."""
    shock_date = datetime.date(2026, 3, 1)
    today = datetime.date.today()
    weeks = round((today - shock_date).days / 7)
    wti_pre = 65.4  # 2025 annual avg (pre-shock baseline)
    wti_now = vals.get('wti', wti_pre)
    wti_chg = round((wti_now / wti_pre - 1) * 100)

    # Gather latest values for each phase
    gas = data.get('gasoline', [])
    gas_now = gas[0]['value'] if gas else None
    # Gas pre-shock: find last value before March 2026
    gas_pre = 2.89  # default pre-shock baseline
    for obs in (gas or []):
        if obs['date'] < '2026-03-01':
            gas_pre = obs['value']; break
    # No estimates — only use real GASREGW data for status decisions

    # Compute YoY on a monthly CPI index series: latest obs vs same month prior year.
    # Returns (yoy_pct, latest_date) or (None, None) when history is insufficient.
    def _yoy_from_index_series(series):
        if not series or len(series) < 13:
            return None, None
        cur = series[0]
        target_mo = f"{int(cur['date'][:4])-1}{cur['date'][4:7]}"
        ya = next((o for o in series if o['date'][:7] == target_mo), None)
        if not ya or not ya['value']:
            return None, None
        return round((cur['value'] - ya['value']) / ya['value'] * 100, 1), cur['date']

    cpi_energy_yoy, _       = _yoy_from_index_series(data.get('cpiengsl', []))
    cpi_trans_yoy, cpi_trans_date = _yoy_from_index_series(data.get('cpi_transport', []))
    food_away_yoy, food_away_date = _yoy_from_index_series(data.get('cpi_food_away', []))

    # Pre-shock baselines: YoY reading from the last observation before the shock.
    def _pre_shock_yoy(series, shock_iso='2026-03-01'):
        pre_obs = next((o for o in series if o['date'] < shock_iso), None)
        if not pre_obs:
            return None
        target_mo = f"{int(pre_obs['date'][:4])-1}{pre_obs['date'][4:7]}"
        ya = next((o for o in series if o['date'][:7] == target_mo), None)
        if not ya or not ya['value']:
            return None
        return round((pre_obs['value'] - ya['value']) / ya['value'] * 100, 1)

    cpi_trans_pre = _pre_shock_yoy(data.get('cpi_transport', [])) or 5.8
    food_away_pre = _pre_shock_yoy(data.get('cpi_food_away', [])) or 3.4

    # ── MMA-based confirmation (post-shock MoM annualized vs pre-shock 6-MMA) ──
    # Macro-standard methodology for shock pass-through. Immune to the YoY
    # base-effect contamination (e.g. Mar'25 Transport trough inflated YoY).
    def _latest_mom_ann(series):
        """Latest single-month MoM change, annualized as compound rate.
        Returns (yoy_ann_pct, latest_date, prior_value)."""
        if not series or len(series) < 2: return None, None, None
        cur, prev = series[0], series[1]
        if not prev['value']: return None, None, None
        ann = ((cur['value'] / prev['value']) ** 12 - 1) * 100
        return round(ann, 1), cur['date'], prev['value']

    def _pre_shock_6mom_ann(series, shock_iso='2026-03-01'):
        """6-month trailing compound MoM, annualized, ending in last pre-shock
        observation. Formula: (V[pre] / V[pre+6]) ** 2 − 1."""
        if not series: return None
        pre_idx = next((i for i, o in enumerate(series) if o['date'] < shock_iso), None)
        if pre_idx is None or len(series) < pre_idx + 7: return None
        cur, prior = series[pre_idx]['value'], series[pre_idx + 6]['value']
        if not prior: return None
        return round(((cur / prior) ** 2 - 1) * 100, 1)

    def _mma_status(post_mma, pre_mma, expected_weeks, data_is_post_shock):
        """Returns (status, reason). Confirmation rule: latest post-shock MoM
        (annualized) vs pre-shock 6-MMA (annualized). Uses signed diff —
        inflation phases only confirm on acceleration (diff > 0)."""
        win = f'weeks {expected_weeks[0]}\u2013{expected_weeks[1]}'
        if post_mma is None:
            return 'awaiting_data', 'Insufficient post-shock history to compute MMA.'
        if pre_mma is None:
            return 'not_yet', 'Cannot compute pre-shock 6-MMA baseline (needs 7+ obs).'
        if not data_is_post_shock:
            return 'not_yet', f'Latest reading predates the Mar 2026 shock. Expected window: {win}.'
        diff = post_mma - pre_mma
        in_window     = expected_weeks[0] <= weeks <= expected_weeks[1]
        past_window   = weeks > expected_weeks[1]
        before_window = weeks < expected_weeks[0]
        if diff > 0.5 and before_window:
            return 'ahead', f'Moved +{diff:.1f}pp earlier than the expected window ({win}).'
        if diff > 1.5 and (in_window or past_window):
            return 'confirmed', (f'Post-shock pace +{post_mma:.1f}% ann. exceeds pre-shock 6-MMA +{pre_mma:.1f}% by +{diff:.1f}pp (>1.5pp threshold). '
                                 f'We are {"in" if in_window else "past"} the expected window ({win}).')
        if diff > 0.5 and (in_window or past_window):
            return 'emerging', (f'Early signal: +{diff:.1f}pp above pre-shock pace. '
                                f'Between 0.5 and 1.5pp = emerging. Window: {win}.')
        if diff < -0.5 and (in_window or past_window):
            return 'not_yet', (f'Decelerating vs pre-shock pace ({post_mma:.1f}% < {pre_mma:.1f}%). '
                               'Inflation phases only confirm on acceleration.')
        if in_window:
            return 'on_schedule', f'In expected window ({win}) but monthly pace matches pre-shock — no material move yet.'
        if before_window:
            return 'not_yet', f'Too early — expected window starts {win.split()[1]}.'
        return 'not_yet', f'Monthly pace matches pre-shock baseline. Window: {win}.'

    trans_mom_ann, trans_latest, trans_prev_val = _latest_mom_ann(data.get('cpi_transport', []))
    trans_pre_mma = _pre_shock_6mom_ann(data.get('cpi_transport', []))
    food_mom_ann,  food_latest,  food_prev_val  = _latest_mom_ann(data.get('cpi_food_away', []))
    food_pre_mma  = _pre_shock_6mom_ann(data.get('cpi_food_away', []))
    energy_mom_ann, energy_latest, energy_prev_val = _latest_mom_ann(data.get('cpiengsl', []))
    energy_pre_mma = _pre_shock_6mom_ann(data.get('cpiengsl', []))

    def _mo_lbl(d):
        return datetime.datetime.strptime(d, '%Y-%m-%d').strftime("%b'%y") if d else ''

    def _base_effect_note(series, pre_yoy, cur_yoy, pre_mma, post_mma):
        """Compose a base-effect callout when the YoY change is big but the
        monthly pace hasn't actually accelerated above pre-shock. Looks up the
        year-ago index by DATE (not position) to dodge missing-month gaps."""
        if not series or pre_yoy is None or cur_yoy is None:
            return None
        if pre_mma is None or post_mma is None:
            return None
        yoy_delta = cur_yoy - pre_yoy
        mma_delta = post_mma - pre_mma
        if yoy_delta <= 1.5 or mma_delta >= 1.0:
            return None  # YoY isn't inflated relative to actual monthly pace
        cur_date = series[0]['date']  # e.g. '2026-03-01'
        target_mo = f"{int(cur_date[:4]) - 1}{cur_date[4:7]}"
        ya_obs = next((o for o in series if o['date'][:7] == target_mo), None)
        if not ya_obs:
            return None
        return (f"YoY jumped {pre_yoy}% \u2192 {cur_yoy}% (+{round(yoy_delta,1)}pp), "
                f"but this is largely a base effect: {_mo_lbl(ya_obs['date'])} index "
                f"{ya_obs['value']} was a local dip. Monthly pace is what matters.")

    core_cpi = vals.get('core_cpi_yoy', 2.5)
    umcsent = vals.get('umcsent', 56.6)
    saving = vals.get('saving_rate', 4.5)
    cc_del = vals.get('cc_delinq', 2.94)

    def _status(now, pre, expected_weeks, data_is_post_shock=False, move_threshold=0.15):
        """Determine phase status. Only confirm/emerge if data is post-shock.
        chg is SIGNED — positive = shock-consistent direction. Callers for drop-
        expected phases (sentiment, savings) negate both inputs. Opposite-direction
        moves never confirm (METHODOLOGY.md §1.4).

        move_threshold is the noise floor for the metric's natural units (pp for
        YoY series, $/gal for gasoline, index points for sentiment). Pass an
        explicit value per phase — the 0.15 default is only appropriate for
        $/gal-scale series; YoY % and index series have wider noise floors."""
        if now is None:
            return 'awaiting_data'
        if pre is None:
            return 'not_yet'
        if not data_is_post_shock:
            return 'not_yet'  # pre-shock data = baseline, can't confirm
        chg = now - pre
        in_window = expected_weeks[0] <= weeks <= expected_weeks[1]
        past_window = weeks > expected_weeks[1]
        before_window = weeks < expected_weeks[0]
        moved = chg > move_threshold
        if moved and before_window:
            return 'ahead'
        if moved and (in_window or past_window):
            # Confirmation gate stays an absolute floor (0.5 in natural units)
            # so phases with higher move_thresholds still confirm at the same
            # level the narrative copy advertises ($0.50/gal, 0.5pt UMich, etc.)
            return 'confirmed' if chg > 0.5 else 'emerging'
        return 'on_schedule' if in_window else 'not_yet'

    # Check which data readings are post-shock (date >= Mar 2026)
    shock = '2026-03-01'
    def _latest_date(key):
        s = data.get(key, [])
        return s[0].get('date', '') if s else ''

    gas_post     = _latest_date('gasoline') >= shock
    cpi_post     = _latest_date('cpi_all') >= shock
    umcsent_post = _latest_date('umcsent') >= shock
    saving_post  = _latest_date('psavert') >= shock

    # Now that `shock` is defined, resolve the MMA-phase statuses + reasons.
    trans_status, trans_reason = _mma_status(trans_mom_ann, trans_pre_mma, [4, 6],
                                             data_is_post_shock=(trans_latest or '') >= shock)
    energy_status, energy_reason = _mma_status(energy_mom_ann, energy_pre_mma, [6, 14],
                                               data_is_post_shock=(energy_latest or '') >= shock)
    food_status, food_reason = _mma_status(food_mom_ann, food_pre_mma, [12, 20],
                                           data_is_post_shock=(food_latest or '') >= shock)
    cc_post      = _latest_date('cc_delinq') >= shock

    phases = [
        {"phase": "Pump Prices Spike", "expected": "Days 1\u201314", "expected_weeks": [0, 2],
         "metric": "Gasoline $/gal", "pre": gas_pre, "now": gas_now,
         "chg": round(gas_now - gas_pre, 2) if gas_now and gas_pre else None,
         "status": _status(gas_now, gas_pre, [0, 2], data_is_post_shock=gas_post,
                           move_threshold=0.15),  # $/gal \u2014 ~$0.05-0.10 weekly noise
         "source": "FRED GASREGW \u00b7 EIA weekly retail gasoline",
         "status_reason": (
             (f'Gasoline +${round(gas_now-gas_pre,2)}/gal (+{((gas_now-gas_pre)/gas_pre*100):.0f}%) vs pre-shock baseline — well beyond $0.50 confirmation threshold. Expected window: weeks 0\u20132.'
              ) if gas_now and gas_post and gas_pre else 'Awaiting weekly GASREGW release.'
         ),
         "note": f"FRED GASREGW: ${gas_pre:.2f} \u2192 ${gas_now:.2f}/gal (+{((gas_now-gas_pre)/gas_pre*100):.0f}%)" if gas_now and gas_post else "Awaiting FRED GASREGW weekly retail gasoline data",
         "commentary": (
             (f"Retail pumps moved within ~2 weeks of the WTI spike; +${round(gas_now-gas_pre,2)}/gal pass-through is roughly in line with the $0.24/gal-per-$10/bbl rule-of-thumb."
              ) if gas_now and gas_post and gas_pre else "Awaiting weekly GASREGW release."
         ),
        },
        {"phase": "Transport & Freight Costs", "expected": "Weeks 4\u20136", "expected_weeks": [4, 6],
         "metric": "CPI Transport Svcs YoY", "pre": cpi_trans_pre, "now": cpi_trans_yoy,
         "chg": round(cpi_trans_yoy - cpi_trans_pre, 1) if cpi_trans_yoy is not None else None,
         "status": trans_status, "status_reason": trans_reason,
         "source": "FRED CUSR0000SETG \u00b7 BLS CPI Transportation Services (monthly)",
         "base_effect_note": _base_effect_note(
             data.get('cpi_transport', []), cpi_trans_pre, cpi_trans_yoy,
             trans_pre_mma, trans_mom_ann
         ),
         "post_mom_ann": trans_mom_ann, "pre_6mma": trans_pre_mma,
         "detail": (f"{_mo_lbl(trans_latest)} {data.get('cpi_transport',[{}])[0].get('value','?')} vs {trans_prev_val} prior \u00b7 post-shock +{trans_mom_ann}% ann. \u00b7 pre-shock 6-MMA +{trans_pre_mma}%"
                    if trans_mom_ann is not None and trans_pre_mma is not None else
                    "Awaiting CPI Transport Services history"),
         "note": (f"CPI Transport Svcs at {cpi_trans_yoy}% YoY ({_mo_lbl(cpi_trans_date)})"
                  if cpi_trans_yoy is not None else "Awaiting CPI Transport Services data"),
         "commentary": (
             ("Airfare + auto insurance renewals + shipping passing through. "
              "Part of the YoY jump is base effect (Mar'25 trough); post-shock monthly pace is the cleaner signal."
             ) if trans_mom_ann is not None and trans_pre_mma is not None and trans_mom_ann > trans_pre_mma + 0.5 else
             ("Transport Services running at pre-shock pace \u2014 oil shock not yet visible in the monthly cadence."
              if trans_mom_ann is not None else
              "Needs 24 obs of CUSR0000SETG to compute post-shock vs pre-shock MMA."))
        },
        {"phase": "CPI Energy Prints", "expected": "Weeks 6\u201314", "expected_weeks": [6, 14],
         "metric": "CPI Energy YoY", "pre": 0.4, "now": cpi_energy_yoy,
         "chg": round(cpi_energy_yoy - 0.4, 1) if cpi_energy_yoy is not None else None,
         "status": energy_status, "status_reason": energy_reason,
         "source": "FRED CPIENGSL \u00b7 BLS CPI Energy (monthly)",
         "base_effect_note": _base_effect_note(
             data.get('cpiengsl', []), 0.4, cpi_energy_yoy,
             energy_pre_mma, energy_mom_ann
         ),
         "post_mom_ann": energy_mom_ann, "pre_6mma": energy_pre_mma,
         "detail": (f"{_mo_lbl(energy_latest)} vs prior month \u00b7 post-shock +{energy_mom_ann}% ann. \u00b7 pre-shock 6-MMA +{energy_pre_mma}%"
                    if energy_mom_ann is not None and energy_pre_mma is not None else
                    "Awaiting CPI Energy history"),
         "note": f"CPI Energy at +{cpi_energy_yoy}% YoY" if cpi_energy_yoy is not None else "Awaiting post-shock CPI release",
         "commentary": (
             ("Headline energy print absorbing the full WTI + gasoline spike \u2014 "
              "single largest monthly move in the tracker. Feeds directly into April headline CPI."
             ) if energy_mom_ann is not None and energy_pre_mma is not None and energy_mom_ann > energy_pre_mma + 5 else
             ("CPI Energy tracking oil gently \u2014 passthrough slower than expected."
              if energy_mom_ann is not None else
              "No post-shock CPI Energy release yet."))
        },
        {"phase": "Food & Services Inflation", "expected": "Months 3\u20135", "expected_weeks": [12, 20],
         "metric": "CPI Food Away YoY", "pre": food_away_pre, "now": food_away_yoy,
         "chg": round(food_away_yoy - food_away_pre, 1) if food_away_yoy is not None else None,
         "status": food_status, "status_reason": food_reason,
         "source": "FRED CUSR0000SEFV \u00b7 BLS CPI Food Away from Home (monthly)",
         "base_effect_note": _base_effect_note(
             data.get('cpi_food_away', []), food_away_pre, food_away_yoy,
             food_pre_mma, food_mom_ann
         ),
         "post_mom_ann": food_mom_ann, "pre_6mma": food_pre_mma,
         "detail": (f"{_mo_lbl(food_latest)} vs prior month \u00b7 post-shock +{food_mom_ann}% ann. \u00b7 pre-shock 6-MMA +{food_pre_mma}%"
                    if food_mom_ann is not None and food_pre_mma is not None else
                    "Awaiting CPI Food Away history"),
         "note": (f"CPI Food Away at {food_away_yoy}% YoY ({_mo_lbl(food_away_date)})"
                  if food_away_yoy is not None else "Awaiting CPI Food Away data"),
         "commentary": (
             ("Restaurant prices decelerating slightly \u2014 menu changes typically lag oil by 3\u20135 months, "
              "so the first real test will be May\u2013June prints."
             ) if food_mom_ann is not None and food_pre_mma is not None and food_mom_ann < food_pre_mma + 0.5 else
             ("Food Away accelerating above pre-shock pace \u2014 menu pass-through arriving earlier than expected."
              if food_mom_ann is not None else
              "Needs CPI Food Away history for the MMA comparison."))
        },
        {"phase": "Core Goods Inflation", "expected": "Months 5\u20138", "expected_weeks": [20, 32],
         "metric": "Core CPI YoY", "pre": 2.5, "now": core_cpi, "chg": round(core_cpi - 2.5, 1),
         "status": _status(core_cpi, 2.5, [20, 32], data_is_post_shock=cpi_post,
                           move_threshold=0.5),  # pp YoY \u2014 Core CPI wiggles \u00b10.2-0.3pp month-to-month
         "source": "FRED CPILFESL \u00b7 BLS CPI ex-Food & Energy (monthly)",
         "status_reason": (
             f'Latest Core CPI reading predates the shock. First post-shock print will land within ~1 month of release.'
             if not cpi_post else
             (f'Core CPI {core_cpi}% vs 2.5% pre-shock ({round(core_cpi-2.5,1):+.1f}pp) \u2014 within the \u00b10.5pp noise floor for Core CPI YoY. Expected window: weeks 20\u201332 (months 5\u20138 post-shock), currently at week {weeks}.'
              if abs(core_cpi - 2.5) < 0.5 else
              f'Core CPI {core_cpi}% vs 2.5% pre-shock ({round(core_cpi-2.5,1):+.1f}pp) \u2014 beyond \u00b10.5pp noise floor. Expected window: weeks 20\u201332 (months 5\u20138), currently at week {weeks}.')
         ),
         "note": f"Core CPI at {core_cpi}% \u2014 {'data predates shock' if not cpi_post else 'energy input costs tracking'}",
         "commentary": "Manufacturing/chemicals absorb input costs over 5\u20138 months. Too early for this phase \u2014 energy input costs only began passing through in Mar'26 PPI."
        },
        {"phase": "Consumer Sentiment Falls", "expected": "Weeks 2\u20136", "expected_weeks": [2, 6],
         "metric": "UMich Sentiment", "pre": 56.6, "now": umcsent, "chg": round(umcsent - 56.6, 1),
         "status": _status(-umcsent, -56.6, [2, 6], data_is_post_shock=umcsent_post,
                           move_threshold=0.5),  # index points \u2014 confirmation threshold cited in reason text below
         "source": "UMich Survey of Consumers (direct) \u00b7 prelim mid-month, final end-of-month",
         "status_reason": (
             f'UMich dropped from 56.6 to {umcsent} ({round(umcsent-56.6,1):+.1f}pt). Confirmation threshold: 0.5pt move. Expected window: weeks 2\u20136, currently at week {weeks}.'
             if umcsent_post else
             'Latest UMich reading predates the shock. Next prelim typically ~mid-month.'
         ),
         "note": f"UMich at {umcsent} \u2014 {'pre-shock baseline, awaiting Mar+ reading' if not umcsent_post else 'post-shock reading' + (' confirms decline' if umcsent < 55 else ', watching')}",
         "commentary": (
             ("Sharp drop in visible-inflation-sensitive households. Pump pain + media cycle around oil shock drove the print. "
              "UMich often overshoots relative to actual spending changes."
             ) if umcsent_post and umcsent is not None and umcsent < 55 else
             ("Sentiment holding relative to pre-shock \u2014 consumer psychology not yet reflecting the spike."
              if umcsent_post else
              "Awaiting first post-shock sentiment reading."))
        },
        {"phase": "Savings Drawdown", "expected": "Months 2\u20134", "expected_weeks": [8, 16],
         "metric": "Personal Saving Rate", "pre": 4.5, "now": saving, "chg": round(saving - 4.5, 1),
         "status": _status(-saving, -4.5, [8, 16], data_is_post_shock=saving_post,
                           move_threshold=0.3),  # pp \u2014 saving rate moves \u00b10.2-0.3pp month-to-month
         "source": "FRED PSAVERT \u00b7 BEA Personal Saving Rate (monthly, ~1-mo lag)",
         "status_reason": (
             f'Latest PSAVERT reading ({_latest_date("psavert")}) is pre-shock. BEA releases with ~1-month lag, so the first post-shock print lands in ~May.'
             if not saving_post else
             f'Saving rate {saving}% vs 4.5% pre-shock ({round(saving-4.5,1):+.1f}pp). Expected window: weeks 8\u201316.'
         ),
         "note": f"Saving rate at {saving}% \u2014 {'pre-shock baseline' if not saving_post else 'stable so far' if saving >= 4.2 else 'declining'}",
         "commentary": (
             "PSAVERT lags ~1 month so current data is still pre-shock. The fuel-cost bite on take-home pay won't show until May\u2013Jun prints."
             if not saving_post else
             ("Saving rate compressing as expected \u2014 liquid buffer erosion underway."
              if saving < 4.2 else "Saving rate stable despite the pump hit; either absorbed via discretionary spending or income strong."))
        },
        {"phase": "Delinquencies Climb", "expected": "Months 5\u201310", "expected_weeks": [20, 40],
         "metric": "CC 90+ DPD Rate", "pre": 2.94, "now": cc_del, "chg": round(cc_del - 2.94, 2),
         "status": _status(cc_del, 2.94, [20, 40], data_is_post_shock=cc_post,
                           move_threshold=0.15),  # pp \u2014 quarterly series, slow-moving, 0.1-0.2pp is signal
         "source": "NY Fed Household Debt & Credit Report \u00b7 CC 90+ DPD (quarterly)",
         "status_reason": (
             f'Latest CC 90+ DPD is quarterly (NY Fed HHDC), reading {_latest_date("cc_delinq")}. Pre-shock. Expected window: months 5\u201310 (weeks 20\u201340). First post-shock look is Q3\'26 release (~Nov\'26).'
             if not cc_post else
             f'CC delinquency {cc_del}% vs 2.94% pre-shock ({round(cc_del-2.94,2):+.2f}pp).'
         ),
         "note": f"CC delinquency at {cc_del}% \u2014 {'pre-shock data, too early' if not cc_post else 'monitoring for oil impact'}",
         "commentary": (
             "90+ DPD is quarterly (NY Fed HHDC) and lags 2\u20133 quarters. Current reading is pre-shock; first real look is Q3'26 release (Nov'26)."
             if not cc_post else
             "Credit stress surfacing earlier than typical; watch subprime segments first.")
        },
    ]

    tracker = {
        "shock_date": "2026-03-01",
        "weeks_elapsed": weeks,
        "wti_pre": wti_pre, "wti_now": round(wti_now, 1), "wti_chg_pct": wti_chg,
        "phases": phases
    }

    # Tier 1 anti-clone migration: SHOCK_TRACKER is now served via
    # /api/state.json. Register the full payload and patch the inline
    # declaration to a `let SHOCK_TRACKER = null;` placeholder.
    #
    # Placement note: the placeholder lives at SCRIPT scope (just before
    # `function buildOilTab() {`), not inside the tab builder. A previous
    # iteration placed it inside the function, which shadowed the
    # hydration target and left oil-impact-chain blank on the live page
    # (the boot loader's reassignment hit `window.SHOCK_TRACKER` instead
    # of the function-local let). The regex anchors on the declaration
    # itself; no comment anchor required since SHOCK_TRACKER is unique.
    _api_writer.register('SHOCK_TRACKER', tracker)
    placeholder = 'let SHOCK_TRACKER = null;'  # boot loader hydrates from /api/state.json
    # Accept both legacy literal and placeholder shapes (idempotent re-runs).
    pattern = r'(?:const|let|var)\s+SHOCK_TRACKER\s*=\s*(?:\{[\s\S]*?\}|null)\s*;'
    new_html, n = re.subn(pattern, lambda m: placeholder, html, count=1)
    _record_subn_result('SHOCK_TRACKER', pattern, n)
    if n:
        applied.append(f'SHOCK_TRACKER registered to state.json ({weeks} weeks, WTI ${wti_now:.0f}); inline zeroed')
        html = new_html
    else:
        warnings.append('update_shock_tracker: SHOCK_TRACKER const not matched')
    return html


def render_outlook(html, ana):
    kpis    = ana.get('kpi_updates', {})
    posture = kpis.get('risk_posture', 'Neutral')
    regime  = kpis.get('macro_regime', 'Expansion')
    fed     = kpis.get('fed_bias',     'On Hold')

    html = patch_kpi(html, 'Risk Posture', posture)
    html = patch_kpi(html, 'Macro Regime', regime)
    html = patch_kpi(html, 'Fed Bias',     fed)

    # NB: outlook_body is generated by the briefing agent but no longer patched
    # onto the dashboard. The only class="stk-lead" element is the architecture
    # page hero (How the Dashboard Works) and patching it there clobbered the
    # static infra description every render. The Outlook tab's narrative comes
    # from tabs.gdp → patch_commentary below.

    txt = ana.get('tabs', {}).get('gdp', '')
    if txt: html = patch_commentary(html, 'gdp', txt)

    banks_txt = ana.get('tabs', {}).get('banks', '')
    if banks_txt: html = patch_commentary(html, 'banks', banks_txt)
    return html


def rebuild_kpi_strip(html, data, vals):
    """Rebuild the top-level KPIS array with latest values and MoM deltas."""

    def _mlbl(date_str):
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")

    def _qlbl(date_str):
        """Quarter label for start-of-quarter dates (FRED convention).
        e.g. '2025-10-01' → "Q4'25", '2025-07-01' → "Q3'25"."""
        y, m = int(date_str[:4]), int(date_str[5:7])
        q = (m - 1) // 3 + 1
        return f"Q{q}'{y % 100:02d}"

    def _mom(series, precision=1, pct=False):
        """Return (current, prior, delta_str, delta_num) from newest-first monthly series."""
        if not series or len(series) < 2:
            return None, None, '', 0
        cur, prev = series[0]['value'], series[1]['value']
        if pct:
            # Both are already YoY %, compute the delta in pp
            d = round(cur - prev, precision)
        else:
            d = round(cur - prev, precision)
        sign = '+' if d > 0 else ''
        return cur, prev, f'{sign}{d}', d

    # ── §8 Vintage-badge helpers ───────────────────────────────────
    # Publish-lag table from data/playbook.md / known_normal.json.
    # If a series' latest observation is older than 1.5x its expected
    # cadence, flag STALE. Datasets released within the last 7 days
    # earn a FRESH badge. UMich already carries its own PRELIM badge
    # (set elsewhere) so we don't override it.
    _PUBLISH_LAG_DAYS = {
        # series_key: typical days between latest obs and present
        'gasoline': 7, 'wti': 7, 'brent': 7, 'icsa': 7, 'ccsa': 7,    # weekly
        'unrate': 35, 'nfp': 35, 'cpi': 45, 'core_cpi': 45,            # monthly
        'cpiengsl': 45, 'cpi_food_away': 45, 'cpi_transport': 45,
        'pce': 65, 'core_pce': 65, 'psavert': 65,                     # monthly w/ lag
        'umcsent': 30, 'retail': 45, 'jolts': 50,
        'tdsp': 120, 'gdp_yoy': 100,                                  # quarterly
        'rate30': 7, 'ig_oas': 1, 'hy_oas': 1, 'dgs10': 1, 'ffr': 1,  # daily
        'cc_delinq': 100,
    }

    def _vintage_badge(series_key, latest_iso_date):
        """Return 'STALE' | 'FRESH' | None for a given latest data point.

        - STALE: latest obs is older than 1.5x publish-lag
        - FRESH: latest obs is within last 7 days (new release)
        - None: in normal range — let other badge logic (PRELIM) take over
        """
        if not latest_iso_date or series_key not in _PUBLISH_LAG_DAYS:
            return None
        try:
            obs = datetime.datetime.strptime(latest_iso_date, '%Y-%m-%d').date()
        except Exception:
            return None
        age_days = (datetime.date.today() - obs).days
        lag = _PUBLISH_LAG_DAYS[series_key]
        if age_days <= 7:
            return 'FRESH'
        if age_days > int(lag * 1.5):
            return 'STALE'
        return None

    def _yoy_pair(series):
        """Return (latest_yoy, prior_month_yoy) from index series.
        Matches by calendar month (not index position) to handle gaps.
        """
        if not series or len(series) < 14:
            return None, None
        def _find_month(yr, mo):
            for obs in series:
                od = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
                if od.year == yr and od.month == mo:
                    return obs['value']
            return None
        d0 = datetime.datetime.strptime(series[0]['date'], '%Y-%m-%d')
        d1 = datetime.datetime.strptime(series[1]['date'], '%Y-%m-%d')
        v0, v12 = series[0]['value'], _find_month(d0.year - 1, d0.month)
        v1, v13 = series[1]['value'], _find_month(d1.year - 1, d1.month)
        # Fallback to index position if exact month not found
        if v12 is None: v12 = series[12]['value'] if len(series) > 12 else None
        if v13 is None: v13 = series[13]['value'] if len(series) > 13 else None
        yoy_cur  = round((v0 - v12) / v12 * 100, 2) if v12 else None
        yoy_prev = round((v1 - v13) / v13 * 100, 2) if v13 else None
        return yoy_cur, yoy_prev

    cards = []

    # Card order mirrors tab nav (Jobs → Wages → CPI → Consumer & PCE → Fed
    # Rates) so the strip reads top-to-bottom of the dashboard. Initial Claims
    # sits next to Jobs since both are labor-market timeliness signals.

    # 1. NFP Jobs (MoM change)  (up = good)
    payems = data.get('payems', [])
    if payems and len(payems) >= 3:
        cur_chg = round(payems[0]['value'] - payems[1]['value'])
        prev_chg = round(payems[1]['value'] - payems[2]['value'])
        d = cur_chg - prev_chg
        sign = '+' if d > 0 else ''
        lbl = f"Jobs {_mlbl(payems[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur_chg:+.0f}K', 'metric': 'jobs',
                      'delta': d, 'chg': f'{sign}{d:.0f}K',
                      'sub': f"Prior: {prev_chg:+.0f}K ({_mlbl(payems[1]['date'])})"})

    # 2. Initial Claims (weekly)  (up = bad) — paired with Jobs
    icsa = data.get('icsa', [])
    if icsa and len(icsa) >= 2:
        cur, prev = icsa[0]['value'], icsa[1]['value']
        d = round(cur - prev)
        sign = '+' if d > 0 else ''
        lbl = f"Initial Claims {_mlbl(icsa[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur/1000:.0f}K', 'metric': 'claims',
                      'delta': d, 'chg': f'{sign}{d/1000:.0f}K', 'inv': True,
                      'sub': f"Prior wk: {prev/1000:.0f}K ({_mlbl(icsa[1]['date'])})"})

    # 3. Unemployment  (up = bad)
    unrate = data.get('unrate', [])
    if unrate and len(unrate) >= 2:
        cur, prev, chg, d = _mom(unrate)
        lbl = f"Unemployment {_mlbl(unrate[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur:.1f}%', 'metric': 'unemp',
                      'delta': d, 'chg': f'{chg}pp', 'inv': True,
                      'sub': f"Prior: {prev:.1f}% ({_mlbl(unrate[1]['date'])})"})

    # 3b. Sahm Rule (up ≥ +0.5pp = recession trigger). Defined as the
    # 3-month average U-rate minus the lowest 3-month average from the
    # prior 12 months. Has fired in 9 of 11 NBER recessions since 1948.
    if unrate and len(unrate) >= 15:
        # Newest-first series → take latest 3 for current avg
        recent3 = sum(o['value'] for o in unrate[:3]) / 3
        # Compute rolling 3-mo avg for each of the prior 12 months and find min
        rolling = []
        for i in range(1, 13):
            window = unrate[i:i + 3]
            if len(window) == 3:
                rolling.append(sum(o['value'] for o in window) / 3)
        if rolling:
            min_prior = min(rolling)
            sahm = round(recent3 - min_prior, 2)
            sign = '+' if sahm > 0 else ''
            # Triggered when ≥ +0.5pp; flag color codes the urgency
            triggered = sahm >= 0.5
            cards.append({'lbl': f"Sahm Rule {_mlbl(unrate[0]['date'])}",
                          'val': f'{sign}{sahm:.2f}pp',
                          'metric': 'unemp',
                          'delta': sahm, 'chg': 'TRIGGERED' if triggered else 'OK',
                          'inv': True,
                          'sub': f"3M avg {recent3:.2f}% − 12M low {min_prior:.2f}% · trigger ≥ +0.5pp"})

    # 4. Wages — Atlanta Fed Wage Growth Tracker 3MMA (up = good). Value is
    # already YoY % for continuously-employed workers. Falls back to AHETPI-YoY
    # only when the new series hasn't been collected yet.
    atl_wgt = data.get('wage_growth_atl', [])
    ahetpi = data.get('ahetpi', [])
    if atl_wgt and len(atl_wgt) >= 2:
        cur, prev = atl_wgt[0]['value'], atl_wgt[1]['value']
        d = round(cur - prev, 2)
        sign = '+' if d > 0 else ''
        lbl = f"Wage Growth {_mlbl(atl_wgt[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur:.1f}%', 'metric': 'wages',
                      'delta': d, 'chg': f'{sign}{d:.1f}pp',
                      'sub': f"Prior: {prev:.1f}% ({_mlbl(atl_wgt[1]['date'])}) · Atlanta Fed WGT 3MMA"})
    elif ahetpi and len(ahetpi) >= 14:
        yoy_cur, yoy_prev = _yoy_pair(ahetpi)
        if yoy_cur is not None and yoy_prev is not None:
            d = round(yoy_cur - yoy_prev, 2)
            sign = '+' if d > 0 else ''
            lbl = f"Wage Growth {_mlbl(ahetpi[0]['date'])}"
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'wages',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp',
                          'sub': f"Prior: {yoy_prev:.1f}% ({_mlbl(ahetpi[1]['date'])}) · BLS AHETPI"})

    # 5. CPI YoY — with 3M avg + MoM + YoY in sub
    cpi = data.get('cpi_all', [])
    if cpi and len(cpi) >= 14:
        yoy_cur, yoy_prev = _yoy_pair(cpi)
        # MoM % change (index level)
        mom_pct = None
        if len(cpi) >= 2 and cpi[1]['value']:
            mom_pct = round((cpi[0]['value'] - cpi[1]['value']) / cpi[1]['value'] * 100, 2)
        # 3-month average of monthly YoY (match by calendar month, not index)
        avg3m = None
        if len(cpi) >= 15:
            _cpi_ym = {}
            for obs in cpi:
                _d = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
                _cpi_ym[(_d.year, _d.month)] = obs['value']
            yoys = []
            for i in range(3):
                _d = datetime.datetime.strptime(cpi[i]['date'], '%Y-%m-%d')
                yr_ago = _cpi_ym.get((_d.year - 1, _d.month))
                if yr_ago and yr_ago != 0:
                    yoys.append(round((cpi[i]['value'] - yr_ago) / yr_ago * 100, 2))
            if yoys:
                avg3m = round(sum(yoys) / len(yoys), 1)
        if yoy_cur is not None and yoy_prev is not None:
            d = round(yoy_cur - yoy_prev, 2)
            sign = '+' if d > 0 else ''
            lbl = f"Headline CPI {_mlbl(cpi[0]['date'])}"
            mom_str = f"MoM: {mom_pct:+.2f}% · " if mom_pct is not None else ""
            avg3m_str = f" · 3M avg: {avg3m:.1f}%" if avg3m is not None else ""
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'cpi',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp', 'inv': True,
                          'sub': f"{mom_str}YoY: {yoy_cur:.1f}%{avg3m_str} · Prior: {yoy_prev:.1f}% ({_mlbl(cpi[1]['date'])})"})

    # 6. Core PCE YoY  (up = bad)
    pce_core = data.get('pce_core', [])
    if pce_core and len(pce_core) >= 14:
        yoy_cur, yoy_prev = _yoy_pair(pce_core)
        if yoy_cur is not None and yoy_prev is not None:
            d = round(yoy_cur - yoy_prev, 2)
            sign = '+' if d > 0 else ''
            lbl = f"Core PCE {_mlbl(pce_core[0]['date'])}"
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'pce',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp', 'inv': True,
                          'sub': f"Prior: {yoy_prev:.1f}% ({_mlbl(pce_core[1]['date'])})"})

    # 7. Headline PCE YoY  (up = bad). Paired with Core PCE — when headline
    # detaches from core (e.g. an oil shock pushing energy through), the gap
    # is itself a signal worth seeing on the strip.
    pce_h = data.get('pce', [])
    if pce_h and len(pce_h) >= 14:
        yoy_cur, yoy_prev = _yoy_pair(pce_h)
        if yoy_cur is not None and yoy_prev is not None:
            d = round(yoy_cur - yoy_prev, 2)
            sign = '+' if d > 0 else ''
            lbl = f"Headline PCE {_mlbl(pce_h[0]['date'])}"
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'pce',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp', 'inv': True,
                          'sub': f"Prior: {yoy_prev:.1f}% ({_mlbl(pce_h[1]['date'])}) · BEA PCEPI"})

    # 8. Consumer Sentiment (UMich)  (up = good)
    umcsent = data.get('umcsent', [])
    if umcsent and len(umcsent) >= 2:
        cur_s, prev_s, chg_s, d_s = _mom(umcsent)
        yoy_s = None
        if len(umcsent) >= MONTHLY_TREND_WINDOW:
            yoy_s = round(cur_s - umcsent[12]['value'], 1)
        lbl = f"UMich Sentiment {_mlbl(umcsent[0]['date'])}"
        yoy_str = f" · YoY: {yoy_s:+.1f}" if yoy_s is not None else ""
        # Surface prelim/final flag from UMich direct feed so the KPI can badge it.
        badge = 'PRELIM' if umcsent[0].get('status') == 'preliminary' else None
        cards.append({'lbl': lbl, 'val': f'{cur_s:.1f}', 'metric': 'umcsent',
                      'delta': d_s, 'chg': f'{chg_s}', 'badge': badge,
                      'sub': f"MoM: {chg_s}{yoy_str} · Prior: {prev_s:.1f} ({_mlbl(umcsent[1]['date'])})"})

    # 9. Debt Service Ratio (TDSP)  (up = bad). TDSP is QUARTERLY (FRED
    # stores with start-of-quarter date — 2025-10-01 = Q4 2025), so use
    # _qlbl here instead of _mlbl.
    tdsp = data.get('tdsp', [])
    if tdsp and len(tdsp) >= 2:
        cur_t, prev_t, chg_t, d_t = _mom(tdsp)
        lbl = f"Debt Service Ratio {_qlbl(tdsp[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur_t:.1f}%', 'metric': 'dsr',
                      'delta': d_t, 'chg': f'{chg_t}pp', 'inv': True,
                      'sub': f"% of disp. income · Prior: {prev_t:.1f}% ({_qlbl(tdsp[1]['date'])})"})

    # 10. Fed Funds Rate
    ffr = data.get('ffr')
    if ffr and isinstance(ffr, dict):
        v = ffr['value']
        # Derive FOMC target range from effective rate (round down to nearest 0.25)
        lower = math.floor(v * 4) / 4
        upper = lower + 0.25
        lbl = f"Fed Funds {_mlbl(ffr['date'])}"
        cards.append({'lbl': lbl, 'val': f'{v:.2f}%', 'metric': 'rate',
                      'delta': 0, 'chg': '',
                      'sub': f"FOMC range: {lower:.2f}–{upper:.2f}% · Effective rate"})

    # 11. 10Y Treasury
    dgs10 = data.get('dgs10')
    dgs2 = data.get('dgs2')
    if dgs10 and isinstance(dgs10, dict):
        spr = ''
        if dgs2 and isinstance(dgs2, dict):
            bp = round((dgs10['value'] - dgs2['value']) * 100)
            spr = f" · 2Y: {dgs2['value']:.2f}% · Spread: {bp:+d}bp"
        lbl = f"10Y Treasury {_mlbl(dgs10['date'])}"
        cards.append({'lbl': lbl, 'val': f'{dgs10["value"]:.2f}%', 'metric': 'rate',
                      'delta': 0, 'chg': '',
                      'sub': f"Daily{spr}"})

    if not cards:
        return html

    # §8 vintage-badge post-pass — annotate STALE/FRESH on every card
    # that doesn't already carry an explicit badge (PRELIM from UMich).
    # Mapping from card.metric to the raw_data series key. Unknown
    # metrics get no auto-badge.
    _METRIC_TO_SERIES = {
        'jobs': 'nfp', 'claims': 'icsa', 'unemp': 'unrate',
        'wages': 'ahetpi', 'cpi': 'cpi', 'pce': 'pce',
        'umcsent': 'umcsent', 'dsr': 'tdsp',
        'rate': 'rate30',  # 30y mortgage — closest weekly proxy
    }
    for c in cards:
        if c.get('badge'):
            continue  # respect explicit badges (e.g. UMich PRELIM)
        m = c.get('metric')
        series_key = _METRIC_TO_SERIES.get(m)
        if not series_key:
            continue
        series = data.get(series_key) or []
        if not series:
            continue
        latest = series[0].get('date') if isinstance(series[0], dict) else None
        v = _vintage_badge(series_key, latest)
        if v:
            c['badge'] = v

    # ── §1 Sparklines post-pass ────────────────────────────────────
    # Emit a small ordered list of values for each card so the client
    # can render an inline SVG polyline next to the headline number.
    # Three reduction modes:
    #   - 'levels': series values directly (rate %, sentiment, count)
    #   - 'yoy'   : 12-month YoY % for each of the last N months
    #   - 'mom'   : month-on-month diff in original units (NFP)
    # Rate cards (Fed Funds, 10Y) are intentionally skipped — their
    # weekly drift is too small to read at sparkline scale and would
    # just look like a noisy horizontal line.
    def _spark_levels(series, n=18):
        if not series or len(series) < 2:
            return None
        sl = [o['value'] for o in series[:n] if isinstance(o, dict) and 'value' in o]
        if len(sl) < 2:
            return None
        return list(reversed(sl))  # oldest -> newest, chronological L-to-R

    def _spark_yoy_series(series, n=12):
        if not series or len(series) < 13:
            return None
        # Build a (year, month) -> value index so we can match calendar
        # months across the series irrespective of irregular cadence.
        ym = {}
        for o in series:
            try:
                d = datetime.datetime.strptime(o['date'], '%Y-%m-%d')
                ym[(d.year, d.month)] = o['value']
            except Exception:
                continue
        out = []
        # Walk the n most-recent observations and look up the same
        # calendar month one year prior. Skip points where the year-ago
        # value is missing (rather than back-fill with NaN).
        for o in series[:n]:
            try:
                d = datetime.datetime.strptime(o['date'], '%Y-%m-%d')
            except Exception:
                continue
            prior = ym.get((d.year - 1, d.month))
            if prior is None or prior == 0:
                continue
            out.append(round((o['value'] - prior) / prior * 100, 2))
        if len(out) < 2:
            return None
        return list(reversed(out))

    def _spark_mom_diff(series, n=12):
        if not series or len(series) < 3:
            return None
        # Walk newest-first pairs and compute MoM delta in original units.
        diffs = []
        for i in range(min(n, len(series) - 1)):
            try:
                diffs.append(round(series[i]['value'] - series[i + 1]['value'], 2))
            except Exception:
                continue
        if len(diffs) < 2:
            return None
        return list(reversed(diffs))

    # metric → (series_key, mode, post-divisor, max_points)
    # max_points caps history so the sparkline stays readable at small
    # widths (~72px). Weekly series get more points than monthly.
    _METRIC_TO_SPARK = {
        'jobs':    ('payems',           'mom',    None,    12),
        'claims':  ('icsa',             'levels', 1000.0,  26),  # → 'K' scale
        'unemp':   ('unrate',           'levels', None,    18),
        'wages':   ('wage_growth_atl',  'levels', None,    18),
        'cpi':     ('cpi_all',          'yoy',    None,    18),
        'pce':     ('pce',              'yoy',    None,    18),
        'umcsent': ('umcsent',          'levels', None,    18),
        'dsr':     ('tdsp',             'levels', None,    12),
    }
    for c in cards:
        m = c.get('metric')
        mapping = _METRIC_TO_SPARK.get(m)
        if not mapping:
            continue
        lbl = c.get('lbl') if isinstance(c.get('lbl'), str) else ''
        # Sahm Rule shares metric='unemp' with Unemployment but is a
        # derived signal — sparkling the level would mislead. Skip it
        # by checking the label prefix.
        if m == 'unemp' and lbl.startswith('Sahm'):
            continue
        # Wages YoY: prefer Atlanta Fed WGT (already YoY %); if
        # absent, fall back to YoY series computed off AHETPI levels.
        series_key, mode, divisor, max_pts = mapping
        # PCE metric is shared between Core PCE and Headline PCE
        # cards — disambiguate by label so each spark tracks the
        # right series rather than both ending on the headline value.
        if m == 'pce' and lbl.startswith('Core PCE'):
            series_key = 'pce_core'
        series = data.get(series_key) or []
        if m == 'wages' and not series:
            series = data.get('ahetpi') or []
            mode = 'yoy'
        if not series:
            continue
        if mode == 'levels':
            vals = _spark_levels(series, n=max_pts)
        elif mode == 'yoy':
            vals = _spark_yoy_series(series, n=max_pts)
        elif mode == 'mom':
            vals = _spark_mom_diff(series, n=max_pts)
        else:
            vals = None
        if not vals:
            continue
        if divisor:
            vals = [round(v / divisor, 3) for v in vals]
        c['spark'] = vals

    # Tier 1 anti-clone migration: KPIS is now served via /api/state.json
    # (Origin-gated) rather than inlined in the page. The renderer
    # registers the payload here and patches the inline declaration to
    # a `let KPIS = null;` placeholder. The boot loader in index.html
    # hydrates from the API endpoint (or /data/state.json in local dev)
    # and then calls _renderKpiStrip().
    #
    # Accept BOTH the legacy `const KPIS = [...];` literal AND the new
    # `let KPIS = null;` placeholder so a re-run of the renderer against
    # an already-migrated HTML stays idempotent. Both shapes patch to
    # the placeholder.
    _api_writer.register('KPIS', cards)
    # Cross-cycle overlay: register ~1-month-ago KPIS so the toggle UI can
    # show month-over-month comparison without a second fetch.
    # Uses data/kpis_history.json — a rolling dated log (≤104 entries, ≈2 years).
    # Renderer appends today's KPIS, then reads back the entry closest to
    # 28 days ago as PRIOR_KPIS. First-run graceful: file missing → no key.
    try:
        import datetime as _dt, json as _json
        _KPIS_HIST = ROOT / 'data' / 'kpis_history.json'
        _today_str = _dt.date.today().isoformat()
        # Load existing history (oldest-first list of {date, kpis}).
        _hist = []
        if _KPIS_HIST.exists():
            try:
                _hist = _json.loads(_KPIS_HIST.read_text('utf-8'))
            except Exception:
                _hist = []
        # Append today's entry (deduplicate same-day re-runs).
        _hist = [e for e in _hist if e.get('date') != _today_str]
        _hist.append({'date': _today_str, 'kpis': cards})
        # Keep most recent 104 weeks (≈ 2 years of weekly runs).
        _hist.sort(key=lambda e: e['date'], reverse=True)
        _hist = _hist[:104]
        _KPIS_HIST.write_text(_json.dumps(_hist, separators=(',', ':')), 'utf-8')
        # Find entry closest to 28 days ago.
        _target = _dt.date.today() - _dt.timedelta(days=28)
        _best = min(
            (e for e in _hist if e['date'] < _today_str),
            key=lambda e: abs((_dt.date.fromisoformat(e['date']) - _target).days),
            default=None,
        )
        if _best is not None:
            _api_writer.register('PRIOR_KPIS', _best['kpis'])
    except Exception as _exc:
        warnings.append(f'kpis_history: {_exc}')
    pattern = r'(?:const|let|var)\s+KPIS\s*=\s*(?:\[[\s\S]*?\]|null)\s*;'
    placeholder = 'let KPIS = null;'  # boot loader hydrates from /api/state.json
    new_html, n = re.subn(pattern, lambda m: placeholder, html, count=1)
    _record_subn_result('KPIS', pattern, n)
    if n:
        applied.append(f'KPIS registered to state.json ({len(cards)} cards); inline declaration zeroed')
        return new_html
    else:
        warnings.append('rebuild_kpi_strip: KPIS declaration not matched')
        return html


# Field order for the JS literal inside BANK_COMMENTARY —
# must match the consumption pattern in index.html's bank-card template.
_BANK_JS_FIELDS = ('bank', 'ceo', 'ticker', 'color', 'date', 'quote',
                   'economy', 'lending', 'cards_loans', 'macro', 'src',
                   'tech_ai', 'credit', 'outlook')


def update_bank_cards(html):
    """Rebuild BANK_COMMENTARY from data/bank_earnings.json.

    Pending gating: banks with status=='pending' or no actual_report_date
    get a '(pending)' suffix on the displayed date. Field contents are written
    verbatim from the JSON — per CLAUDE.md's factuality rule, whoever edits
    bank_earnings.json is responsible for sourcing every quoted string.
    """
    if not BANK_FILE.exists():
        warnings.append('update_bank_cards: data/bank_earnings.json not found — skipping')
        return html

    bank_data = json.loads(BANK_FILE.read_text(encoding='utf-8'))
    today = datetime.date.today().isoformat()

    new_entries = []
    reported = 0
    for b in bank_data.get('banks', []):
        actual = b.get('actual_report_date', '')
        expected = b.get('expected_report_date', '')
        status = (b.get('status') or '').lower()
        is_pending = (status == 'pending') or not actual or (expected > today and not actual)
        if not is_pending:
            reported += 1

        date_display = b.get('date') or expected or ''
        if is_pending and '(pending)' not in date_display.lower():
            date_display = f'{expected} (pending)' if expected else 'pending'

        entry = {}
        for k in _BANK_JS_FIELDS:
            if k == 'date':
                entry[k] = date_display
            elif k in b:
                entry[k] = b[k]
        new_entries.append(entry)

    # Tier 1 anti-clone migration: BANK_COMMENTARY served via /api/state.json.
    # Register payload and patch inline declaration to placeholder.
    _api_writer.register('BANK_COMMENTARY', new_entries)
    placeholder = 'let BANK_COMMENTARY = null;'  # boot loader hydrates from /api/state.json
    pattern = re.compile(r'(?:const|let|var)\s+BANK_COMMENTARY\s*=\s*(?:\[[\s\S]*?\n?\]|null)\s*;')
    new_html, n = re.subn(pattern, lambda m: placeholder, html, count=1)
    _record_subn_result('BANK_COMMENTARY', pattern, n)
    if n:
        applied.append(f'BANK_COMMENTARY registered to state.json ({len(new_entries)} banks, {reported} reported); inline zeroed')
        return new_html
    warnings.append('update_bank_cards: BANK_COMMENTARY pattern not matched')
    return html


def update_meta(html):
    today = datetime.date.today().strftime('%B %d, %Y')
    utc   = datetime.datetime.utcnow().strftime('%H:%M UTC')
    new_h = re.sub(
        r'(GitHub Actions — Cron trigger: ).*?(?=</span>|<)',
        rf'\g<1>Weekly Sat 8am ET + Monthly 2nd Sat — Last run: {today} {utc}',
        html, count=1
    )
    if new_h != html: applied.append('trigger_timestamp'); html = new_h
    return html


def render_macro_state(html, sig):
    """Patch the MACRO_STATE JS constant from data/signals.json.

    Synthesises a one-line verdict + 4-bar scorecard (Growth / Labor /
    Inflation / Credit) so the Outlook tab opens with a CEO-grade
    above-the-fold answer to "is it good or bad?". Scoring is
    deterministic from the signals.json contract — no LLM call here.
    """
    vals = sig.get('values', {}) or {}
    sigs = sig.get('signals', {}) or {}
    risk_level = (sig.get('risk_level') or 'MEDIUM').upper()
    alerts = sig.get('alert_count', 0)
    watches = sig.get('watch_count', 0)

    def _status(score):
        return 'good' if score >= 66 else 'watch' if score >= 33 else 'stress'

    # ── Growth: anchored on GDP + NFP slope ──
    gdp = vals.get('gdp_yoy') or vals.get('gdp_growth') or 2.0
    nfp = vals.get('nfp_mom') or vals.get('payrolls') or 0
    growth_score = max(0, min(100, int(50 + (float(gdp) - 1.5) * 25)))

    # ── Labor: unrate (lower=better) + wages direction ──
    unrate = float(vals.get('unrate', 4.3))
    wages = float(vals.get('wages_yoy', 3.6))
    labor_score = max(0, min(100, int(70 - (unrate - 4.0) * 20 + (wages - 3.0) * 5)))

    # ── Inflation: distance from 2% target, both sides bad ──
    cpi = float(vals.get('cpi_yoy', 3.0))
    core_pce = float(vals.get('core_pce_yoy', 3.0))
    infl_gap = max(abs(cpi - 2.0), abs(core_pce - 2.0))
    infl_score = max(0, min(100, int(80 - infl_gap * 25)))

    # ── Credit: HY OAS + card delinquency ──
    hy = float(vals.get('hy_oas', 350))
    card = float(vals.get('cc_delinq', 8.0))
    credit_score = max(0, min(100, int(80 - (hy - 300) / 10 - (card - 6) * 5)))

    # ── Verdict line (deterministic, no fabrication) ──
    chip = 'HIGH' if risk_level == 'HIGH' else 'MEDIUM' if risk_level == 'MEDIUM' else 'LOW'
    tone = {
        'HIGH':   'Late-cycle: soft-landing path intact, but inflation re-accelerated and credit stress is building beneath the surface.',
        'MEDIUM': 'Mid-cycle: growth and labor holding, inflation easing slowly, credit stable for now.',
        'LOW':    'Expansion: growth, labor, and inflation all inside their target bands.',
    }.get(risk_level, 'Mixed signals across the four pillars.')

    asof = datetime.date.today().strftime('%b %Y')

    # Tier 1 anti-clone migration: MACRO_STATE served via /api/state.json.
    # Build the dict directly so it can be registered as JSON; the inline
    # declaration becomes a `let MACRO_STATE = null;` placeholder.
    payload = {
        'asof': asof,
        'risk': chip,
        'verdict': tone,
        'bars': [
            {'label': 'Growth',    'score': growth_score, 'status': _status(growth_score), 'detail': f'GDP {gdp:.1f}% \u00b7 NFP slope'},
            {'label': 'Labor',     'score': labor_score,  'status': _status(labor_score),  'detail': f'Unrate {unrate:.1f}% \u00b7 wages {wages:.1f}%'},
            {'label': 'Inflation', 'score': infl_score,   'status': _status(infl_score),   'detail': f'CPI {cpi:.2f}% \u00b7 Core PCE {core_pce:.1f}%'},
            {'label': 'Credit',    'score': credit_score, 'status': _status(credit_score), 'detail': f'Card DPD {card:.1f}% \u00b7 HY OAS {int(hy)}bp'},
        ],
    }
    _api_writer.register('MACRO_STATE', payload)

    placeholder = 'let MACRO_STATE = null;'  # boot loader hydrates from /api/state.json
    # Accept legacy multi-line literal AND the new placeholder (idempotent).
    pattern = re.compile(r'(?:const|let|var)\s+MACRO_STATE\s*=\s*(?:\{.*?\n\}|null)\s*;', re.S)
    new_html, n = pattern.subn(lambda m: placeholder, html, count=1)
    if n == 1:
        applied.append('MACRO_STATE registered to state.json; inline zeroed')
        return new_html
    return html


def render_what_changed(html, sig):
    """Patch WHAT_CHANGED JS const with top-3 WoW moves from signals.json.

    Selection: |delta| ranks all flagged + non-flagged signals; alerted
    items get a 2x score multiplier, watched get 1.5x. The top 3 are
    emitted with a human label, signed delta, unit, direction, tone,
    and a deterministic one-line note (note table is keyed on signal
    id — no LLM call).
    """
    sigs = (sig or {}).get('signals', {}) or {}
    if not isinstance(sigs, dict) or not sigs:
        return html

    # Per-signal metadata: label, unit, formatter, default note.
    META = {
        'wti':           ('WTI Crude',      '/bbl',  lambda d: f'{d:+.2f}',  'Oil shock chain extending'),
        'gasoline':      ('Gasoline',       '/gal',  lambda d: f'{d:+.2f}',  'Pump prices flowing through'),
        'dgs10':         ('10Y Treasury',   'bp',    lambda d: f'{int(round(d*100)):+d}', 'Term premium re-pricing'),
        'dgs2':          ('2Y Treasury',    'bp',    lambda d: f'{int(round(d*100)):+d}', 'Front-end repricing'),
        'ffr':           ('Fed Funds',      'bp',    lambda d: f'{int(round(d*100)):+d}', 'Policy stance shift'),
        'hy_oas':        ('HY OAS',         'bp',    lambda d: f'{int(round(d)):+d}',     'Credit risk repricing'),
        'ig_oas':        ('IG OAS',         'bp',    lambda d: f'{int(round(d)):+d}',     'Investment-grade spreads moving'),
        'cpi_yoy':       ('CPI YoY',        'pp',    lambda d: f'{d:+.1f}',  'Headline inflation print'),
        'core_pce_yoy':  ('Core PCE YoY',   'pp',    lambda d: f'{d:+.1f}',  'Fed-preferred gauge'),
        'core_cpi_yoy':  ('Core CPI YoY',   'pp',    lambda d: f'{d:+.1f}',  'Sticky inflation reading'),
        'unrate':        ('Unemployment',   'pp',    lambda d: f'{d:+.1f}',  'Labor market repricing'),
        'wages_yoy':     ('Wages YoY',      'pp',    lambda d: f'{d:+.1f}',  'Cooling labor market'),
        'jolts':         ('Job Openings',   'k',     lambda d: f'{int(round(d)):+d}', 'Labor demand shift'),
        'umcsent':       ('UMich Sentiment','pts',   lambda d: f'{d:+.1f}',  'Consumer mood shift'),
        'retail_yoy':    ('Retail Sales',   'pp',    lambda d: f'{d:+.1f}',  'Consumer spending pulse'),
        'tdsp':          ('Debt Service',   'pp',    lambda d: f'{d:+.2f}',  'Household debt burden'),
        'cc_delinq':     ('Card DPD',       'pp',    lambda d: f'{d:+.1f}',  'Consumer credit stress'),
        'saving_rate':   ('Saving Rate',    'pp',    lambda d: f'{d:+.1f}',  'Household savings buffer'),
    }

    # Per-signal natural-scale denominators used to convert raw |delta|
    # into a comparable cross-series score. Without this, ICSA (22k
    # claims) would always dominate WTI ($2.49/bbl) on raw magnitude.
    SCALE = {
        'wti': 1.0, 'gasoline': 0.05,
        'dgs10': 0.05, 'dgs2': 0.05, 'ffr': 0.05,
        'hy_oas': 25.0, 'ig_oas': 10.0,
        'cpi_yoy': 0.1, 'core_pce_yoy': 0.1, 'core_cpi_yoy': 0.1,
        'unrate': 0.1, 'wages_yoy': 0.2,
        'jolts': 200.0, 'umcsent': 2.0, 'retail_yoy': 0.3,
        'tdsp': 0.1, 'cc_delinq': 0.2, 'saving_rate': 0.3,
    }

    candidates = []
    for sid, s in sigs.items():
        if not isinstance(s, dict):
            continue
        # Gate: only emit signals we have a META entry for (so labels
        # and units are guaranteed). Skips raw series like 'icsa' that
        # would otherwise outrank narrative-relevant moves.
        if sid not in META:
            continue
        delta = s.get('delta', 0)
        try:
            d = float(delta)
        except Exception:
            continue
        if d == 0:
            continue
        alert = (s.get('alert') or '').lower()
        mult = 2.0 if alert == 'alert' else 1.5 if alert == 'watch' else 1.0
        scale = SCALE.get(sid, 1.0)
        score = (abs(d) / scale) * mult
        candidates.append((score, sid, s, d, alert))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:3]

    items = []
    for _score, sid, s, d, alert in top:
        meta = META.get(sid)
        if meta:
            label, unit, fmt, note = meta
            try:
                delta_str = fmt(d)
            except Exception:
                delta_str = f'{d:+.2f}'
        else:
            label, unit, note = sid.replace('_', ' ').title(), '', 'WoW change'
            delta_str = f'{d:+.2f}'
        direction = 'up' if d > 0 else 'down' if d < 0 else 'flat'
        tone = 'alert' if alert == 'alert' else 'watch' if alert == 'watch' else 'ok'
        items.append({
            'label': label,
            'delta': delta_str,
            'unit':  unit,
            'dir':   direction,
            'tone':  tone,
            'note':  note,
        })

    if not items:
        # Don't emit a stale block — leave the existing placeholder intact.
        return html

    asof = datetime.date.today().strftime('vs prior weekly \u00b7 %b %Y')
    payload = {'asof': asof, 'items': items}

    _api_writer.register('WHAT_CHANGED', payload)
    pattern = re.compile(r'(?:const|let|var)\s+WHAT_CHANGED\s*=\s*(?:\{[\s\S]*?\}|null)\s*;', re.S)
    new_html, n = pattern.subn(lambda m: 'let WHAT_CHANGED = null;', html, count=1)
    if n == 1:
        applied.append(f'WHAT_CHANGED registered to state.json ({len(items)} items); inline zeroed')
        return new_html
    return html


def render_release_calendar(html):
    """Patch the RELEASE_CAL JS constant from data/release_calendar.json.

    Filters the hand-curated calendar to a [today, today+7d] window
    and emits the slice as a JS const. Client-side renderer builds
    a 7-cell horizontal strip (one cell per calendar day) at the
    top of the dashboard so the reader sees what's coming this week.

    The JSON file is human-maintained (refreshed quarterly); the
    pipeline never mutates it. Missing file = silent no-op (the
    placeholder const stays at its default empty value).
    """
    cal_file = ROOT / 'data' / 'release_calendar.json'
    if not cal_file.exists():
        warnings.append('render_release_calendar: data/release_calendar.json missing — skipping')
        return html

    try:
        cal = json.loads(cal_file.read_text(encoding='utf-8'))
    except Exception as e:
        warnings.append(f'render_release_calendar: bad JSON ({e}) — skipping')
        return html

    today = datetime.date.today()
    window_end = today + datetime.timedelta(days=6)  # inclusive 7-day window
    in_window = []
    for r in cal.get('releases', []):
        try:
            d = datetime.datetime.strptime(r.get('date', ''), '%Y-%m-%d').date()
        except Exception:
            continue
        if today <= d <= window_end:
            # Keep only the fields the client renders — drop free-form
            # notes and the maintainer comment block.
            in_window.append({
                'date':       r.get('date'),
                'time':       r.get('time', ''),
                'series':     r.get('series', ''),
                'title':      r.get('title', ''),
                'agency':     r.get('agency', ''),
                'importance': r.get('importance', 'low'),
            })
    # Stable sort: date asc, then time asc (string sort works for HH:MM ET)
    in_window.sort(key=lambda x: (x.get('date') or '', x.get('time') or ''))

    payload = {'today': today.isoformat(), 'window_end': window_end.isoformat(),
               'releases': in_window}

    _api_writer.register('RELEASE_CAL', payload)
    pattern = re.compile(r'(?:const|let|var)\s+RELEASE_CAL\s*=\s*(?:\{[\s\S]*?\}|null)\s*;')
    new_html, n = re.subn(pattern, 'let RELEASE_CAL = null;', html, count=1)
    _record_subn_result('RELEASE_CAL', pattern, n)
    if n:
        applied.append(f'RELEASE_CAL registered to state.json ({len(in_window)} releases in next 7d); inline zeroed')
        return new_html
    warnings.append('render_release_calendar: RELEASE_CAL placeholder not matched')
    return html


def render_wordmark(html):
    """Patch issue # + week label in the publication wordmark.

    Issue number = total weekly runs (from pipeline_version.json).
    Week label  = "WEEK {iso-week} {year}".
    """
    today = datetime.date.today()
    iso_week = today.isocalendar().week
    year = today.year

    issue_num = iso_week  # falls back to ISO week
    ver_file = ROOT / 'data' / 'pipeline_version.json'
    if ver_file.exists():
        try:
            v = json.loads(ver_file.read_text(encoding='utf-8'))
            if isinstance(v, dict):
                issue_num = v.get('total_runs', issue_num) or issue_num
        except Exception:
            pass

    # Replace issue chip
    new_h = re.sub(
        r'(id="sm-wm-issue">)[^<]*(</span>)',
        rf'\g<1>ISSUE {issue_num}\g<2>',
        html, count=1,
    )
    # Replace week chip — year omitted (already on the Macro/YY mark)
    new_h = re.sub(
        r'(id="sm-wm-week">)[^<]*(</span>)',
        rf'\g<1>WEEK {iso_week}\g<2>',
        new_h, count=1,
    )
    if new_h != html:
        applied.append('wordmark')
    return new_h


# ── MAIN ──────────────────────────────────────────────────────────────

def render():
    print('[Agent 4 — Renderer] Starting...')

    for f in (HTML_FILE, RAW_FILE, SIG_FILE):
        if not f.exists(): print(f'ERROR: {f.name} missing'); sys.exit(1)

    html = HTML_FILE.read_text(encoding='utf-8')
    raw  = json.loads(RAW_FILE.read_text())
    sig  = json.loads(SIG_FILE.read_text())
    ana  = json.loads(ANA_FILE.read_text()) if ANA_FILE.exists() else {}

    data = raw.get('data', {})
    vals = sig.get('values', {})
    tabs = ana.get('tabs', {})

    # Merge manual overrides (for data not yet on FRED)
    if OVR_FILE.exists():
        ovr = json.loads(OVR_FILE.read_text())
        for key, entries in ovr.items():
            series = data.get(key, [])
            existing_dates = {e['date'] for e in series}
            added = 0
            for entry in entries:
                if entry['date'] not in existing_dates:
                    series.insert(0, entry)
                    added += 1
            if added:
                # Re-sort descending by date
                series.sort(key=lambda e: e['date'], reverse=True)
                data[key] = series
                print(f'  ✅ Override: added {added} entry(ies) to {key}')

    # Rebuild all chart arrays from historical data (2000+)
    try:
        html = rebuild_charts(html, data)
        print('  \u2705 Chart history rebuild')
    except Exception as e:
        errors.append(f'rebuild_charts: {e}')
        print(f'  \u274c Chart history rebuild: {e}')

    # Rebuild top KPI strip with MoM comparisons
    try:
        html = rebuild_kpi_strip(html, data, vals)
        print('  \u2705 KPI strip (MoM deltas)')
    except Exception as e:
        errors.append(f'rebuild_kpi_strip: {e}')
        print(f'  \u274c KPI strip: {e}')

    sections = [
        ('Rates/Yields', render_rates),
        ('Spreads',      render_spreads),
        ('Labor',        render_labor),
        ('Inflation',    render_inflation),
        ('Housing',      render_housing),
        ('Oil',          render_oil),
    ]
    for name, fn in sections:
        try:
            html = fn(html, data, vals, tabs)
            print(f'  \u2705 {name}')
        except Exception as e:
            errors.append(f'{name}: {e}')
            print(f'  \u274c {name}: {e}')

    if ana:
        try:
            html = render_outlook(html, ana)
            print('  \u2705 Outlook/KPIs')
        except Exception as e:
            errors.append(f'Outlook: {e}')

    try:
        html = update_bank_cards(html)
        print('  \u2705 Bank Earnings Cards')
    except Exception as e:
        errors.append(f'Bank Earnings: {e}')
        print(f'  \u274c Bank Earnings: {e}')

    html = update_meta(html)

    # ── Macro State hero card + publication wordmark ──
    # Both are patched from signals.json + pipeline_version.json so the
    # above-the-fold verdict and identity strip refresh weekly. Idempotent
    # regex patches; first failure logs but doesn't break the pipeline.
    try:
        html = render_macro_state(html, sig)
        print('  \u2705 Macro State hero card')
    except Exception as e:
        errors.append(f'Macro State: {e}')
        print(f'  \u274c Macro State: {e}')

    try:
        html = render_what_changed(html, sig)
        print('  \u2705 What-changed delta block')
    except Exception as e:
        errors.append(f'What-changed: {e}')
        print(f'  \u274c What-changed: {e}')

    try:
        html = render_release_calendar(html)
        print('  \u2705 Release calendar (7-day)')
    except Exception as e:
        errors.append(f'Release calendar: {e}')
        print(f'  \u274c Release calendar: {e}')

    try:
        html = render_wordmark(html)
        print('  \u2705 Wordmark (issue / week)')
    except Exception as e:
        errors.append(f'Wordmark: {e}')
        print(f'  \u274c Wordmark: {e}')

    # Write version.json and sync BUILD_V in index.html for cache-busting
    build_v = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    ver_file = ROOT / 'version.json'
    ver_file.write_text(json.dumps({"v": build_v}), encoding='utf-8')
    html = re.sub(r'var BUILD_V\s*=\s*"[^"]*"', f'var BUILD_V = "{build_v}"', html)

    # Tier 1 anti-clone: flush the registered state-bundle keys to
    # data/state.json. The /api/state.json serverless function reads
    # this file at request time. BUILD_V is exposed via env so the
    # bundle's _meta carries the same version stamp as index.html.
    try:
        os.environ['BUILD_V'] = build_v
        out = _api_writer.flush()
        ks = _api_writer.keys()
        applied.append(f'state.json flushed ({len(ks)} keys: {", ".join(ks) or "—"})')
        print(f'  \u2705 state.json \u2192 {out.relative_to(ROOT)} ({len(ks)} keys)')
    except Exception as e:
        errors.append(f'state.json flush: {e}')
        print(f'  \u274c state.json flush: {e}')

    # Cache-bust unfingerprinted static assets so browser caches don't serve
    # a stale theme-overlay.{js,css} after the file content changes on origin.
    # Idempotent: any existing ?v=... query string is replaced with the
    # current build_v.
    def _bust(mm):
        return f'{mm.group(1)}="{mm.group(2)}?v={build_v}"'
    html = re.sub(
        r'(href|src)="(theme-overlay\.(?:js|css))(?:\?v=[^"]*)?"',
        _bust,
        html,
    )

    # VALIDATION_REPORT is no longer inlined — dashboard fetches
    # data/validation_report.json at runtime (see METHODOLOGY.md §5).

    # NOTE: HTML_FILE.write_text(html) is intentionally deferred to __main__
    # AFTER the --strict gate has evaluated zero_replacement_errors. This way
    # a silent-injection failure in --strict mode no longer leaves a stale or
    # half-patched HTML on disk. Non-strict mode still writes unconditionally
    # because that's the legacy weekly cadence contract.

    # ── Revision detection: flag when source data changed key values ──
    revisions = []
    def _check_revision(label, computed, html_pattern):
        """Compare computed value against what's in the HTML after patching."""
        m = re.search(html_pattern, html)
        if m and computed is not None:
            in_html = float(m.group(1))
            if abs(in_html - computed) > 0.15:
                revisions.append(f'{label}: HTML={in_html}, Source={computed} (Δ={computed-in_html:+.1f})')

    # Check key indicators for revision drift
    for series_key, label in [('unrate', 'Unemployment'), ('cpi_all', 'CPI')]:
        s = data.get(series_key, [])
        if s:
            _check_revision(f'{label} latest', s[0]['value'],
                           rf'"val":"([\d.]+)%".*?"metric":"{label.lower()[:4]}"')
    prev_yr = datetime.date.today().year - 1
    wti_a = data.get('wti_annual', [])
    for obs in (wti_a if isinstance(wti_a, list) else []):
        if int(obs['date'][:4]) == prev_yr:
            _check_revision(f'WTI {prev_yr} avg', round(obs['value'], 1),
                           rf'Full Year {prev_yr} Avg[^}}]*val:"\$([\d.]+)"')

    if revisions:
        print(f'  🔄 REVISIONS DETECTED ({len(revisions)}):')
        for r in revisions:
            print(f'     → {r}')

    print(f'[Agent 4] Done — {len(applied)} patches, {len(errors)} errors, {len(warnings)} warnings | {len(html.encode("utf-8")):,} bytes (pending write)')
    for a in applied:  print(f'  ✅ {a}')
    for e in errors:   print(f'  ⚠  {e}')
    for w in warnings: print(f'  ℹ  {w}')

    # ── INJECTION SUMMARY (B-stability-1) ────────────────────────────────
    # Every re.subn call site is wired through _record_subn_result. The
    # summary below makes silent "0 replacements" injections visible in CI
    # logs even when not running with --strict. Non-strict behaviour is
    # unchanged — this is observability only.
    total_subn = subn_success_count + len(zero_replacement_errors)
    print('')
    print(f'[Agent 4] INJECTION SUMMARY — '
          f'{subn_success_count}/{total_subn} re.subn call sites applied >=1 replacement, '
          f'{len(zero_replacement_errors)} returned 0 replacements')
    if zero_replacement_errors:
        print('[Agent 4] Zero-replacement re.subn call sites (silent injection failures):')
        for z in zero_replacement_errors:
            print(f'  🛑 {z}')

    # Exit 1 only on hard errors, not on missing KPI labels
    hard_errors = [e for e in errors if 'missing' in e.lower() or 'ERROR' in e]
    return (len(hard_errors) == 0, html)


if __name__ == '__main__':
    # --strict: exit code 2 when any re.subn call site returned 0 replacements.
    # Wired in CI for the Agent 4b re-render step (post-validator) so silent
    # injection failures become hard build failures once the data layer is
    # known-good. The weekly Saturday CI Agent 4 step does NOT pass --strict
    # so any pre-validator JSON-shape drift surfaces as a SUMMARY warning
    # rather than blocking the cadence.
    #
    # HTML write ordering: render() now returns the patched HTML in-memory
    # without touching disk. We only commit to HTML_FILE AFTER the strict
    # gate decides — so a --strict failure leaves the previous good HTML
    # intact rather than landing a half-patched file. Non-strict runs still
    # write unconditionally (legacy weekly cadence behaviour).
    strict = '--strict' in sys.argv[1:]
    ok, html_out = render()
    if strict and zero_replacement_errors:
        print(f'[Agent 4] --strict gate FAILED — {len(zero_replacement_errors)} '
              f'silent injection failure(s) listed above. Exiting 2 WITHOUT '
              f'writing index.html — previous version preserved on disk.')
        sys.exit(2)
    HTML_FILE.write_text(html_out, encoding='utf-8')
    print(f'[Agent 4] index.html written — {HTML_FILE.stat().st_size:,} bytes')
    sys.exit(0 if ok else 1)
