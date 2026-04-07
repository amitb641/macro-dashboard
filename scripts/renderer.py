#!/usr/bin/env python3
"""
Agent 4 — RENDERER  (renderer.py)
Reads raw_data.json + analysis.json.
Patches index.html: chart arrays, KPIs, tab commentary.
No LLM. Output: index.html (updated in-place).
"""

import os, re, json, datetime, math, sys
from pathlib import Path


ROOT      = Path(__file__).parent.parent
HTML_FILE = ROOT / 'index.html'
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SIG_FILE  = ROOT / 'data' / 'signals.json'
ANA_FILE  = ROOT / 'data' / 'analysis.json'
OVR_FILE  = ROOT / 'data' / 'overrides.json'
VAL_FILE  = ROOT / 'data' / 'validation_report.json'

applied  = []
errors   = []
warnings = []

START_YEAR = 2000   # all charts start from this year


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


def _monthly_yoy_series(monthly_series, n_months=12):
    """Compute YoY% for the last n_months from monthly index data (newest-first).
    Returns (labels, values) where labels are "Mon'YY" strings."""
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


def _monthly_avg_by_month(weekly_series, n_months=12):
    """Compute monthly averages from weekly data (newest-first).
    Returns (labels, avg_values) for the last n_months complete months."""
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


def _inject_const(html, var_name, obj):
    """Replace const VAR_NAME = {...}; in HTML with new data."""
    new_json = json.dumps(obj, separators=(', ', ':'))
    # Match from 'const VAR_NAME = {' to next '};'
    pattern = rf'const {var_name}\s*=\s*\{{[\s\S]*?\}};'
    new_decl = f'const {var_name} = {new_json};'
    # Use lambda to avoid regex interpreting \u escapes in replacement
    new_html, n = re.subn(pattern, lambda m: new_decl, html, count=1)
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


