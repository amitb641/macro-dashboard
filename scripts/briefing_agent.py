#!/usr/bin/env python3
"""
Agent 3 — ANALYST  (briefing_agent.py)
Reads signals.json. Calls claude-sonnet-4-6 to write macro commentary.
Only agent that uses an LLM (~8K token prompt → JSON output).
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

SYSTEM = """You are a senior macro strategist at an institutional investment firm.
Write precise, data-driven commentary for an internal dashboard read by PMs and analysts.

Rules:
- Use exact numbers provided. Never invent figures.
- 2-4 sentences per commentary block. Be direct — no hedging clichés.
- Flag genuine risks clearly. Don't soften alarming signals.
- Return ONLY valid JSON — no markdown fences, no preamble."""


def build_prompt(sig: dict) -> str:
    v    = sig.get('values', {})
    risk = sig.get('risk_level', 'MODERATE')
    hl   = sig.get('headlines', [])
    today = datetime.date.today().strftime('%B %d, %Y')

    def fv(k, dec=2, sfx=''):
        val = v.get(k)
        return f'{val:.{dec}f}{sfx}' if val is not None else 'N/A'

    headline_block = '\n'.join(h['line'] for h in hl) if hl else 'No major changes vs prior snapshot.'

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

Respond with this exact JSON (no markdown):
{{
  "generated_at": "{today}",
  "risk_level": "{risk}",
  "risk_rationale": "2-3 sentence explanation of the risk level and key drivers",
  "outlook_headline": "One sharp sentence summarizing current macro posture",
  "outlook_body": "3-4 sentence macro bottom line for the Outlook tab",
  "tabs": {{
    "gdp":     "2-3 sentences on GDP trajectory and key risks",
    "jobs":    "2-3 sentences on labor market — NFP trend, leading vs lagging",
    "unemp":   "2-3 sentences on unemployment rate, breadth, U-6 divergence",
    "wages":   "2-3 sentences on wage growth, real vs nominal, inflation implications",
    "cpi":     "2-3 sentences on CPI headline vs core, trend, Fed implications",
    "pce":     "2-3 sentences on PCE, saving rate, consumer health",
    "yield":   "2-3 sentences on yield curve, Fed path, rate outlook",
    "credit":  "2-3 sentences on IG/HY spreads, credit conditions, risk appetite",
    "housing": "2-3 sentences on mortgage rates, affordability, supply/demand balance",
    "oil":     "2-3 sentences on WTI/Brent, supply/demand, macro transmission",
    "banks":   "2-3 sentences on bank earnings themes, NII outlook, consumer credit quality"
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
    try:
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
            timeout=60,
        )
        r.raise_for_status()
        text = r.json()['content'][0]['text'].strip()
        if text.startswith('```'): text = text.split('```')[1]
        if text.startswith('json'): text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f'  ❌ Claude call failed: {e}')
        return _fallback()


def _fallback() -> dict:
    today = datetime.date.today().strftime('%B %d, %Y')
    msg = 'Data refreshed. Add ANTHROPIC_API_KEY to GitHub Secrets for AI commentary.'
    return {
        'generated_at':    today,
        'risk_level':      'MODERATE',
        'risk_rationale':  msg,
        'outlook_headline': msg,
        'outlook_body':     msg,
        'tabs':            {k: msg for k in ['gdp','jobs','unemp','wages','cpi',
                                             'pce','yield','credit','housing','oil','banks']},
        'kpi_updates':     {'risk_posture':'Neutral','macro_regime':'Expansion','fed_bias':'On Hold'},
        'signal_flags':    [],
    }


def run():
    print('[Agent 3 — Analyst] Starting...')
    if not SIG_FILE.exists():
        print('ERROR: signals.json missing — run analyzer.py first'); sys.exit(1)

    sig    = json.loads(SIG_FILE.read_text())
    prompt = build_prompt(sig)
    print(f'  Prompt: {len(prompt):,} chars')

    result = call_claude(prompt)
    result['agent3_ran_at'] = datetime.datetime.utcnow().isoformat() + 'Z'

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, indent=2))

    print(f'[Agent 3] Done → data/analysis.json')
    print(f'  Posture: {result.get("kpi_updates",{}).get("risk_posture")}  '
          f'Regime: {result.get("kpi_updates",{}).get("macro_regime")}  '
          f'Flags: {len(result.get("signal_flags",[]))}')
    return True


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
