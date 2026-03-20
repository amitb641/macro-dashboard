#!/usr/bin/env python3
"""
Agent 2 — ANALYZER
Diffs raw_data.json vs prior snapshot.json.
Scores signal changes, flags surprises, tags directional deltas.
No LLM used. Output: data/signals.json
"""

import json, datetime, sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
RAW_FILE  = ROOT / 'data' / 'raw_data.json'
SNAP_FILE = ROOT / 'data' / 'last_update.json'
OUT_FILE  = ROOT / 'data' / 'signals.json'

# Flag if MoM/period change exceeds these thresholds
THRESHOLDS = {
    'ffr':        0.25,   # pp — full 25bp Fed move
    'dgs10':      0.20,   # pp — 20bp yield move
    'ig_oas':     15,     # bp
    'hy_oas':     50,     # bp
    'unrate':     0.2,    # pp
    'cpi_yoy':    0.2,    # pp
    'pce_yoy':    0.2,    # pp
    'nfp_mom':    75,     # 000s payrolls
    'wti':        3.0,    # $/bbl
    'mortgage30': 0.15,   # pp
    'wages_yoy':  0.3,    # pp
    'cs_hpi_yoy': 1.0,    # pp
    'icsa':       30000,  # weekly initial claims swing
    'umcsent':    5.0,    # UMich sentiment index points
    'tdsp':       0.3,    # pp — Debt Service Ratio
}

# Absolute level alerts
LEVEL_ALERTS = {
    'ig_oas':     {'watch': 120,  'alert': 160},
    'hy_oas':     {'watch': 400,  'alert': 500},
    'dgs10':      {'watch': 4.5,  'alert': 5.0},
    'unrate':     {'watch': 4.5,  'alert': 5.0},
    'cpi_yoy':    {'watch': 3.0,  'alert': 3.5},
    'core_pce_yoy': {'watch': 2.8, 'alert': 3.2},
    'wti':        {'watch': 85,   'alert': 95},
    'mortgage30': {'watch': 7.0,  'alert': 7.5},
    'cc_delinq':  {'watch': 9.5,  'alert': 11.0},
    'icsa':       {'watch': 250000, 'alert': 300000},
    'umcsent':    {'watch': 60,   'alert': 50},     # consumer pessimism
    'tdsp':       {'watch': 10.5, 'alert': 11.5},   # debt service stress
}


def yoy(series):
    """YoY % change from list of {date,value} newest-first.
    Matches by calendar month 12 months prior (not by index position),
    so gaps in monthly data (e.g. gov't shutdown) don't shift the comparison.
    """
    if not series or len(series) < 13: return None
    latest = series[0]
    v = latest['value']
    d0 = datetime.datetime.strptime(latest['date'], '%Y-%m-%d')
    target_yr, target_mo = d0.year - 1, d0.month
    v0 = None
    for obs in series:
        od = datetime.datetime.strptime(obs['date'], '%Y-%m-%d')
        if od.year == target_yr and od.month == target_mo:
            v0 = obs['value']
            break
    if v0 is None:
        # Fallback to index [12] if exact month not found
        v0 = series[12]['value'] if len(series) > 12 else None
    return round((v - v0) / abs(v0) * 100, 2) if v0 else None


def latest(x):
    if not x: return None
    if isinstance(x, dict):  return x.get('value')
    if isinstance(x, list):  return x[0]['value'] if x else None
    return None


def level_alert(key, val):
    if key not in LEVEL_ALERTS or val is None: return None
    lvl = LEVEL_ALERTS[key]
    if val >= lvl.get('alert', 9e9): return 'alert'
    if val >= lvl.get('watch',  9e9): return 'watch'
    return None


def make_signal(val, snap_val, threshold):
    delta = round(val - snap_val, 4) if (val is not None and snap_val is not None) else None
    flagged = delta is not None and abs(delta) >= threshold
    direction = ('rising' if delta > 0 else 'falling') if flagged else 'stable'
    return {'value': val, 'delta': delta, 'direction': direction, 'flagged': flagged}


