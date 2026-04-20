#!/usr/bin/env python3
"""
Backtest — Oil Impact Chain phase-timing rules vs. historical shocks.

Takes the current SHOCK_TRACKER methodology (see METHODOLOGY.md) and
replays it against historical oil-shock episodes to measure threshold
calibration. Produces:

  data/backtest_calibration.json   — structured per-phase results
  BACKTEST_REPORT.md               — human-readable summary

Usage:
  FRED_API_KEY=... python scripts/backtest_shock.py

Scope for v1: 2022 Ukraine shock (primary, best data coverage) and
2008 Lehman-era peak (secondary, tests the inverse-direction case).
Further shocks (1990 Gulf, 1979 Iran, 1973 OPEC) require longer-dated
FRED series coverage that not every sub-index supports; flagged in
METHODOLOGY.md as a v1.1 follow-up.

Known limitations:
  * Uses current (latest revised) FRED vintages, not ALFRED vintages
    as-of each shock snapshot. Real-time revisions will have changed
    some of these readings; that gap lands in v1.1 alongside vintage
    pinning.
  * Fetches run against the live FRED API; needs FRED_API_KEY.
"""

import os, sys, json, time, datetime, urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

FRED_KEY = os.environ.get('FRED_API_KEY', '')
ROOT     = Path(__file__).parent.parent
OUT_JSON = ROOT / 'data' / 'backtest_calibration.json'
OUT_MD   = ROOT / 'BACKTEST_REPORT.md'


# ── Historical shock scenarios ─────────────────────────────────────────

SHOCKS = [
    {
        'id':          'ukraine-2022',
        'name':        '2022 Ukraine invasion',
        'shock_date':  '2022-02-24',
        'wti_pre':     92.10,          # ~5-day avg before the invasion
        'wti_peak':    123.70,         # intraday peak March 8, 2022
        'wti_peak_chg_pct': 34,
        'notes':       'Closest analog to 2026 scenario: post-pandemic demand + supply disruption.',
    },
    {
        'id':          'lehman-2008',
        'name':        '2008 Oil crash (peak-to-trough)',
        'shock_date':  '2008-07-01',   # WTI peak month
        'wti_pre':     90.00,          # ~2007 average
        'wti_peak':    145.29,         # intraday peak July 11, 2008
        'wti_peak_chg_pct': 61,
        'notes':       'Inverse test case — prices collapsed into 2009. Tracker should NOT confirm ongoing shock transmission.',
    },
]


# ── FRED fetch (vintage-agnostic — uses current revised data) ──────────

def fred_fetch(series_id, start_date=None, end_date=None, freq=None):
    """Fetch full observation history between two dates (inclusive)."""
    if not FRED_KEY:
        print(f'  ⚠ FRED key missing — skipping {series_id}')
        return []
    params = {
        'series_id':   series_id,
        'api_key':     FRED_KEY,
        'file_type':   'json',
        'sort_order':  'asc',
        'limit':       2000,
    }
    if start_date: params['observation_start'] = start_date
    if end_date:   params['observation_end']   = end_date
    if freq:       params['frequency']         = freq
    url = 'https://api.stlouisfed.org/fred/series/observations'
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return [{'date': o['date'], 'value': float(o['value'])}
                for o in r.json().get('observations', []) if o['value'] != '.']
    except Exception as e:
        print(f'  ⚠ FRED {series_id} fetch failed: {e}')
        return []


# ── Phase series registry (mirrors METHODOLOGY.md §2) ──────────────────

PHASES = [
    {'phase': 'Pump Prices Spike',        'kind': 'level',    'series': 'GASREGW',       'expected_weeks': [0, 2],  'baseline_threshold': 0.50},
    {'phase': 'Transport & Freight',      'kind': 'mma',      'series': 'CUSR0000SETG',  'expected_weeks': [4, 6]},
    {'phase': 'CPI Energy Prints',        'kind': 'mma',      'series': 'CPIENGSL',      'expected_weeks': [6, 14]},
    {'phase': 'Food & Services',          'kind': 'mma',      'series': 'CUSR0000SEFV',  'expected_weeks': [12, 20]},
    {'phase': 'Core Goods Inflation',     'kind': 'yoy',      'series': 'CPILFESL',      'expected_weeks': [20, 32], 'baseline_threshold': 0.5},
    {'phase': 'Consumer Sentiment Falls', 'kind': 'level',    'series': 'UMCSENT',       'expected_weeks': [2, 6],   'baseline_threshold': 0.5, 'sign': -1},
    {'phase': 'Savings Drawdown',         'kind': 'level',    'series': 'PSAVERT',       'expected_weeks': [8, 16],  'baseline_threshold': 0.5, 'sign': -1},
    {'phase': 'Delinquencies Climb',      'kind': 'level',    'series': 'DRCCLACBS',     'expected_weeks': [20, 40], 'baseline_threshold': 0.15},
]


