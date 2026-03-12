#!/usr/bin/env python3
"""
Agent 4 — RENDERER  (renderer.py)
Reads raw_data.json + analysis.json.
Patches macro_dashboard_v6.html: all chart arrays, KPIs, tab commentary.
No LLM used. Output: macro_dashboard_v6.html (updated in-place).
"""

import os, re, json, datetime, sys
from pathlib import Path

FRED_KEY  = os.environ.get('FRED_API_KEY', '')

ROOT      = Path(__file__).parent.parent
HTML_FILE = ROOT / 'macro_dashboard_v6.html'
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SIG_FILE  = ROOT / 'data' / 'signals.json'
ANA_FILE  = ROOT / 'data' / 'analysis.json'

applied = []
errors  = []


# ══════════════════════════════════════════════════════════════════════
# PATCH HELPERS
# ══════════════════════════════════════════════════════════════════════

def patch_array_last(html, js_key, new_val, precision=2):
    """Replace last numeric value in  js_key:[..., OLD]  with new_val."""
    fmt = str(round(new_val, precision)) if new_val is not None else 'null'
    pattern = rf'(\b{re.escape(js_key)}:\s*\[[^\]]*,\s*)[\d\.\-]+((\s*)\])'
    new_html, n = re.subn(pattern, rf'\g<1>{fmt}\g<3>]', html, count=1, flags=re.DOTALL)
    if n: applied.append(f'{js_key}[-1]={fmt}')
    else: errors.append(f'patch_array_last: {js_key} not found')
    return new_html


def patch_var_last_label(html, var_name, new_label):
    """Replace last string in the labels:[...] of a specific JS const."""
    idx = html.find(f'const {var_name} =')
    if idx < 0: idx = html.find(f'let {var_name} =')
    if idx < 0: errors.append(f'patch_var_last_label: {var_name} not found'); return html
    chunk = html[idx: idx + 700]
    new_chunk = re.sub(
        r'(labels:\s*\[[^\]]*,\s*)"[^"]*"(\s*\])',
        rf'\1"{new_label}"\2', chunk, count=1, flags=re.DOTALL
    )
    if new_chunk == chunk: errors.append(f'patch_var_last_label: labels not found in {var_name}')
    else: applied.append(f'{var_name}.labels[-1]={new_label}')
    return html[:idx] + new_chunk + html[idx + 700:]


def patch_kpi(html, label, val, sub=None):
    """Update a KPI card {lbl:"LABEL", val:"...", sub:"..."}."""
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


def patch_commentary(html, tab_id, text):
    """Replace content of  id="commentary-{tab_id}"  div."""
    marker = f'id="commentary-{tab_id}"'
    if marker not in html: return html
    pat = rf'({re.escape(marker)}[^>]*>)(.*?)(</div>)'
    new_html, n = re.subn(pat, rf'\g<1>{text}\g<3>', html, count=1, flags=re.DOTALL)
    if n: applied.append(f'commentary.{tab_id}')
    return new_html


def inject_fred_key(html):
    if not FRED_KEY: return html
    new_h = re.sub(r"var FRED_KEY = '[^']*';",
                   f"var FRED_KEY = '{FRED_KEY}';", html, count=1)
    if new_h != html: applied.append('FRED_KEY')
    return new_h


def month_label(date_str):
    """'2026-02-01' → \"Feb'26\" """
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime("%b'%y")


# ══════════════════════════════════════════════════════════════════════
# SECTION RENDERERS
# ══════════════════════════════════════════════════════════════════════

def render_rates(html, data, vals, tabs):
    ffr  = vals.get('ffr')
    dgs10= vals.get('dgs10')
    dgs2 = vals.get('dgs2')
    spr  = vals.get('spread_10_2_bp')

    if ffr:
        html = patch_array_last(html, 'actual', ffr, 2)
        html = patch_kpi(html, 'Fed Funds Rate', f'{ffr:.2f}%')
    if dgs10 and dgs2:
        html = patch_kpi(html, '10Y–2Y Spread',
                         f'{spr:+d}bp' if spr is not None else 'N/A',
                         f'10Y: {dgs10:.2f}% · 2Y: {dgs2:.2f}%')
    txt = tabs.get('yield', '')
    if txt: html = patch_commentary(html, 'yield', txt)
    return html