def analyze():
    print('[Agent 2 — Analyzer] Starting...')

    if not RAW_FILE.exists():
        print('ERROR: raw_data.json missing — run collector.py first'); sys.exit(1)

    raw  = json.loads(RAW_FILE.read_text())
    data = raw.get('data', {})

    snap_vals = {}
    if SNAP_FILE.exists():
        snap = json.loads(SNAP_FILE.read_text())
        # last_update.json stores prior values under 'values' key
        snap_vals = snap.get('values', {})
        print(f'  Prior snapshot: {snap.get("completed_at", snap.get("saved_at", "?"))}')
    else:
        print('  No prior data — first run, no signal deltas available')

    # ── Derive current values ─────────────────────────────────────────
    v = {}
    v['ffr']          = latest(data.get('ffr'))
    v['dgs2']         = latest(data.get('dgs2'))
    v['dgs5']         = latest(data.get('dgs5'))
    v['dgs10']        = latest(data.get('dgs10'))
    v['dgs30']        = latest(data.get('dgs30'))
    # FRED OAS series return percentage points (e.g. 0.88 = 88bp); convert to bp
    _ig_raw = latest(data.get('ig_oas'))
    _hy_raw = latest(data.get('hy_oas'))
    v['ig_oas']       = round(_ig_raw * 100) if _ig_raw is not None else None
    v['hy_oas']       = round(_hy_raw * 100) if _hy_raw is not None else None

    unrate = data.get('unrate', [])
    v['unrate']       = unrate[0]['value'] if unrate else None
    v['u6rate']       = latest(data.get('u6rate')) if not isinstance(data.get('u6rate'), list) else (data['u6rate'][0]['value'] if data.get('u6rate') else None)

    payems = data.get('payems', [])
    v['nfp_level']    = payems[0]['value'] if payems else None
    v['nfp_mom']      = round(payems[0]['value'] - payems[1]['value']) if len(payems) >= 2 else None

    icsa = data.get('icsa', [])
    v['icsa']         = icsa[0]['value'] if icsa else None
    ccsa = data.get('ccsa', [])
    v['ccsa']         = ccsa[0]['value'] if ccsa else None

    v['wages_yoy']    = yoy(data.get('ahetpi', []))
    v['cpi_yoy']      = yoy(data.get('cpi_all', []))
    v['core_cpi_yoy'] = yoy(data.get('cpi_core', []))
    v['pce_yoy']      = yoy(data.get('pce', []))
    v['core_pce_yoy'] = yoy(data.get('pce_core', []))

    psavert = data.get('psavert', [])
    v['saving_rate']  = psavert[0]['value'] if psavert else None

    mtg = data.get('mortgage30', [])
    v['mortgage30']   = mtg[0]['value'] if mtg else None

    starts = data.get('houst', [])
    v['housing_starts'] = starts[0]['value'] if starts else None

    v['cs_hpi_yoy']   = yoy(data.get('cs_hpi', []))

    umcsent = data.get('umcsent', [])
    v['umcsent']      = umcsent[0]['value'] if umcsent else None

    atl_wage = data.get('atl_wage_tracker', [])
    v['atl_wage_3m']  = atl_wage[0]['value'] if atl_wage else None

    tdsp = data.get('tdsp', [])
    v['tdsp']         = tdsp[0]['value'] if tdsp else None

    wti = data.get('wti_daily', [])
    v['wti']          = wti[0]['value'] if wti else None
    brent = data.get('brent_daily', [])
    v['brent']        = brent[0]['value'] if brent else None

    gdp_q = data.get('gdp_growth', [])
    v['gdp_growth_q'] = gdp_q[0]['value'] if gdp_q else None

    cc = data.get('cc_delinq', [])
    v['cc_delinq']    = cc[0]['value'] if cc else None

    # 10Y-2Y spread in bp
    if v['dgs10'] and v['dgs2']:
        v['spread_10_2_bp'] = round((v['dgs10'] - v['dgs2']) * 100)
    else:
        v['spread_10_2_bp'] = None

    # ── Build signals ─────────────────────────────────────────────────
    sigs = {}
    for key, thresh in THRESHOLDS.items():
        sigs[key] = make_signal(v.get(key), snap_vals.get(key), thresh)
        sigs[key]['alert'] = level_alert(key, v.get(key))

    # Extra signals without thresholds
    for key in ['dgs2', 'dgs5', 'dgs30', 'spread_10_2_bp', 'core_cpi_yoy',
                'core_pce_yoy', 'u6rate', 'saving_rate', 'housing_starts',
                'brent', 'gdp_growth_q', 'cc_delinq', 'ccsa',
                'umcsent', 'atl_wage_3m', 'tdsp']:
        if key not in sigs:
            sigs[key] = make_signal(v.get(key), snap_vals.get(key), 9e9)
            sigs[key]['alert'] = level_alert(key, v.get(key))

    # ── Score overall risk ────────────────────────────────────────────
    alert_n = sum(1 for s in sigs.values() if s.get('alert') == 'alert')
    watch_n = sum(1 for s in sigs.values() if s.get('alert') == 'watch')
    flag_n  = sum(1 for s in sigs.values() if s.get('flagged'))

    risk = ('HIGH'     if alert_n >= 3 else
            'ELEVATED' if alert_n >= 1 or watch_n >= 3 else
            'MODERATE' if watch_n >= 1 or flag_n >= 3 else
            'LOW')

    # ── Build change headlines (for Agent 3 prompt) ───────────────────
    headlines = []
    for key, s in sigs.items():
        if s.get('flagged') and s['value'] is not None:
            d = s['delta']
            arrow = '▲' if d > 0 else '▼'
            alert_tag = f' [{s["alert"].upper()}]' if s.get('alert') else ''
            headlines.append({
                'key':   key,
                'line':  f'{key}: {s["value"]:.2f} ({arrow}{abs(d):.2f} vs prior){alert_tag}',
                'alert': s.get('alert'),
            })

    print(f'  Risk: {risk} | alerts={alert_n} watches={watch_n} flagged={flag_n}')
    print(f'  Change headlines: {len(headlines)}')

    out = {
        'analyzed_at':   datetime.datetime.utcnow().isoformat() + 'Z',
        'risk_level':    risk,
        'alert_count':   alert_n,
        'watch_count':   watch_n,
        'flagged_count': flag_n,
        'values':        v,
        'signals':       sigs,
        'headlines':     headlines,
        'raw_errors':    raw.get('errors', []),
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
    print(f'[Agent 2] Done → data/signals.json')
    return True


if __name__ == '__main__':
    sys.exit(0 if analyze() else 1)
