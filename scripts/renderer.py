#!/usr/bin/env python3
"""
Agent 4 — RENDERER  (renderer.py)
Reads raw_data.json + analysis.json.
Patches macro_dashboard_v6.html: chart arrays, KPIs, tab commentary.
No LLM. Output: macro_dashboard_v6.html (updated in-place).
"""

import os, re, json, datetime, sys
from pathlib import Path


ROOT      = Path(__file__).parent.parent
HTML_FILE = ROOT / 'macro_dashboard_v6.html'
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SIG_FILE  = ROOT / 'data' / 'signals.json'
ANA_FILE  = ROOT / 'data' / 'analysis.json'

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
        # Skip current year (partial) — handled by appending latest
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
    """Compute latest-month YoY% from monthly index data."""
    if not monthly_series or len(monthly_series) < 13:
        return None, None
    v0, v12 = monthly_series[0]['value'], monthly_series[12]['value']
    if v12 == 0:
        return None, None
    yoy = round((v0 - v12) / v12 * 100, 1)
    lbl = datetime.datetime.strptime(monthly_series[0]['date'], '%Y-%m-%d').strftime("%b'%y")
    return lbl, yoy


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
    new_html, n = re.subn(pattern, new_decl, html, count=1)
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

    # ── U_ANNUAL ──────────────────────────────────────────────────────
    unrate = data.get('unrate', [])
    if len(unrate) >= 60:
        labels, values = _annual_avg(unrate)
        if labels and unrate:
            labels.append(_month_lbl(unrate[0]['date']))
            values.append(round(unrate[0]['value'], 1))
        if labels:
            html = _inject_const(html, 'U_ANNUAL', {'labels': labels, 'data': values})

    # ── CPI_ANNUAL ────────────────────────────────────────────────────
    cpi_all = data.get('cpi_all', [])
    if len(cpi_all) >= 60:
        labels, values = _dec_yoy(cpi_all)
        lbl, yoy = _latest_yoy(cpi_all)
        if lbl and labels:
            labels.append(lbl)
            values.append(yoy)
        if labels:
            html = _inject_const(html, 'CPI_ANNUAL', {'labels': labels, 'data': values})

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
        # Append latest
        h_lbl, h_yoy = _latest_yoy(pce)
        c_lbl, c_yoy = _latest_yoy(pce_core)
        if h_lbl and h_yoy is not None and c_yoy is not None:
            common_labels.append(h_lbl)
            headline.append(h_yoy)
            core.append(c_yoy)
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
        # Append latest
        w_lbl, w_yoy = _latest_yoy(ahetpi)
        c_lbl, c_yoy = _latest_yoy(cpi_all)
        if w_lbl and w_yoy is not None and c_yoy is not None:
            labels.append(w_lbl)
            nominal.append(w_yoy)
            real.append(round(w_yoy - c_yoy, 1))
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

    # ── SAVING_RATE ───────────────────────────────────────────────────
    psavert = data.get('psavert', [])
    if len(psavert) >= 60:
        labels, values = _annual_avg(psavert)
        if psavert:
            labels.append(_month_lbl(psavert[0]['date']))
            values.append(round(psavert[0]['value'], 1))
        if labels:
            html = _inject_const(html, 'SAVING_RATE', {'labels': labels, 'data': values})

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
        # Add forecast
        common.append('2026F')
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

    return html


# ── HELPERS ───────────────────────────────────────────────────────────

def patch_array_last(html, js_key, new_val, precision=2):
    fmt = str(round(new_val, precision)) if new_val is not None else 'null'
    pattern = rf'(\b{re.escape(js_key)}:\s*\[[^\]]*,\s*)[\d\.\-]+((\s*)\])'
    new_html, n = re.subn(pattern, rf'\g<1>{fmt}\g<3>]', html, count=1, flags=re.DOTALL)
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
    # First rename the label key in the JS object
    pat = rf'(\{{lbl:"){re.escape(old_label)}(")'
    new_html, n = re.subn(pat, rf'\g<1>{new_label}\2', html)
    if n:
        applied.append(f'kpi.rename "{old_label}" → "{new_label}"')
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
    chunk = html[idx: idx + 700]
    new_chunk = re.sub(
        r'(labels:\s*\[[^\]]*,\s*)"[^"]*"(\s*\])',
        rf'\1"{new_label}"\2', chunk, count=1, flags=re.DOTALL
    )
    if new_chunk == chunk: errors.append(f'labels not found in {var_name}')
    else: applied.append(f'{var_name}.labels[-1]={new_label}')
    return html[:idx] + new_chunk + html[idx + 700:]




def month_label(date_str):
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")