# ── Methodology functions (ported from renderer.update_shock_tracker) ──
# IMPORTANT: keep these in lock-step with renderer.py. When thresholds
# change in METHODOLOGY.md, update both this file and the renderer.

def latest_mom_ann(series_newest_first):
    """(V_latest / V_prior)^12 − 1, in %. None if < 2 obs."""
    if not series_newest_first or len(series_newest_first) < 2: return None
    cur, prev = series_newest_first[0]['value'], series_newest_first[1]['value']
    if not prev: return None
    return round(((cur / prev) ** 12 - 1) * 100, 1)


def pre_shock_6mma(series_newest_first, shock_iso):
    """Compound 6-month MoM ending in last pre-shock obs, annualized."""
    if not series_newest_first: return None
    pre_idx = next((i for i, o in enumerate(series_newest_first) if o['date'] < shock_iso), None)
    if pre_idx is None or len(series_newest_first) < pre_idx + 7: return None
    cur = series_newest_first[pre_idx]['value']
    prior = series_newest_first[pre_idx + 6]['value']
    if not prior: return None
    return round(((cur / prior) ** 2 - 1) * 100, 1)


def mma_status(post_mma, pre_mma, weeks_elapsed, expected_weeks, data_is_post_shock):
    if post_mma is None: return 'awaiting_data'
    if pre_mma is None or not data_is_post_shock: return 'not_yet'
    delta = post_mma - pre_mma
    in_window     = expected_weeks[0] <= weeks_elapsed <= expected_weeks[1]
    past_window   = weeks_elapsed > expected_weeks[1]
    before_window = weeks_elapsed < expected_weeks[0]
    if delta > 0.5 and before_window:
        return 'ahead'
    if delta > 1.5 and (in_window or past_window):
        return 'confirmed'
    if delta > 0.5 and (in_window or past_window):
        return 'emerging'
    return 'on_schedule' if in_window else 'not_yet'


def level_status(now, pre, weeks_elapsed, expected_weeks, threshold, data_is_post_shock, sign=1):
    """Used for pump prices, sentiment, savings, delinquencies, core CPI.
    sign=-1 means shock predicts a DROP. chg is SIGNED after the sign flip —
    opposite-direction moves never confirm (see METHODOLOGY.md §1.4).
    Mirrors renderer.py:_status — keep in sync."""
    if now is None or pre is None: return 'awaiting_data'
    if not data_is_post_shock: return 'not_yet'
    chg = (now - pre) * sign  # positive = shock-consistent direction
    in_window     = expected_weeks[0] <= weeks_elapsed <= expected_weeks[1]
    past_window   = weeks_elapsed > expected_weeks[1]
    before_window = weeks_elapsed < expected_weeks[0]
    moved = chg > 0.15
    if moved and before_window:
        return 'ahead'
    if moved and (in_window or past_window):
        return 'confirmed' if chg > threshold else 'emerging'
    return 'on_schedule' if in_window else 'not_yet'


# ── Backtest engine ────────────────────────────────────────────────────

SNAPSHOT_WEEKS = [2, 4, 8, 13, 26]  # when post-shock we'd "look" at the tracker


def snapshots_for(shock):
    """Date ISO strings for each snapshot, plus weeks elapsed."""
    sd = datetime.date.fromisoformat(shock['shock_date'])
    out = []
    for w in SNAPSHOT_WEEKS:
        snap = sd + datetime.timedelta(weeks=w)
        out.append({'weeks': w, 'snapshot_date': snap.isoformat()})
    return out