def rebuild_charts(html, data):
    """Rebuild all chart arrays from collected historical data (from 2000)."""
    today = datetime.date.today()

    # ── U_ANNUAL (annual averages only — monthly shown in U_MONTHLY) ──
    unrate = data.get('unrate', [])
    if len(unrate) >= 60:
        labels, values = _annual_avg(unrate)
        if labels:
            html = _inject_const(html, 'U_ANNUAL', {'labels': labels, 'data': values})

    # ── CPI_ANNUAL (Dec-to-Dec only — monthly shown in CPI_MONTHLY) ───
    cpi_all = data.get('cpi_all', [])
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
    pce = data.get('pce', [])
    pce_core = data.get('pce_core', [])
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
    ahetpi = data.get('ahetpi', [])
    if len(ahetpi) >= 60 and len(cpi_all) >= 60:
        w_labels, w_values = _dec_yoy(ahetpi)
        c_labels, c_values = _dec_yoy(cpi_all)
        labels, nominal, real = [], [], []
        for l in w_labels:
            if l in c_labels:
                n = w_values[w_labels.index(l)]
                c = c_values[c_labels.index(l)]
                labels.append(l)
                nominal.append(n)
                real.append(round(n - c, 1))
        # Annual only — monthly shown in WAGE_MONTHLY
        if labels:
            html = _inject_const(html, 'WAGE_ANNUAL', {
                'labels': labels, 'nominal': nominal, 'real': real})

    # ── JOBS_ANNUAL ───────────────────────────────────────────────────
    payems = data.get('payems', [])
    if len(payems) >= 60:
        by_ym = {}
        for obs in payems:
            yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
            by_ym[(yr, mo)] = obs['value']
        labels, values, low, high = [], [], [], []
        for yr in sorted(set(y for y, m in by_ym if y >= START_YEAR and y < today.year)):
            dec_cur = by_ym.get((yr, 12))
            dec_prev = by_ym.get((yr - 1, 12))
            if dec_cur is not None and dec_prev is not None:
                labels.append(str(yr))
                values.append(round(dec_cur - dec_prev))
                low.append(None)
                high.append(None)
        if labels:
            html = _inject_const(html, 'JOBS_ANNUAL', {
                'labels': labels, 'data': values, 'low': low, 'high': high})

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
            labels[-1] = d.strftime("%-d %b'%y")  # e.g. "8 Mar'26"
        if labels:
            html = _inject_const(html, 'CLAIMS_WEEKLY', {
                'labels': labels, 'initial': initial, 'continued': continued})

    # ── SAVING_ANNUAL (annual averages from 2000) ─────────────────────
    psavert = data.get('psavert', [])
    if len(psavert) >= 60:
        labels, values = _annual_avg(psavert)
        if labels:
            html = _inject_const(html, 'SAVING_ANNUAL', {'labels': labels, 'data': values})

    # ── SAVING_MONTHLY (last 12 months) ──────────────────────────────
    if len(psavert) >= 12:
        monthly = sorted(psavert[:12], key=lambda x: x['date'])  # oldest-first for chart
        m_labels = [_month_lbl(o['date']) for o in monthly]
        m_values = [round(o['value'], 1) for o in monthly]
        html = _inject_const(html, 'SAVING_MONTHLY', {'labels': m_labels, 'data': m_values})

    # ── UMCSENT_MONTHLY (last 12 months) ────────────────────────────
    umcsent = data.get('umcsent', [])
    if len(umcsent) >= 12:
        monthly = sorted(umcsent[:12], key=lambda x: x['date'])  # oldest-first for chart
        m_labels = [_month_lbl(o['date']) for o in monthly]
        m_values = [round(o['value'], 1) for o in monthly]
        html = _inject_const(html, 'UMCSENT_MONTHLY', {'labels': m_labels, 'data': m_values})

    # ── GDP_TOTAL_DATA ────────────────────────────────────────────────
    gdpc1_a = data.get('gdpc1_annual', [])
    gdp_a = data.get('gdp_annual', [])
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
        h_labels, h_values = _monthly_yoy_series(cpi_all_m, 12)
        c_labels, c_values = _monthly_yoy_series(cpi_core_m, 12)
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
        h_labels, h_values = _monthly_yoy_series(pce_m, 12)
        c_labels, c_values = _monthly_yoy_series(pce_core_m, 12)
        if h_labels and h_labels == c_labels:
            html = _inject_const(html, 'PCE_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values})
        elif h_labels:
            html = _inject_const(html, 'PCE_MONTHLY', {
                'labels': h_labels, 'headline': h_values, 'core': c_values[:len(h_values)]})

    # ── U_MONTHLY (rolling 12-month unemployment rate) ────────────────
    unrate_m = data.get('unrate', [])
    if len(unrate_m) >= 12:
        # Unemployment rate is already a rate, not an index — no YoY needed
        labels_u, values_u = [], []
        for i in range(min(12, len(unrate_m))):
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
        cs_labels, cs_values = _monthly_yoy_series(cs_hpi_m, 12)
        # Get monthly-averaged mortgage rates
        mtg_labels, mtg_values = _monthly_avg_by_month(mortgage30_m, 12)
        # Align to Case-Shiller labels (CS has pub lag, mortgage is more current)
        if cs_labels:
            # Use CS labels as base; fill mortgage where available
            mtg_by_lbl = dict(zip(mtg_labels, mtg_values))
            mtg_aligned = [mtg_by_lbl.get(l, None) for l in cs_labels]
            # If CS is shorter than mortgage, extend with mortgage-only months
            extra_mtg_labels = [l for l in mtg_labels if l not in cs_labels]
            all_labels = cs_labels + extra_mtg_labels
            all_cs = cs_values + [cs_values[-1]] * len(extra_mtg_labels)  # hold last CS value
            all_mtg = mtg_aligned + [mtg_by_lbl[l] for l in extra_mtg_labels]
            html = _inject_const(html, 'HOUSING_MONTHLY', {
                'labels': all_labels,
                'caseShiller': all_cs,
                'mortgage30': all_mtg})

    # ── SPREADS_DATA ──────────────────────────────────────────────────
    ig_a = data.get('ig_oas_annual', [])
    hy_a = data.get('hy_oas_annual', [])
    if ig_a and hy_a:
        i_labels, i_values = _annual_from_freq(ig_a, precision=0)
        h_labels, h_values = _annual_from_freq(hy_a, precision=0)
        common = [l for l in i_labels if l in h_labels]
        ig = [int(i_values[i_labels.index(l)]) for l in common]
        hy = [int(h_values[h_labels.index(l)]) for l in common]
        # Append latest daily value
        ig_latest = data.get('ig_oas')
        hy_latest = data.get('hy_oas')
        if ig_latest and hy_latest:
            common.append(today.strftime("%b'%y"))
            ig.append(round(ig_latest.get('value', 0)))
            hy.append(round(hy_latest.get('value', 0)))
        if common:
            html = _inject_const(html, 'SPREADS_DATA', {
                'labels': common, 'ig': ig, 'hy': hy})

    # ── OIL_ANNUAL ────────────────────────────────────────────────────
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
    if wti_a and hy_a:
        w_labels, w_values = _annual_from_freq(wti_a, precision=0)
        h_labels, h_values = _annual_from_freq(hy_a, precision=0)
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

    # ── NFP_VS_ADP (BLS side only — ADP is manually maintained) ────
    payems = data.get('payems', [])
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
            bls_json = json.dumps({'labels': nfp_labels, 'bls': nfp_bls}, separators=(', ', ':'))
            pattern = r'const NFP_BLS_MOM\s*=\s*\{[\s\S]*?\};'
            new_decl = f'const NFP_BLS_MOM = {bls_json};'
            new_html, n = re.subn(pattern, lambda m: new_decl, html, count=1)
            if n:
                applied.append(f'NFP_BLS_MOM rebuilt ({len(nfp_labels)} months)')
                html = new_html

            # Also update BLS side of NFP_VS_ADP (12-month chart, preserving ADP)
            bls_12 = nfp_bls[-12:]
            lbl_12 = nfp_labels[-12:]
            # Extract existing ADP array from HTML to preserve it
            adp_match = re.search(r'const NFP_VS_ADP\s*=\s*\{[^}]*adp:\s*\[([^\]]*)\]', html)
            if adp_match:
                adp_str = adp_match.group(1).strip()
                new_vs = (f'const NFP_VS_ADP = {{\n'
                          f'  labels:{json.dumps(lbl_12)},\n'
                          f'  bls:   {json.dumps(bls_12)},\n'
                          f'  adp:   [{adp_str}]')
                pattern_vs = r'const NFP_VS_ADP\s*=\s*\{[^}]*adp:\s*\[[^\]]*\]'
                new_html2, n2 = re.subn(pattern_vs, new_vs, html, count=1)
                if n2:
                    applied.append(f'NFP_VS_ADP.bls updated ({len(bls_12)} months, ADP preserved)')
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

        # Read existing SECTOR_MOM sectors list from HTML
        sm_match = re.search(r'const SECTOR_MOM\s*=\s*\{', html)
        if sm_match and sector_mom_data:
            # Get the sector order from current HTML
            sectors_match = re.search(
                r'const SECTOR_MOM\s*=\s*\{[^}]*sectors:\s*\[([^\]]*)\]', html)
            if sectors_match:
                import ast
                try:
                    sector_names = ast.literal_eval('[' + sectors_match.group(1) + ']')
                except Exception:
                    sector_names = []

                if sector_names:
                    # Determine month keys from data
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
                        new_sm = (f'const SECTOR_MOM = {{\n'
                                  f'  sectors:{json.dumps(sector_names)},\n'
                                  f'  {prev_key}:  {json.dumps(prev_vals)},\n'
                                  f'  {cur_key}:  {json.dumps(cur_vals)}\n'
                                  f'}};')
                        pattern_sm = r'const SECTOR_MOM\s*=\s*\{[\s\S]*?\};'
                        new_html3, n3 = re.subn(pattern_sm, lambda m: new_sm, html, count=1)
                        if n3:
                            applied.append(f'SECTOR_MOM rebuilt ({updated_count} sectors, {prev_key} & {cur_key})')
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
                if n4:
                    updated_sectors += 1
                    html = new_html4
        if updated_sectors:
            applied.append(f'JOBS_SECTORS.{yr_key} updated ({updated_sectors} sectors)')

    # ── FC_MACRO actuals (auto-update from FRED data) ─────────────────
    # FC_MACRO.act25 = [Real GDP %, Unemployment %, CPI %, Wage Growth %, FFR %]
    prev_yr = datetime.date.today().year - 1
    act_key = f'act{str(prev_yr)[2:]}'  # e.g. "act25"
    fc_vals = []
    # 1. Real GDP — use latest annual from gdp_real series if available
    gdp_r = data.get('gdp_real_annual', data.get('gdp_real', []))
    gdp_val = None
    for obs in (gdp_r if isinstance(gdp_r, list) else []):
        if int(obs['date'][:4]) == prev_yr:
            gdp_val = round(obs['value'], 1)
            break
    fc_vals.append(gdp_val)
    # 2. Unemployment — Dec of prev_yr
    unrate_s = data.get('unrate', [])
    u_val = None
    for obs in unrate_s:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        if yr == prev_yr and mo == 12:
            u_val = round(obs['value'], 1)
            break
    fc_vals.append(u_val)
    # 3. CPI — Dec YoY
    cpi_s = data.get('cpi_all', [])
    cpi_by_ym = {}
    for obs in cpi_s:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        cpi_by_ym[(yr, mo)] = obs['value']
    cpi_dec = cpi_by_ym.get((prev_yr, 12))
    cpi_dec_prev = cpi_by_ym.get((prev_yr - 1, 12))
    cpi_val = round((cpi_dec - cpi_dec_prev) / cpi_dec_prev * 100, 1) if cpi_dec and cpi_dec_prev else None
    fc_vals.append(cpi_val)
    # 4. Wage Growth — Dec YoY from AHETPI
    ahetpi_s = data.get('ahetpi', [])
    ahe_by_ym = {}
    for obs in ahetpi_s:
        yr, mo = int(obs['date'][:4]), int(obs['date'][5:7])
        ahe_by_ym[(yr, mo)] = obs['value']
    ahe_dec = ahe_by_ym.get((prev_yr, 12))
    ahe_dec_prev = ahe_by_ym.get((prev_yr - 1, 12))
    wage_val = round((ahe_dec - ahe_dec_prev) / ahe_dec_prev * 100, 1) if ahe_dec and ahe_dec_prev else None
    fc_vals.append(wage_val)
    # 5. Fed Funds Rate — annual average
    ffr_s = data.get('ffr_monthly', data.get('ffr_annual', []))
    ffr_vals_yr = []
    for obs in (ffr_s if isinstance(ffr_s, list) else []):
        if int(obs['date'][:4]) == prev_yr:
            ffr_vals_yr.append(obs['value'])
    ffr_val = round(sum(ffr_vals_yr) / len(ffr_vals_yr), 1) if ffr_vals_yr else None
    fc_vals.append(ffr_val)
    # Only update if we have at least 3 non-None values
    non_none = [v for v in fc_vals if v is not None]
    if len(non_none) >= 3:
        # Build the replacement array, keeping existing values for None entries
        existing_match = re.search(rf'{re.escape(act_key)}:\s*\[([^\]]+)\]', html)
        if existing_match:
            existing_vals = [float(v.strip()) for v in existing_match.group(1).split(',')]
            final_vals = [fc_vals[i] if fc_vals[i] is not None else existing_vals[i]
                         for i in range(min(len(fc_vals), len(existing_vals)))]
            new_arr = ', '.join(str(v) for v in final_vals)
            pat_fc = rf'({re.escape(act_key)}:\s*\[)[^\]]+(\])'
            new_html5, n5 = re.subn(pat_fc, rf'\g<1>{new_arr}\2', html, count=1)
            if n5:
                applied.append(f'FC_MACRO.{act_key} updated {final_vals}')
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
        if n6:
            applied.append(f'Oil tile WTI {prev_yr} avg → ${wti_prev_avg}')
            html = new_html6
    if brent_prev_avg is not None:
        pat_brent_tile = rf'(lbl:"Brent {prev_yr} Avg"[^}}]*val:")(\$[\d.]+)(")'
        new_html7, n7 = re.subn(pat_brent_tile, rf'\g<1>${brent_prev_avg}\3', html, count=1)
        if n7:
            applied.append(f'Oil tile Brent {prev_yr} avg → ${brent_prev_avg}')
            html = new_html7

    # ── Category MoM auto-rebuilders ─────────────────────────────────
    html = rebuild_u_sector_mom(html, data)
    html = rebuild_cpi_cat_mom(html, data)
    html = rebuild_treasury_data(html, data)
    html = rebuild_oil_prod_spread(html, data)

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
    if n: applied.append(f'{js_key}[-1]={fmt}')
    else: errors.append(f'patch_array_last: {js_key} not found')
    return new_html


def patch_kpi(html, label, val, sub=None):
    pat = rf'(\{{lbl:"{re.escape(label)}"[^}}]*?val:")[^"]*(")'
    new_html, n = re.subn(pat, rf'\g<1>{val}\2', html)
    if n:
        applied.append(f'kpi.{label}={val}')
        if sub:
            pat2 = rf'(lbl:"{re.escape(label)}"[^}}]*?sub:")[^"]*(")'
            new_html, _ = re.subn(pat2, rf'\g<1>{sub}\2', new_html)
    else:
        errors.append(f'patch_kpi: "{label}" not found')
    return new_html


def patch_kpi_full(html, old_label, new_label, val, sub=None):
    """Update both the label text AND value of a KPI card in one pass."""
    # Extract base prefix (e.g. "Core PCE" from "Core PCE Dec 2025")
    # Try exact match first, then fuzzy match on base prefix
    pat = rf'(\{{lbl:"){re.escape(old_label)}(")'
    new_html, n = re.subn(pat, rf'\g<1>{new_label}\2', html)
    if not n:
        # Fuzzy: match any label starting with the same base words
        # e.g. "Core PCE Dec 2025" base = "Core PCE" matches "Core PCE Dec'25"
        base = re.split(r'\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})', old_label)[0].strip()
        if base and len(base) > 3:
            fuzzy_pat = rf'(\{{lbl:"){re.escape(base)}[^"]*(")'
            new_html, n = re.subn(fuzzy_pat, rf'\g<1>{new_label}\2', html, count=1)
    if n:
        applied.append(f'kpi.rename → "{new_label}"')
    # Then patch the value using the new label
    return patch_kpi(new_html, new_label, val, sub)


def patch_commentary(html, tab_id, text):
    marker = f'id="commentary-{tab_id}"'
    if marker not in html: return html
    pat = rf'({re.escape(marker)}[^>]*>)(.*?)(</div>)'
    new_html, n = re.subn(pat, rf'\g<1>{text}\g<3>', html, count=1, flags=re.DOTALL)
    if n: applied.append(f'commentary.{tab_id}')
    return new_html


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
    new_html, n = re.subn(
        r'(const OIL_DAILY\s*=\s*)\{[^;]*\}(\s*;)',
        lambda m: m.group(1) + new_data + m.group(2),
        html, count=1, flags=re.DOTALL
    )
    if n:
        applied.append('OIL_DAILY (%d sessions, %s)' % (
            oil_daily.get('sessions', 0), oil_daily.get('month', '')))
    else:
        errors.append('inject_oil_daily: OIL_DAILY const not found')

    # Also patch the static panel title so it reflects the current month
    month = oil_daily.get('month', '')
    if month:
        new_html, m = re.subn(
            r'(<div class="panel-title">)\w+ \d{4} — Daily Closes \(Live\)(</div>)',
            lambda x: x.group(1) + month + ' — Daily Closes (Live)' + x.group(2),
            new_html, count=1
        )
        if m:
            applied.append('oil panel title → %s' % month)
        else:
            warnings.append('inject_oil_daily: panel title pattern not found')

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
            month_key = datetime.datetime.strptime(cur_date, '%Y-%m-%d').strftime('%b').lower()
            results.append({'month_key': month_key, 'yoy': yoy, 'date': cur_date})
    return results


def rebuild_u_sector_mom(html, data):
    """Rebuild U_SECTOR_MOM from BLS CPS sector unemployment data."""
    bls_unemp = data.get('bls_unemp_sectors', {})
    if not bls_unemp:
        return html

    SECTOR_MAP = {
        'LNS14032200': 'Construction',
        'LNS14033260': 'Hotel & Lodging',
        'LNS14033270': 'Restaurant Workers',
        'LNS14032500': 'Retail Trade',
        'LNS14032800': 'Information/Tech',
        'LNS14032600': 'Transport & Warehousing',
        'LNS14032300': 'Manufacturing',
        'LNS14033000': 'Prof. & Biz Services',
        'LNS14032100': 'Agriculture & Mining',
        'LNS14032400': 'Wholesale Trade',
        'LNS14033100': 'Healthcare & Education',
        'LNS14032900': 'Financial Activities',
        'LNS14033400': 'Government',
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

        new_obj = (f'const U_SECTOR_MOM = {{\n'
                   f'  sectors:{json.dumps(sector_names)},\n'
                   f'  {prv_k}: {json.dumps(prv_vals)},\n'
                   f'  {cur_k}: {json.dumps(cur_vals)}\n'
                   f'}};')
        pattern = r'const U_SECTOR_MOM\s*=\s*\{[\s\S]*?\};'
        new_html, n = re.subn(pattern, new_obj, html, count=1)
        if n:
            applied.append(f'U_SECTOR_MOM rebuilt ({len(sector_data)} sectors, {prv_k}/{cur_k})')
            html = new_html

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
        ('Energy (all)',        'cpi_energy',    '#FFB84C'),
        ('Used Cars & Trucks',  'cpi_used_cars', '#00C9A7'),
    ]

    entries = []
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

    if len(entries) >= 8:
        new_json = json.dumps(entries, separators=(', ', ':'))
        pattern = r'const CPI_CAT_MOM\s*=\s*\[[\s\S]*?\];'
        new_html, n = re.subn(pattern, f'const CPI_CAT_MOM = {new_json};', html, count=1)
        if n:
            keys = [k for k in entries[0] if k not in ('cat', 'color')]
            applied.append(f'CPI_CAT_MOM rebuilt ({len(entries)} cats, {"/".join(keys)})')
            html = new_html

    return html


def rebuild_treasury_data(html, data):
    """Rebuild TREASURY_DATA with annual DGS10/DGS2 averages + latest daily."""
    dgs10_ann = data.get('dgs10_annual', [])
    dgs2_ann = data.get('dgs2_annual', [])
    if not dgs10_ann or not dgs2_ann:
        # Fall back to computing from daily history
        return html

    today = datetime.date.today()
    t10_labels, t10_vals = _annual_from_freq(dgs10_ann, precision=2)
    t2_labels, t2_vals = _annual_from_freq(dgs2_ann, precision=2)

    if not t10_labels:
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

    # Card 90+ DPD — preserve existing values (NY Fed quarterly, not in FRED)
    # Extract from current HTML
    card90_match = re.search(r'"card90":\s*\[([^\]]*)\]', html)
    card90 = []
    if card90_match:
        import ast as _ast
        try:
            card90 = _ast.literal_eval(f'[{card90_match.group(1)}]')
        except Exception:
            card90 = []
    # Pad/trim card90 to match labels length
    while len(card90) < len(common):
        card90.append(card90[-1] if card90 else None)
    card90 = card90[:len(common)]

    obj = {'labels': common, 'dgs10': dgs10, 'dgs2': dgs2, 'spread': spread, 'card90': card90}
    new_json = json.dumps(obj, separators=(', ', ':'))
    pattern = r'const TREASURY_DATA\s*=\s*\{[^;]*\};'
    new_html, n = re.subn(pattern, f'const TREASURY_DATA = {new_json};', html, count=1)
    if n:
        applied.append(f'TREASURY_DATA rebuilt ({len(common)} points, latest {common[-1]})')
        html = new_html
    return html


def rebuild_oil_prod_spread(html, data):
    """Rebuild OIL_SPREAD from existing annual WTI/Brent data."""
    wti_a = data.get('wti_annual', [])
    brent_a = data.get('brent_annual', [])
    if not wti_a or not brent_a:
        return html

    w_labels, w_vals = _annual_from_freq(wti_a, start_year=2015, precision=1)
    b_labels, b_vals = _annual_from_freq(brent_a, start_year=2015, precision=1)
    common = [l for l in w_labels if l in b_labels]
    if not common:
        return html

    wti = [w_vals[w_labels.index(l)] for l in common]
    brent = [b_vals[b_labels.index(l)] for l in common]
    spread = [round(w - b, 1) for w, b in zip(wti, brent)]

    obj = {'labels': common, 'spread': spread}
    new_json = json.dumps(obj, separators=(', ', ':'))
    pattern = r'const OIL_SPREAD\s*=\s*\{[^;]*\};'
    new_html, n = re.subn(pattern, f'const OIL_SPREAD = {new_json};', html, count=1)
    if n:
        applied.append(f'OIL_SPREAD rebuilt ({len(common)} years)')
        html = new_html
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
        ahetpi_s = data.get('ahetpi')
        wages_date = ahetpi_s[0].get('date','') if ahetpi_s else ''
        wages_lbl = f"Nominal Wage Growth {month_label(wages_date)}" if wages_date else 'Nominal Wage Growth'
        html = patch_kpi_full(html, 'Nominal Wage Growth 2025', wages_lbl, f'{wages:+.1f}%')

    icsa_val = vals.get('icsa')
    if icsa_val is not None:
        icsa_s = data.get('icsa', [])
        icsa_date = icsa_s[0].get('date', '') if icsa_s else ''
        icsa_lbl = f"Initial Claims {month_label(icsa_date)}" if icsa_date else 'Initial Claims'
        html = patch_kpi_full(html, 'Initial Claims', icsa_lbl, f'{icsa_val/1000:.0f}K')

    # ── Auto-update Unemployment tab month references ──────────────
    unrate_s = data.get('unrate', [])
    if unrate_s and len(unrate_s) >= 2:
        u_cur_d = unrate_s[0].get('date', '')
        u_prv_d = unrate_s[1].get('date', '')
        if u_cur_d and u_prv_d:
            u_cur = month_label(u_cur_d)
            u_prv = month_label(u_prv_d)
            u_prv_short = u_prv.split("'")[0]
            html = re.sub(
                r"(Change in unemployment rate vs prior month · BLS CPS · )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+",
                rf"\g<1>{u_cur} vs {u_prv}", html, count=1)
            html = re.sub(r"([A-Z][a-z]+'\d+) rate rose", f"{u_cur} rate rose", html, count=1)
            html = re.sub(r"([A-Z][a-z]+'\d+) rate fell", f"{u_cur} rate fell", html, count=1)
            applied.append(f'Unemployment tab month refs updated to {u_prv}/{u_cur}')

    # ── Auto-update Jobs tab month references ────────────────────────
    # The Jobs tab has hardcoded month names in titles, legends, and tiles.
    # Derive current and prior month labels from PAYEMS data.
    payems_s = data.get('payems', [])
    if payems_s and len(payems_s) >= 2:
        cur_date = payems_s[0].get('date', '')
        prev_date = payems_s[1].get('date', '')
        if cur_date and prev_date:
            cur_lbl = month_label(cur_date)    # e.g. "Mar'26"
            prev_lbl = month_label(prev_date)  # e.g. "Feb'26"
            cur_upper = cur_lbl.upper()        # e.g. "MAR'26"

            # Update sector chart title and subtitle
            html = re.sub(
                r'Monthly Job Change by Sector — [A-Z][a-z]+\'\d+ vs [A-Z][a-z]+\'\d+ \(thousands\)',
                f"Monthly Job Change by Sector — {prev_lbl} vs {cur_lbl} (thousands)",
                html, count=1)
            html = re.sub(
                r'(BLS CES major sector breakdown · month-over-month net payroll change · sorted by )[A-Z][a-z]+\'\d+',
                rf'\g<1>{cur_lbl}', html, count=1)

            # Update sector legend labels
            html = re.sub(
                r"([A-Z][a-z]+'\d+) improved vs [A-Z][a-z]+",
                f"{cur_lbl} improved vs {prev_lbl.split(chr(39))[0]}",
                html, count=1)
            html = re.sub(
                r"([A-Z][a-z]+'\d+) worsened vs [A-Z][a-z]+",
                f"{cur_lbl} worsened vs {prev_lbl.split(chr(39))[0]}",
                html, count=1)

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
    cpi_s = data.get('cpi_all', [])
    if cpi_s and len(cpi_s) >= 2:
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
            html = re.sub(r"([A-Z][a-z]+'\d+) accelerating", f"{c_cur} accelerating", html, count=1)
            html = re.sub(r"([A-Z][a-z]+'\d+) cooling", f"{c_cur} cooling", html, count=1)
            # Prior month legend label in CPI section — skip complex regex, not critical
            html = re.sub(
                r"(Monthly YoY % change by category\. )[A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+",
                rf"\g<1>{c_cur} vs {c_prv}", html, count=1)
            applied.append(f'CPI tab month refs updated to {c_prv}/{c_cur}')

    # ── Auto-update PCE tab month references ────────────────────────
    pce_s = data.get('pce', [])
    if pce_s and len(pce_s) >= 2:
        p_cur_d = pce_s[0].get('date', '')
        p_prv_d = pce_s[1].get('date', '')
        if p_cur_d and p_prv_d:
            p_cur = month_label(p_cur_d)
            p_prv = month_label(p_prv_d)
            html = re.sub(
                r"PCE by Category — MoM Change \([A-Z][a-z]+'\d+ vs [A-Z][a-z]+'\d+\)",
                f"PCE by Category — MoM Change ({p_cur} vs {p_prv})", html, count=1)
            html = re.sub(
                r"(Real PCE spending growth by category · sorted by )[A-Z][a-z]+'\d+",
                rf"\g<1>{p_cur}", html, count=1)
            # PCE legend labels — find within the PCE tab section only
            pce_section = html.find('PCE by Category')
            if pce_section > 0:
                chunk = html[pce_section:pce_section+2000]
                chunk = re.sub(r"([A-Z][a-z]+'\d+) accelerating", f"{p_cur} accelerating", chunk, count=1)
                chunk = re.sub(r"([A-Z][a-z]+'\d+) cooling", f"{p_cur} cooling", chunk, count=1)
                html = html[:pce_section] + chunk + html[pce_section+2000:]
            applied.append(f'PCE tab month refs updated to {p_prv}/{p_cur}')

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

    cpi_trans = 5.8  # CPI Transport Svcs baseline (Feb'26 from CPI_CAT_MOM)
    cpi_energy_yoy = None
    cpieng = data.get('cpiengsl', [])
    if cpieng and len(cpieng) >= 13:
        cur = cpieng[0]
        target_mo = f"{int(cur['date'][:4])-1}{cur['date'][4:7]}"
        ya = [o for o in cpieng if o['date'][:7] == target_mo]
        if ya:
            cpi_energy_yoy = round((cur['value'] - ya[0]['value']) / ya[0]['value'] * 100, 1)

    core_cpi = vals.get('core_cpi_yoy', 2.5)
    food_away = 3.4  # baseline from CPI_CAT_MOM
    umcsent = vals.get('umcsent', 56.6)
    saving = vals.get('saving_rate', 4.5)
    cc_del = vals.get('cc_delinq', 2.94)

    def _status(now, pre, expected_weeks, data_is_post_shock=False):
        """Determine phase status. Only confirm/emerge if data is post-shock."""
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
        moved = abs(chg) > 0.15
        if moved and before_window:
            return 'ahead'
        if moved and (in_window or past_window):
            return 'confirmed' if abs(chg) > 0.5 else 'emerging'
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
    cc_post      = _latest_date('cc_delinq') >= shock

    phases = [
        {"phase": "Pump Prices Spike", "expected": "Days 1\u201314", "expected_weeks": [0, 2],
         "metric": "Gasoline $/gal", "pre": gas_pre, "now": gas_now,
         "chg": round(gas_now - gas_pre, 2) if gas_now and gas_pre else None,
         "status": _status(gas_now, gas_pre, [0, 2], data_is_post_shock=gas_post),
         "note": f"FRED GASREGW: ${gas_pre:.2f} \u2192 ${gas_now:.2f}/gal (+{((gas_now-gas_pre)/gas_pre*100):.0f}%)" if gas_now and gas_post else "Awaiting FRED GASREGW weekly retail gasoline data"
        },
        {"phase": "Transport & Freight Costs", "expected": "Weeks 4\u20136", "expected_weeks": [4, 6],
         "metric": "CPI Transport Svcs YoY", "pre": cpi_trans, "now": cpi_trans, "chg": 0.0,
         "status": _status(cpi_trans, cpi_trans, [4, 6], data_is_post_shock=cpi_post),
         "note": "Data predates shock \u2014 next CPI print will be first test" if not cpi_post else f"CPI Transport at {cpi_trans}%"
        },
        {"phase": "CPI Energy Prints", "expected": "Weeks 6\u201310", "expected_weeks": [6, 10],
         "metric": "CPI Energy YoY", "pre": 0.4, "now": cpi_energy_yoy,
         "chg": round(cpi_energy_yoy - 0.4, 1) if cpi_energy_yoy is not None else None,
         "status": _status(cpi_energy_yoy, 0.4, [6, 10], data_is_post_shock=cpi_post),
         "note": f"CPI Energy at +{cpi_energy_yoy}% YoY" if cpi_energy_yoy is not None else "Awaiting post-shock CPI release"
        },
        {"phase": "Food & Services Inflation", "expected": "Months 3\u20135", "expected_weeks": [12, 20],
         "metric": "CPI Food Away YoY", "pre": food_away, "now": food_away, "chg": 0.0,
         "status": "not_yet",
         "note": "Too early \u2014 food & services pass-through takes 3+ months"
        },
        {"phase": "Core Goods Inflation", "expected": "Months 5\u20138", "expected_weeks": [20, 32],
         "metric": "Core CPI YoY", "pre": 2.5, "now": core_cpi, "chg": round(core_cpi - 2.5, 1),
         "status": _status(core_cpi, 2.5, [20, 32], data_is_post_shock=cpi_post),
         "note": f"Core CPI at {core_cpi}% \u2014 {'data predates shock' if not cpi_post else 'energy input costs tracking'}"
        },
        {"phase": "Consumer Sentiment Falls", "expected": "Weeks 2\u20136", "expected_weeks": [2, 6],
         "metric": "UMich Sentiment", "pre": 56.6, "now": umcsent, "chg": round(umcsent - 56.6, 1),
         "status": _status(-umcsent, -56.6, [2, 6], data_is_post_shock=umcsent_post),
         "note": f"UMich at {umcsent} \u2014 {'pre-shock baseline, awaiting Mar+ reading' if not umcsent_post else 'post-shock reading' + (' confirms decline' if umcsent < 55 else ', watching')}"
        },
        {"phase": "Savings Drawdown", "expected": "Months 2\u20134", "expected_weeks": [8, 16],
         "metric": "Personal Saving Rate", "pre": 4.5, "now": saving, "chg": round(saving - 4.5, 1),
         "status": _status(-saving, -4.5, [8, 16], data_is_post_shock=saving_post),
         "note": f"Saving rate at {saving}% \u2014 {'pre-shock baseline' if not saving_post else 'stable so far' if saving >= 4.2 else 'declining'}"
        },
        {"phase": "Delinquencies Climb", "expected": "Months 5\u201310", "expected_weeks": [20, 40],
         "metric": "CC 90+ DPD Rate", "pre": 2.94, "now": cc_del, "chg": round(cc_del - 2.94, 2),
         "status": _status(cc_del, 2.94, [20, 40], data_is_post_shock=cc_post),
         "note": f"CC delinquency at {cc_del}% \u2014 {'pre-shock data, too early' if not cc_post else 'monitoring for oil impact'}"
        },
    ]

    tracker = {
        "shock_date": "2026-03-01",
        "weeks_elapsed": weeks,
        "wti_pre": wti_pre, "wti_now": round(wti_now, 1), "wti_chg_pct": wti_chg,
        "phases": phases
    }

    new_json = json.dumps(tracker, separators=(', ', ':'), ensure_ascii=False)
    new_decl = f'const SHOCK_TRACKER = {new_json};'
    # SHOCK_TRACKER has nested arrays/objects — match up to the line
    # before '// OIL_DAILY' which always follows it
    pattern = r'const SHOCK_TRACKER\s*=\s*\{[\s\S]*?\n\};\s*(?=\n// OIL_DAILY)'
    # Use lambda to avoid regex interpreting \u escapes in replacement string
    new_html, n = re.subn(pattern, lambda m: new_decl, html, count=1)
    if n:
        applied.append(f'SHOCK_TRACKER updated ({weeks} weeks, WTI ${wti_now:.0f})')
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

    body = ana.get('outlook_body', '')
    if body:
        new_h = re.sub(r'(class="stk-lead"[^>]*>).*?(</div>)',
                       rf'\g<1>{body}\g<2>', html, count=1, flags=re.DOTALL)
        if new_h != html: applied.append('outlook_body'); html = new_h

    txt = ana.get('tabs', {}).get('gdp', '')
    if txt: html = patch_commentary(html, 'gdp', txt)

    banks_txt = ana.get('tabs', {}).get('banks', '')
    if banks_txt: html = patch_commentary(html, 'banks', banks_txt)
    return html


def rebuild_kpi_strip(html, data, vals):
    """Rebuild the top-level KPIS array with latest values and MoM deltas."""

    def _mlbl(date_str):
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")

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

    # 1. Unemployment  (up = bad)
    unrate = data.get('unrate', [])
    if unrate and len(unrate) >= 2:
        cur, prev, chg, d = _mom(unrate)
        lbl = f"Unemployment {_mlbl(unrate[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur:.1f}%', 'metric': 'unemp',
                      'delta': d, 'chg': f'{chg}pp', 'inv': True,
                      'sub': f"Prior: {prev:.1f}% ({_mlbl(unrate[1]['date'])})"})

    # 2. NFP Jobs (MoM change)  (up = good)
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

    # 3. CPI YoY — with 3M avg + MoM + YoY in sub
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
            lbl = f"CPI YoY {_mlbl(cpi[0]['date'])}"
            mom_str = f"MoM: {mom_pct:+.2f}% · " if mom_pct is not None else ""
            avg3m_str = f" · 3M avg: {avg3m:.1f}%" if avg3m is not None else ""
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'cpi',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp', 'inv': True,
                          'sub': f"{mom_str}YoY: {yoy_cur:.1f}%{avg3m_str} · Prior: {yoy_prev:.1f}% ({_mlbl(cpi[1]['date'])})"})

    # 4. Core PCE YoY  (up = bad)
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

    # 5. Wages — BLS AHETPI  (up = good)
    ahetpi = data.get('ahetpi', [])
    if ahetpi and len(ahetpi) >= 14:
        yoy_cur, yoy_prev = _yoy_pair(ahetpi)
        if yoy_cur is not None and yoy_prev is not None:
            d = round(yoy_cur - yoy_prev, 2)
            sign = '+' if d > 0 else ''
            lbl = f"Wage Growth {_mlbl(ahetpi[0]['date'])}"
            cards.append({'lbl': lbl, 'val': f'{yoy_cur:.1f}%', 'metric': 'wages',
                          'delta': d, 'chg': f'{sign}{d:.1f}pp',
                          'sub': f"Prior: {yoy_prev:.1f}% ({_mlbl(ahetpi[1]['date'])})"})

    # 6. Fed Funds Rate
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

    # 7. 10Y Treasury
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

    # 8. Initial Claims (weekly)  (up = bad)
    icsa = data.get('icsa', [])
    if icsa and len(icsa) >= 2:
        cur, prev = icsa[0]['value'], icsa[1]['value']
        d = round(cur - prev)
        sign = '+' if d > 0 else ''
        lbl = f"Initial Claims {_mlbl(icsa[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur/1000:.0f}K', 'metric': 'claims',
                      'delta': d, 'chg': f'{sign}{d/1000:.0f}K', 'inv': True,
                      'sub': f"Prior wk: {prev/1000:.0f}K ({_mlbl(icsa[1]['date'])})"})

    # 9. Consumer Sentiment (UMich)  (up = good)
    umcsent = data.get('umcsent', [])
    if umcsent and len(umcsent) >= 2:
        cur_s, prev_s, chg_s, d_s = _mom(umcsent)
        yoy_s = None
        if len(umcsent) >= 13:
            yoy_s = round(cur_s - umcsent[12]['value'], 1)
        lbl = f"UMich Sentiment {_mlbl(umcsent[0]['date'])}"
        yoy_str = f" · YoY: {yoy_s:+.1f}" if yoy_s is not None else ""
        cards.append({'lbl': lbl, 'val': f'{cur_s:.1f}', 'metric': 'umcsent',
                      'delta': d_s, 'chg': f'{chg_s}',
                      'sub': f"MoM: {chg_s}{yoy_str} · Prior: {prev_s:.1f} ({_mlbl(umcsent[1]['date'])})"})

    # 10. Debt Service Ratio (TDSP)  (up = bad)
    tdsp = data.get('tdsp', [])
    if tdsp and len(tdsp) >= 2:
        cur_t, prev_t, chg_t, d_t = _mom(tdsp)
        lbl = f"Debt Service Ratio {_mlbl(tdsp[0]['date'])}"
        cards.append({'lbl': lbl, 'val': f'{cur_t:.1f}%', 'metric': 'dsr',
                      'delta': d_t, 'chg': f'{chg_t}pp', 'inv': True,
                      'sub': f"% of disp. income · Prior: {prev_t:.1f}% ({_mlbl(tdsp[1]['date'])})"})

    if not cards:
        return html

    # Inject as JS
    cards_json = json.dumps(cards, separators=(', ', ':'))
    pattern = r'const KPIS\s*=\s*\[[\s\S]*?\];'
    new_decl = f'const KPIS = {cards_json};'
    new_html, n = re.subn(pattern, lambda m: new_decl, html, count=1)
    if n:
        applied.append(f'KPIS rebuilt ({len(cards)} cards with MoM deltas)')
        return new_html
    else:
        warnings.append('rebuild_kpi_strip: KPIS array not matched')
        return html


