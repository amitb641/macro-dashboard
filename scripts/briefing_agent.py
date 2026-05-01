#!/usr/bin/env python3
"""
Agent 3 — ANALYST  (briefing_agent.py)
Reads signals.json. Calls claude-sonnet-4-6 to write macro commentary.
Only agent that uses an LLM.
Smart refresh: only regenerates commentary for tabs whose data changed.
Output: data/analysis.json
"""

import os, json, datetime, sys
from pathlib import Path

try:
    import requests
except ImportError:
    print('pip install requests'); sys.exit(1)

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

ROOT     = Path(__file__).parent.parent
SIG_FILE = ROOT / 'data' / 'signals.json'
OUT_FILE = ROOT / 'data' / 'analysis.json'
LAST_FILE = ROOT / 'data' / 'last_update.json'

SYSTEM = """You are a senior macro strategist at an institutional investment firm.
Write precise, data-driven commentary for an internal dashboard read by PMs and analysts.

Rules:
- Use exact numbers provided. Never invent figures.
- 2-4 sentences per commentary block. Be direct — no hedging clichés.
- Flag genuine risks clearly. Don't soften alarming signals.
- Return ONLY valid JSON — no markdown fences, no preamble."""

# ── Tab → data dependencies ──────────────────────────────────────────
# Maps each tab to the signal keys that drive its commentary.
# If ANY key in the list changed, that tab gets fresh commentary.

TAB_DEPS = {
    'yield':   ['ffr', 'dgs2', 'dgs5', 'dgs10', 'dgs30', 'ig_oas', 'hy_oas', 'spread_10_2_bp'],
    'oil':     ['wti', 'brent'],
    'credit':  ['ig_oas', 'hy_oas', 'cc_delinq', 'tdsp'],
    'jobs':    ['nfp_mom', 'nfp_level', 'icsa', 'ccsa'],
    'unemp':   ['unrate', 'u6rate'],
    'wages':   ['wages_yoy'],
    'cpi':     ['cpi_yoy', 'core_cpi_yoy'],
    'pce':     ['pce_yoy', 'core_pce_yoy', 'saving_rate'],
    'housing': ['mortgage30', 'housing_starts', 'cs_hpi_yoy'],
    'gdp':     ['gdp_growth_q'],
    'banks':   ['cc_delinq', 'ig_oas', 'hy_oas', 'ffr'],
}

# Thresholds: minimum change to consider "moved" (avoids noise)
CHANGE_THRESHOLDS = {
    'ffr': 0.01, 'dgs2': 0.03, 'dgs5': 0.03, 'dgs10': 0.03, 'dgs30': 0.03,
    'ig_oas': 3, 'hy_oas': 10, 'spread_10_2_bp': 3,
    'wti': 1.0, 'brent': 1.0,
    'unrate': 0.1, 'u6rate': 0.1,
    'nfp_mom': 20, 'nfp_level': 50, 'icsa': 5000, 'ccsa': 10000,
    'wages_yoy': 0.1,
    'cpi_yoy': 0.1, 'core_cpi_yoy': 0.1,
    'pce_yoy': 0.1, 'core_pce_yoy': 0.1, 'saving_rate': 0.2,
    'mortgage30': 0.05, 'housing_starts': 20, 'cs_hpi_yoy': 0.3,
    'gdp_growth_q': 0.1,
    'cc_delinq': 0.1, 'tdsp': 0.1,
}


def detect_changed_tabs(current_values: dict, prior_values: dict) -> list:
    """Compare current vs prior values and return list of tabs needing refresh."""
    if not prior_values:
        return list(TAB_DEPS.keys())  # First run — refresh everything

    changed_tabs = []
    for tab, keys in TAB_DEPS.items():
        for key in keys:
            curr = current_values.get(key)
            prev = prior_values.get(key)
            if curr is None or prev is None:
                if curr != prev:  # One is None, other isn't
                    changed_tabs.append(tab)
                    break
                continue
            threshold = CHANGE_THRESHOLDS.get(key, 0)
            if abs(curr - prev) > threshold:
                changed_tabs.append(tab)
                break

    return changed_tabs


# ── Always-refresh tabs: outlook, KPIs, risk, signal_flags ───────────
# These are top-level summary fields that should reflect the latest
# signal mix even if individual tab data didn't change.