def run_phase_for_shock(phase, shock, all_series):
    """Evaluate one phase across each snapshot for one shock.
    Returns list of {weeks, snapshot_date, status, post_mma/pre_mma/chg, ...}."""
    series_id = phase['series']
    raw = all_series.get(series_id, [])
    if not raw:
        return [{'weeks': s['weeks'], 'snapshot_date': s['snapshot_date'],
                 'status': 'awaiting_data', 'note': 'series unavailable'}
                for s in snapshots_for(shock)]

    # Sort newest-first (FRED fetch was asc; we need desc for the helpers)
    raw_desc = list(reversed(raw))
    out = []
    for snap in snapshots_for(shock):
        # Slice the series to only obs up to the snapshot date
        as_of = [o for o in raw_desc if o['date'] <= snap['snapshot_date']]
        if not as_of:
            out.append({**snap, 'status': 'awaiting_data', 'note': 'no data before snapshot'})
            continue

        latest_date = as_of[0]['date']
        data_is_post_shock = latest_date >= shock['shock_date']
        row = {'weeks': snap['weeks'], 'snapshot_date': snap['snapshot_date'],
               'latest_obs_date': latest_date, 'latest_value': as_of[0]['value']}

        if phase['kind'] == 'mma':
            post = latest_mom_ann(as_of)
            pre  = pre_shock_6mma(as_of, shock['shock_date'])
            status = mma_status(post, pre, snap['weeks'], phase['expected_weeks'], data_is_post_shock)
            row.update({'post_mma': post, 'pre_6mma': pre,
                        'delta_pp': round(post - pre, 2) if (post is not None and pre is not None) else None,
                        'status': status})
        elif phase['kind'] == 'level':
            pre_obs = next((o for o in as_of if o['date'] < shock['shock_date']), None)
            pre = pre_obs['value'] if pre_obs else None
            now = as_of[0]['value']
            sign = phase.get('sign', 1)
            status = level_status(now, pre, snap['weeks'], phase['expected_weeks'],
                                  phase['baseline_threshold'], data_is_post_shock, sign)
            row.update({'pre_value': pre, 'now_value': now,
                        'chg': round((now - pre) * sign, 2) if pre is not None else None,
                        'status': status})
        elif phase['kind'] == 'yoy':
            # 12-month YoY from monthly index
            yoy = None
            if len(as_of) >= 13 and as_of[12]['value']:
                yoy = round((as_of[0]['value'] - as_of[12]['value']) / as_of[12]['value'] * 100, 1)
            pre_obs = next((o for o in as_of if o['date'] < shock['shock_date']), None)
            pre_yoy = None
            if pre_obs:
                idx = next((i for i, o in enumerate(as_of) if o['date'] == pre_obs['date']), None)
                if idx is not None and len(as_of) >= idx + 13 and as_of[idx + 12]['value']:
                    pre_yoy = round((pre_obs['value'] - as_of[idx + 12]['value']) / as_of[idx + 12]['value'] * 100, 1)
            status = 'not_yet'
            if yoy is not None and pre_yoy is not None and data_is_post_shock:
                chg = yoy - pre_yoy  # SIGNED — only confirm on acceleration, not deflation
                in_window = phase['expected_weeks'][0] <= snap['weeks'] <= phase['expected_weeks'][1]
                past_window = snap['weeks'] > phase['expected_weeks'][1]
                if chg > phase['baseline_threshold'] and (in_window or past_window):
                    status = 'confirmed'
                elif in_window:
                    status = 'on_schedule'
            row.update({'yoy': yoy, 'pre_yoy': pre_yoy, 'status': status})

        out.append(row)
    return out


def backtest(shock):
    print(f"\n── {shock['name']} (shock {shock['shock_date']}) ──")
    # Fetch each phase's series with buffer: 3y before shock → 1y after
    sd = datetime.date.fromisoformat(shock['shock_date'])
    start = (sd - datetime.timedelta(days=365 * 3)).isoformat()
    end   = (sd + datetime.timedelta(days=365)).isoformat()
    all_series = {}
    for p in PHASES:
        print(f"  Fetching {p['series']} ...")
        all_series[p['series']] = fred_fetch(p['series'], start_date=start, end_date=end)
        time.sleep(0.2)  # be nice to FRED

    result = {
        'shock': shock,
        'snapshots': [s['snapshot_date'] for s in snapshots_for(shock)],
        'phases': [],
    }
    for p in PHASES:
        phase_result = {
            'phase':          p['phase'],
            'series':         p['series'],
            'kind':           p['kind'],
            'expected_weeks': p['expected_weeks'],
            'snapshots':      run_phase_for_shock(p, shock, all_series),
        }
        result['phases'].append(phase_result)
    return result


# ── Report generation ──────────────────────────────────────────────────