def render_spreads(html, data, vals, tabs):
    ig = vals.get('ig_oas')
    hy = vals.get('hy_oas')
    if ig:
        html = patch_array_last(html, 'ig', round(ig), 0)
        html = patch_kpi(html, 'IG OAS', f'{round(ig)}bp')
    if hy:
        html = patch_array_last(html, 'hy', round(hy), 0)
        html = patch_kpi(html, 'HY OAS', f'{round(hy)}bp')
    if ig:
        label = datetime.date.today().strftime("%b'%y")
        html = re.sub(
            r'(SPREADS_DATA\s*=\s*\{[^}]*?labels:\s*\[[^\]]*,\s*)"[^"]+(")',
            rf'\g<1>"{label}"\2', html, count=1, flags=re.DOTALL
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
        html = patch_array_last(html, 'data', unrate, 1)  # U_ANNUAL.data
        html = patch_kpi(html, 'Unemployment (Feb)', f'{unrate:.1f}%')
        unrate_s = data.get('unrate', [])
        if unrate_s: html = patch_var_last_label(html, 'U_ANNUAL', month_label(unrate_s[0]['date']))

    if u6 is not None:
        html = patch_kpi(html, 'U-6 Underemployment', f'{u6:.1f}%')

    if nfp is not None:
        html = patch_kpi(html, 'NFP (Feb)', f'{nfp:+.0f}K')

    if wages is not None:
        html = patch_array_last(html, 'nominal', wages, 1)  # WAGE_ANNUAL.nominal
        html = patch_kpi(html, 'Wages YoY (Feb)', f'{wages:+.1f}%')

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
        html = patch_array_last(html, 'data', cpi, 1)   # CPI_ANNUAL.data
        html = patch_kpi(html, 'CPI (Feb)', f'{cpi:+.1f}%')
        cpi_s = data.get('cpi_all', [])
        if cpi_s: html = patch_var_last_label(html, 'CPI_ANNUAL', month_label(cpi_s[0]['date']))

    if core_cpi is not None:
        html = patch_array_last(html, 'core', core_cpi, 1)  # CPI_ANNUAL.core

    if pce is not None:
        html = patch_array_last(html, 'headline', pce, 1)   # PCE_ANNUAL.headline
        html = patch_kpi(html, 'Core PCE (Jan)', f'{pce:+.1f}%')

    if core_pce is not None:
        html = patch_array_last(html, 'core', core_pce, 1)  # PCE_ANNUAL.core (2nd hit)

    if save is not None:
        html = patch_array_last(html, 'data', save, 1)  # SAVING_RATE.data

    for tab in ('cpi', 'pce'):
        txt = tabs.get(tab, '')
        if txt: html = patch_commentary(html, tab, txt)
    return html


def render_housing(html, data, vals, tabs):
    mtg    = vals.get('mortgage30')
    starts = vals.get('housing_starts')

    if mtg is not None:
        html = patch_kpi(html, '30Y Mortgage', f'{mtg:.2f}%')
        html = patch_array_last(html, 'rate30', mtg, 2)  # MORTGAGE_DATA.rate30

    if starts is not None:
        html = patch_array_last(html, 'sf', round(starts), 0)  # STARTS_DATA.sf

    txt = tabs.get('housing', '')
    if txt: html = patch_commentary(html, 'housing', txt)
    return html


def render_oil(html, data, vals, tabs):
    wti   = vals.get('wti')
    brent = vals.get('brent')

    if wti is not None:
        html = patch_kpi(html, 'WTI — Latest', f'${wti:.1f}')
        html = patch_array_last(html, 'wti',   round(wti, 1), 1)

    if brent is not None:
        html = patch_array_last(html, 'brent', round(brent, 1), 1)

    # Inject OIL_DAILY for the current-month daily chart
    oil_daily = data.get('oil_daily_chart')
    if oil_daily:
        html = inject_oil_daily(html, oil_daily)

    txt = tabs.get('oil', '')
    if txt: html = patch_commentary(html, 'oil', txt)
    return html


def inject_oil_daily(html, oil_daily):
    """Replace OIL_DAILY constant in HTML with fresh pipeline data."""
    import json as _json
    new_data = _json.dumps(oil_daily, separators=(',', ':'))
    new_html, n = re.subn(
        r'(const OIL_DAILY\s*=\s*)\{[^;]+\}(\s*;)',
        lambda m: m.group(1) + new_data + m.group(2),
        html, count=1, flags=re.DOTALL
    )
    if n:
        applied.append('OIL_DAILY (%d sessions, %s)' % (
            oil_daily.get('sessions', 0), oil_daily.get('month', '')))
    else:
        errors.append('inject_oil_daily: OIL_DAILY const not found in HTML')
    return new_html


def render_outlook(html, ana):
    """Update risk posture KPIs and Outlook tab from Agent 3 analysis."""
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
    """Update trigger timestamp in ⚙️ tab and page eyebrow."""
    today = datetime.date.today().strftime('%B %d, %Y')
    utc   = datetime.datetime.utcnow().strftime('%H:%M UTC')

    # ⚙️ tab trigger line
    new_h = re.sub(
        r'(GitHub Actions — Cron trigger: ).*?(?=</span>|<)',
        rf'\g<1>1st of every month, 9am ET — Last run: {today} {utc}',
        html, count=1
    )
    if new_h != html: applied.append('trigger_timestamp'); html = new_h

    # Page eyebrow
    new_h = re.sub(
        r'(BEA · BLS · Fed Reserve · EIA — ).*?(?=</div>)',
        f'\\1Data refreshed: {today} {utc}',
        html, count=1
    )
    if new_h != html: applied.append('eyebrow'); html = new_h

    return html


# ══════════════════════════════════════════════════════════════════════

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

    html = inject_fred_key(html)

    sections = [
        ('Rates/Yields',  render_rates),
        ('Spreads',       render_spreads),
        ('Labor',         render_labor),
        ('Inflation',     render_inflation),
        ('Housing',       render_housing),
        ('Oil',           render_oil),
    ]
    for name, fn in sections:
        try:
            html = fn(html, data, vals, tabs)
            print(f'  ✅ {name}')
        except Exception as e:
            errors.append(f'{name}: {e}')
            print(f'  ❌ {name}: {e}')

    if ana:
        try:
            html = render_outlook(html, ana)
            print('  ✅ Outlook/KPIs')
        except Exception as e:
            errors.append(f'Outlook: {e}')

    html = update_meta(html)

    HTML_FILE.write_text(html, encoding='utf-8')
    print(f'[Agent 4] Done — {len(applied)} patches, {len(errors)} errors | {HTML_FILE.stat().st_size:,} bytes')
    for e in errors: print(f'  ⚠  {e}')
    return len(errors) == 0


if __name__ == '__main__':
    sys.exit(0 if render() else 1)