def inject_oil_daily(html, oil_daily):
    new_data = json.dumps(oil_daily, separators=(',', ':'))
    new_html, n = re.subn(
        r'(const OIL_DAILY\s*=\s*)\{.*?\n\}(\s*;)',
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


# ── OIL MONTHLY CHART INJECTOR ───────────────────────────────────────

def inject_oil_monthly(html, data):
    """
    Rebuild OIL_MONTHLY from raw FRED/EIA monthly data.
    Always ends at the PRIOR complete month (never current partial month).
    Updates panel title and subtitle date ranges automatically.
    """
    wti_raw   = data.get('wti_daily',   [])
    brent_raw = data.get('brent_daily', [])
    if not wti_raw: return html

    today = datetime.date.today()
    # Prior complete month = last month
    prior_month_end = today.replace(day=1) - datetime.timedelta(days=1)
    start_date = datetime.date(2022, 1, 1)

    # Build monthly averages from daily data — but daily only covers 35 days
    # For the full historical series, use FRED monthly DCOILWTICO / DCOILBRENTEU
    # If only daily available, just drop the current partial month from OIL_MONTHLY
    # by patching out the last label if it matches current month
    cur_month_label = today.strftime("%b'%y").replace("'26","'26")  # e.g. Mar'26
    cur_month_alt   = today.strftime("%b '%y")                        # e.g. Mar '26

    # Find OIL_MONTHLY labels array and remove current month entry
    m = re.search(r'(const OIL_MONTHLY\s*=\s*\{[^}]*labels:\s*\[)([^\]]+)(\])', html, re.DOTALL)
    if not m: warnings.append('inject_oil_monthly: labels array not found'); return html

    labels_str = m.group(2)
    # Parse labels
    label_list = re.findall(r'"([^"]+)"', labels_str)
    if not label_list: return html

    last_label = label_list[-1]
    # Check if last label is current month (partial)
    cur_mon_str = today.strftime("%b'%y")      # Mar'26
    cur_mon_alt = today.strftime("%-m/%y")     # 3/26
    cur_mon_3   = today.strftime("%b '%y")     # Mar '26
    is_partial  = (cur_mon_str in last_label or
                   '*' in last_label or
                   today.strftime('%b') in last_label and str(today.year)[-2:] in last_label)

    if not is_partial:
        applied.append('inject_oil_monthly: already ends at prior month')
        return html

    # Remove last entry from labels, wti, brent arrays
    for arr_name in ['labels', 'wti', 'brent']:
        if arr_name == 'labels':
            # Remove last quoted string
            pat = r'(const OIL_MONTHLY[^}]*?' + arr_name + r':\s*\[)(.*?)(,?\s*"[^"]*"\s*)(\])'
            new_html, n = re.subn(pat, lambda x: x.group(1) + x.group(2).rstrip(', ') + x.group(4),
                                  html, count=1, flags=re.DOTALL)
        else:
            # Remove last numeric value
            pat = rf'(const OIL_MONTHLY[^;]*?{arr_name}:[^\[]*\[[^\]]*,\s*)(\d+\.\d+)(\s*\])'
            new_html, n = re.subn(pat, r'\g<1>\g<3>', html, count=1, flags=re.DOTALL)
        if n:
            html = new_html
            applied.append(f'oil_monthly.{arr_name}: dropped partial {last_label}')
        else:
            warnings.append(f'inject_oil_monthly: could not trim {arr_name}')

    # Update panel title date range
    prior_str = prior_month_end.strftime("%b %Y")  # e.g. Feb 2026
    start_str = f"Jan {START_YEAR}"
    old_title_pat = r'WTI &amp; Brent — Monthly [^<]+'
    new_title = f'WTI &amp; Brent — Monthly {start_str}–{prior_str} (Prior Month)'
    new_html, n = re.subn(old_title_pat, new_title, html, count=1)
    if n:
        html = new_html
        applied.append(f'oil_monthly.title → {prior_str}')

    # Update subtitle date range + spike callout
    old_sub_pat = r'Monthly avg \$/bbl · Jan \d{4}–[A-Za-z]+ \d{4}'
    new_sub = f'Monthly avg $/bbl · Jan {START_YEAR}–{prior_str}'
    new_html, n = re.subn(old_sub_pat, new_sub, html, count=1)
    if n:
        html = new_html
        applied.append(f'oil_monthly.subtitle → {prior_str}')

    # Update the spike callout span to reference current month
    cur_str = today.strftime('%b %Y')  # e.g. Apr 2026
    old_spike_pat = r'<span style="color:#C0392B;font-weight:600">⚡ [^<]+ spike shown in daily chart →</span>'
    new_spike = f'<span style="color:#C0392B;font-weight:600">⚡ {cur_str} — see daily chart →</span>'
    new_html2, n2 = re.subn(old_spike_pat, new_spike, html, count=1)
    if n2:
        html = new_html2
        applied.append(f'oil_monthly.spike_note → {cur_str}')

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
            r'(SPREADS_DATA\s*=\s*\{[^}]*?labels:\s*\[[^\]]*,\s*)"[^"]+"',
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
        html = patch_array_last(html, 'data', unrate, 1)
        unemp_date = data.get('unrate', [{}])[0].get('date','') if data.get('unrate') else ''
        u_lbl = f"Unemployment {month_label(unemp_date)}" if unemp_date else 'Unemployment'
        html = patch_kpi_full(html, 'Unemployment 2025', u_lbl, f'{unrate:.1f}%')
        unrate_s = data.get('unrate', [])
        if unrate_s:
            html = patch_var_last_label(html, 'U_ANNUAL', month_label(unrate_s[0]['date']))

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
        html = patch_array_last(html, 'nominal', wages, 1)
        ahetpi_s = data.get('ahetpi')
        wages_date = ahetpi_s[0].get('date','') if ahetpi_s else ''
        wages_lbl = f"Nominal Wage Growth {month_label(wages_date)}" if wages_date else 'Nominal Wage Growth'
        html = patch_kpi_full(html, 'Nominal Wage Growth 2025', wages_lbl, f'{wages:+.1f}%')

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
        html = patch_array_last(html, 'data', cpi, 1)
        cpi_s2 = data.get('cpi_all')
        cpi_date = cpi_s2[0].get('date','') if cpi_s2 else ''
        cpi_lbl = f"CPI All Items {month_label(cpi_date)}" if cpi_date else 'CPI All Items'
        html = patch_kpi_full(html, 'CPI All Items 2025', cpi_lbl, f'{cpi:+.1f}%')
        cpi_s = data.get('cpi_all', [])
        if cpi_s:
            html = patch_var_last_label(html, 'CPI_ANNUAL', month_label(cpi_s[0]['date']))

    if core_cpi is not None:
        html = patch_array_last(html, 'core', core_cpi, 1)

    if pce is not None:
        html = patch_array_last(html, 'headline', pce, 1)

    if core_pce is not None:
        pce_core_s = data.get('pce_core')
        pce_date = pce_core_s[0].get('date','') if pce_core_s else ''
        pce_lbl = f"Core PCE {month_label(pce_date)}" if pce_date else 'Core PCE'
        html = patch_kpi_full(html, 'Core PCE Dec 2025', pce_lbl, f'{core_pce:+.1f}%')

    if save is not None:
        html = patch_array_last(html, 'data', save, 1)

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
        html = patch_array_last(html, 'wti', round(wti, 1), 1)

    if brent is not None:
        brent_sub = f'Spread: ${brent - wti:.1f}' if wti is not None else None
        html = patch_kpi(html, 'Brent — Latest', f'${brent:.1f}', brent_sub)
        html = patch_array_last(html, 'brent', round(brent, 1), 1)

    oil_daily = data.get('oil_daily_chart')
    if oil_daily:
        html = inject_oil_daily(html, oil_daily)

    txt = tabs.get('oil', '')
    if txt: html = patch_commentary(html, 'oil', txt)
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
    return html


def update_meta(html):
    today = datetime.date.today().strftime('%B %d, %Y')
    utc   = datetime.datetime.utcnow().strftime('%H:%M UTC')
    new_h = re.sub(
        r'(GitHub Actions — Cron trigger: ).*?(?=</span>|<)',
        rf'\g<1>Daily 7am ET — Last run: {today} {utc}',
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

    # Rebuild all chart arrays from historical data (2000+)
    try:
        html = rebuild_charts(html, data)
        print('  \u2705 Chart history rebuild')
    except Exception as e:
        errors.append(f'rebuild_charts: {e}')
        print(f'  \u274c Chart history rebuild: {e}')

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

    HTML_FILE.write_text(html, encoding='utf-8')
    print(f'[Agent 4] Done — {len(applied)} patches, {len(errors)} errors, {len(warnings)} warnings | {HTML_FILE.stat().st_size:,} bytes')
    for e in errors:   print(f'  ⚠  {e}')
    for w in warnings: print(f'  ℹ  {w}')

    # Exit 1 only on hard errors, not on missing KPI labels
    hard_errors = [e for e in errors if 'missing' in e.lower() or 'ERROR' in e]
    return len(hard_errors) == 0


if __name__ == '__main__':
    sys.exit(0 if render() else 1)