STATUS_ICON = {'confirmed': '✅', 'emerging': '🟡', 'ahead': '🔴',
               'on_schedule': '🟦', 'not_yet': '⏳', 'awaiting_data': '—'}


def write_md_report(results):
    lines = [
        '# Backtest Calibration Report',
        '',
        f'Generated: {datetime.datetime.utcnow().isoformat()}Z',
        '',
        'This report replays the current Oil Impact Chain confirmation rules',
        '(see `METHODOLOGY.md`) against historical oil shocks to calibrate the',
        'MMA thresholds (+1.5pp Confirmed, +0.5pp Emerging) and phase-timing windows.',
        '',
        '⚠ Uses current revised FRED data, not as-of-snapshot vintages. See',
        '`METHODOLOGY.md` §4 for the ALFRED vintage-pinning follow-up.',
        '',
    ]
    for r in results:
        s = r['shock']
        lines += [
            f"## {s['name']}",
            '',
            f"- Shock date: `{s['shock_date']}`",
            f"- WTI pre-shock: ${s['wti_pre']:.2f}",
            f"- WTI peak: ${s['wti_peak']:.2f} (+{s['wti_peak_chg_pct']}%)",
            f"- Notes: {s['notes']}",
            '',
            'Phase status by weeks-elapsed snapshot:',
            '',
            '| Phase | Kind | +2w | +4w | +8w | +13w | +26w |',
            '|---|---|---|---|---|---|---|',
        ]
        for p in r['phases']:
            snaps = {s['weeks']: s for s in p['snapshots']}
            row = [p['phase'], p['kind']]
            for w in SNAPSHOT_WEEKS:
                snap = snaps.get(w, {})
                row.append(f"{STATUS_ICON.get(snap.get('status','—'),'?')} {snap.get('status','—')}")
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
        # Per-phase detail for shocks that "confirmed"
        lines.append('<details><summary>Per-phase detail</summary>')
        lines.append('')
        for p in r['phases']:
            lines.append(f"### {p['phase']} ({p['series']})")
            lines.append('')
            for snap in p['snapshots']:
                kv = ' · '.join(f"{k}={v}" for k, v in snap.items()
                                if k not in ('weeks','snapshot_date','status','latest_obs_date','latest_value')
                                and v is not None)
                lines.append(f"- +{snap['weeks']}w ({snap['snapshot_date']}): **{snap['status']}** · latest obs {snap.get('latest_obs_date','?')} · {kv}")
            lines.append('')
        lines.append('</details>')
        lines.append('')

    # Calibration summary
    lines += [
        '---',
        '',
        '## Calibration observations',
        '',
        '_Fill in after inspecting the tables above. Questions to answer:_',
        '',
        '1. **Did Phase 3 (CPI Energy) confirm in the expected 6–10 week window** for',
        '   the 2022 Ukraine shock?',
        '2. **Did Phase 1 (Pump Prices) confirm within 2 weeks** in both shocks?',
        '3. **Did the tracker correctly NOT confirm** phases during the 2008 post-peak',
        '   collapse (where shock was peaking, not accelerating)?',
        '4. **Were there phases that confirmed far outside their expected window** —',
        '   suggesting the window needs adjustment?',
        '5. **Were any thresholds obviously too tight or too loose** based on the',
        '   magnitude of deltas observed?',
        '',
        'If (1)–(4) all pass, current thresholds are defensible. If not, recalibrate',
        'in `renderer.py:_mma_status` / `_status` and update `METHODOLOGY.md` §1.3.',
        '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'\n  ✅ Wrote {OUT_MD.name}')


def main():
    if not FRED_KEY:
        print('ERROR: FRED_API_KEY not set — cannot fetch historical data')
        print('Set FRED_API_KEY in env or .env and retry')
        sys.exit(2)

    results = [backtest(s) for s in SHOCKS]

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')
    print(f'\n  ✅ Wrote {OUT_JSON.name}')
    write_md_report(results)

    # Surface a one-line summary to stdout for CI
    confirmed_counts = []
    for r in results:
        name = r['shock']['name']
        latest_snap = r['phases'][0]['snapshots'][-1]  # +26w for phase 1
        confirmed = sum(1 for p in r['phases']
                        if any(s['status'] == 'confirmed' for s in p['snapshots']))
        confirmed_counts.append(f"{name}: {confirmed}/{len(r['phases'])} confirmed at some snapshot")
    print('\nSummary:')
    for c in confirmed_counts:
        print(f'  - {c}')


if __name__ == '__main__':
    main()