def update_meta(html):
    today = datetime.date.today().strftime('%B %d, %Y')
    utc   = datetime.datetime.utcnow().strftime('%H:%M UTC')
    new_h = re.sub(
        r'(GitHub Actions — Cron trigger: ).*?(?=</span>|<)',
        rf'\g<1>Weekly Fri 8am ET + Monthly 2nd Sat — Last run: {today} {utc}',
        html, count=1
    )
    if new_h != html: applied.append('trigger_timestamp'); html = new_h
    return html


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

    html = update_meta(html)

    # Write version.json and sync BUILD_V in index.html for cache-busting
    build_v = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    ver_file = ROOT / 'version.json'
    ver_file.write_text(json.dumps({"v": build_v}), encoding='utf-8')
    html = re.sub(r'var BUILD_V\s*=\s*"[^"]*"', f'var BUILD_V = "{build_v}"', html)

    # ── Inject validation report into dashboard if available ──
    if VAL_FILE.exists():
        try:
            val_report = json.loads(VAL_FILE.read_text())
            val_json = json.dumps(val_report, separators=(',', ':'))
            pattern_vr = r'const VALIDATION_REPORT\s*=\s*\{[\s\S]*?\};'
            new_vr = f'const VALIDATION_REPORT = {val_json};'
            html, n_vr = re.subn(pattern_vr, lambda m: new_vr, html, count=1)
            if n_vr:
                applied.append(f'VALIDATION_REPORT injected ({val_report.get("status","?")})')
        except Exception as e:
            warnings.append(f'Validation report inject: {e}')

    HTML_FILE.write_text(html, encoding='utf-8')

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

    print(f'[Agent 4] Done — {len(applied)} patches, {len(errors)} errors, {len(warnings)} warnings | {HTML_FILE.stat().st_size:,} bytes')
    for a in applied:  print(f'  ✅ {a}')
    for e in errors:   print(f'  ⚠  {e}')
    for w in warnings: print(f'  ℹ  {w}')

    # Exit 1 only on hard errors, not on missing KPI labels
    hard_errors = [e for e in errors if 'missing' in e.lower() or 'ERROR' in e]
    return len(hard_errors) == 0


if __name__ == '__main__':
    sys.exit(0 if render() else 1)