ALWAYS_REFRESH_FIELDS = ['risk_rationale', 'outlook_headline', 'outlook_body',
                         'kpi_updates', 'signal_flags']


def build_prompt(sig: dict, changed_tabs: list) -> str:
    v    = sig.get('values', {})
    risk = sig.get('risk_level', 'MODERATE')
    hl   = sig.get('headlines', [])
    today = datetime.date.today().strftime('%B %d, %Y')

    def fv(k, dec=2, sfx=''):
        val = v.get(k)
        return f'{val:.{dec}f}{sfx}' if val is not None else 'N/A'

    headline_block = '\n'.join(h['line'] for h in hl) if hl else 'No major changes vs prior snapshot.'

    # Build tab request block — only for changed tabs
    tab_descriptions = {
        'gdp':     '"2-3 sentences on GDP trajectory and key risks"',
        'jobs':    '"2-3 sentences on labor market — NFP trend, leading vs lagging"',
        'unemp':   '"2-3 sentences on unemployment rate, breadth, U-6 divergence"',
        'wages':   '"2-3 sentences on wage growth, real vs nominal, inflation implications"',
        'cpi':     '"2-3 sentences on CPI headline vs core, trend, Fed implications"',
        'pce':     '"2-3 sentences on PCE, saving rate, consumer health"',
        'yield':   '"2-3 sentences on yield curve, Fed path, rate outlook"',
        'credit':  '"2-3 sentences on IG/HY spreads, credit conditions, risk appetite"',
        'housing': '"2-3 sentences on mortgage rates, affordability, supply/demand balance"',
        'oil':     '"2-3 sentences on WTI/Brent, supply/demand, macro transmission"',
        'banks':   '"2-3 sentences on bank earnings themes, NII outlook, consumer credit quality"',
    }

    tab_block = ',\n    '.join(
        f'"{t}": {tab_descriptions[t]}' for t in changed_tabs
    )

    return f"""Today: {today} | Overall risk level: {risk}

CURRENT READINGS:
Fed Funds: {fv('ffr',2,'%')}  |  10Y: {fv('dgs10',2,'%')}  |  2Y: {fv('dgs2',2,'%')}  |  10Y-2Y: {fv('spread_10_2_bp',0,'bp')}
IG OAS: {fv('ig_oas',0,'bp')}  |  HY OAS: {fv('hy_oas',0,'bp')}
Unemployment U-3: {fv('unrate',1,'%')}  |  U-6: {fv('u6rate',1,'%')}
NFP MoM: {fv('nfp_mom',0,'K')}  |  Wages YoY: {fv('wages_yoy',1,'%')}
CPI YoY: {fv('cpi_yoy',1,'%')}  |  Core CPI: {fv('core_cpi_yoy',1,'%')}
PCE YoY: {fv('pce_yoy',1,'%')}  |  Core PCE: {fv('core_pce_yoy',1,'%')}
Saving Rate: {fv('saving_rate',1,'%')}
30Y Mortgage: {fv('mortgage30',2,'%')}  |  Housing Starts: {fv('housing_starts',0,'K')}
WTI: ${fv('wti',1)}  |  Brent: ${fv('brent',1)}
Real GDP Growth (latest Q): {fv('gdp_growth_q',1,'%')} annualized
CC Delinquency: {fv('cc_delinq',1,'%')}

FLAGGED SIGNAL CHANGES VS PRIOR SNAPSHOT:
{headline_block}

Write commentary ONLY for the tabs listed below (data changed for these).
Respond with this exact JSON (no markdown):
{{
  "generated_at": "{today}",
  "risk_level": "{risk}",
  "risk_rationale": "2-3 sentence explanation of the risk level and key drivers",
  "outlook_headline": "One sharp sentence summarizing current macro posture",
  "outlook_body": "3-4 sentence macro bottom line for the Outlook tab",
  "tabs": {{
    {tab_block}
  }},
  "kpi_updates": {{
    "risk_posture": "one of: Defensive | Cautious | Neutral | Constructive | Risk-On",
    "macro_regime": "one of: Expansion | Late Cycle | Slowdown | Contraction | Recovery",
    "fed_bias":     "one of: Hawkish | Neutral | Dovish | On Hold"
  }},
  "signal_flags": [
    {{"metric":"...", "reading":"...", "flag":"watch|alert", "note":"why it matters"}}
  ]
}}"""


def call_claude(prompt: str) -> dict:
    if not ANTHROPIC_KEY:
        print('  ⚠  No ANTHROPIC_API_KEY — using static fallback')
        return _fallback()
    print('  Calling claude-sonnet-4-6...')
    import time
    last_err = None
    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 2 ** attempt
                print(f'  Retry {attempt}/2 after {wait}s...')
                time.sleep(wait)
            r = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': ANTHROPIC_KEY,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': 'claude-sonnet-4-6',
                    'max_tokens': 2000,
                    'system': SYSTEM,
                    'messages': [{'role': 'user', 'content': prompt}],
                },
                timeout=90,
            )
            r.raise_for_status()
            text = r.json()['content'][0]['text'].strip()
            if text.startswith('```'): text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            last_err = e
            print(f'  ❌ Claude call failed (attempt {attempt+1}/3): {e}')
    print(f'  ❌ All retries exhausted. Last error: {last_err}')
    return _fallback()


ALL_TABS = ['gdp', 'jobs', 'unemp', 'wages', 'cpi', 'pce', 'yield', 'credit', 'housing', 'oil', 'banks']


def _fallback() -> dict:
    today = datetime.date.today().strftime('%B %d, %Y')
    return {
        'generated_at':    today,
        'risk_level':      'MODERATE',
        'risk_rationale':  '',
        'outlook_headline': '',
        'outlook_body':     '',
        'tabs':            {k: '' for k in ALL_TABS},
        'kpi_updates':     {'risk_posture': 'Neutral', 'macro_regime': 'Expansion', 'fed_bias': 'On Hold'},
        'signal_flags':    [],
    }


def run():
    print('[Agent 3 — Analyst] Starting...')
    if not SIG_FILE.exists():
        print('ERROR: signals.json missing — run analyzer.py first'); sys.exit(1)

    sig = json.loads(SIG_FILE.read_text())
    current_values = sig.get('values', {})

    # Load prior values for change detection
    prior_values = {}
    if LAST_FILE.exists():
        try:
            prior_values = json.loads(LAST_FILE.read_text()).get('values', {})
        except (json.JSONDecodeError, OSError):
            pass

    # Load existing commentary to carry forward unchanged tabs
    prior_analysis = {}
    if OUT_FILE.exists():
        try:
            prior_analysis = json.loads(OUT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Detect which tabs need fresh commentary
    force_all = os.environ.get('FORCE_AI', 'false').lower() == 'true'
    changed_tabs = ALL_TABS if force_all else detect_changed_tabs(current_values, prior_values)

    # If no prior analysis exists, refresh everything
    prior_tabs = prior_analysis.get('tabs', {})
    if not any(prior_tabs.get(t) for t in ALL_TABS):
        changed_tabs = ALL_TABS

    skipped_tabs = [t for t in ALL_TABS if t not in changed_tabs]

    if changed_tabs:
        print(f'  Tabs to refresh ({len(changed_tabs)}): {", ".join(changed_tabs)}')
        if skipped_tabs:
            print(f'  Tabs carried forward ({len(skipped_tabs)}): {", ".join(skipped_tabs)}')

        prompt = build_prompt(sig, changed_tabs)
        print(f'  Prompt: {len(prompt):,} chars')
        result = call_claude(prompt)
    else:
        print('  No data changes detected — skipping Claude API call')
        result = prior_analysis.copy()
        result['generated_at'] = datetime.date.today().strftime('%B %d, %Y')

    # Merge: carry forward unchanged tabs from prior analysis
    merged_tabs = {}
    for tab in ALL_TABS:
        if tab in changed_tabs:
            merged_tabs[tab] = result.get('tabs', {}).get(tab, '')
        else:
            merged_tabs[tab] = prior_tabs.get(tab, '')
    result['tabs'] = merged_tabs

    result['agent3_ran_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
    result['refreshed_tabs'] = changed_tabs
    result['carried_forward'] = skipped_tabs

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, indent=2))

    print(f'[Agent 3] Done → data/analysis.json')
    print(f'  Posture: {result.get("kpi_updates",{}).get("risk_posture")}  '
          f'Regime: {result.get("kpi_updates",{}).get("macro_regime")}  '
          f'Flags: {len(result.get("signal_flags",[]))}')
    print(f'  Refreshed: {len(changed_tabs)} tabs | Carried forward: {len(skipped_tabs)} tabs')
    return True


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
