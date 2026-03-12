#!/usr/bin/env python3
"""
Agent 5 — PUBLISHER  (publisher.py)
• Saves snapshot.json  →  Agent 2's memory for next month's diff
• Sends HTML briefing email via Gmail API (OAuth)
• Writes data/last_update.json run log
No LLM used. Final stage.
"""

import os, json, base64, datetime, sys
from pathlib import Path

try:
    import requests
except ImportError:
    print('pip install requests'); sys.exit(1)

# Resend email API (simple, no OAuth)
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
EMAIL_FROM     = os.environ.get('EMAIL_FROM', 'onboarding@resend.dev')
EMAIL_TO       = os.environ.get('EMAIL_TO', '')

ROOT      = Path(__file__).parent.parent
SIG_FILE  = ROOT / 'data' / 'signals.json'
ANA_FILE  = ROOT / 'data' / 'analysis.json'
LOG_FILE  = ROOT / 'data' / 'last_update.json'

DASHBOARD_URL = 'https://amitb641.github.io/macro-dashboard/macro_dashboard_v6.html'


# ── Snapshot (Agent 2 memory) ─────────────────────────────────────────

# save_snapshot merged into save_log — single last_update.json file


# ── Run log ───────────────────────────────────────────────────────────

def save_log(sig, ana):
    """Single file for both run log AND Agent 2 snapshot memory."""
    log = {
        'run_date':      datetime.date.today().isoformat(),
        'completed_at':  datetime.datetime.utcnow().isoformat() + 'Z',
        'risk_level':    sig.get('risk_level'),
        'alert_count':   sig.get('alert_count', 0),
        'flagged_count': sig.get('flagged_count', 0),
        'risk_posture':  (ana or {}).get('kpi_updates', {}).get('risk_posture'),
        'macro_regime':  (ana or {}).get('kpi_updates', {}).get('macro_regime'),
        'key_values': {k: sig.get('values', {}).get(k) for k in
                       ['ffr','dgs10','dgs2','ig_oas','hy_oas','unrate',
                        'cpi_yoy','core_pce_yoy','wti','mortgage30']},
        # Agent 2 reads this to diff signals on next run
        'values': sig.get('values', {}),
    }
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))
    print(f'  ✅ last_update.json saved (run log + Agent 2 snapshot)')


# ── Email HTML ────────────────────────────────────────────────────────

def build_email(sig, ana, today_str):
    v    = sig.get('values', {})
    risk = sig.get('risk_level', 'MODERATE')
    kpis = (ana or {}).get('kpi_updates', {})
    tabs = (ana or {}).get('tabs', {})
    flags = (ana or {}).get('signal_flags', [])

    risk_col = {'LOW':'#0D7A4A','MODERATE':'#B45309','ELEVATED':'#C0392B','HIGH':'#7F1D1D'}.get(risk,'#B45309')

    def fv(k, dec=2, sfx=''):
        val = v.get(k)
        return f'{val:.{dec}f}{sfx}' if val is not None else '—'

    def row(lbl, val, note=''):
        return (f'<tr><td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;'
                f'font-size:12px;color:#475569">{lbl}</td>'
                f'<td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;'
                f'font-size:12px;font-weight:700;color:#1E293B">{val}</td>'
                f'<td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;'
                f'font-size:11px;color:#94A3B8">{note}</td></tr>')

    tab_html = ''.join(
        f'<div style="margin-bottom:10px">'
        f'<b style="font-size:11px;color:#1E293B;text-transform:uppercase;letter-spacing:.05em">{k}</b>'
        f'<p style="margin:3px 0 0;font-size:12px;color:#475569;line-height:1.6">{txt}</p></div>'
        for k, txt in tabs.items() if txt
    )

    flag_html = ''.join(
        f'<div style="padding:7px 12px;margin-bottom:5px;background:#FEF3C7;'
        f'border-left:3px solid #B45309;border-radius:4px">'
        f'<b style="font-size:11px;color:#92400E">{f["metric"]}: {f["reading"]}</b>'
        f'<p style="margin:2px 0 0;font-size:11px;color:#78350F">{f["note"]}</p></div>'
        for f in flags
    ) or '<p style="font-size:12px;color:#94A3B8">No active signal alerts this run.</p>'

    utc = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#F8FAFC;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:640px;margin:24px auto;background:#fff;border-radius:12px;
overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">

  <div style="background:#1A56DB;padding:24px 28px">
    <div style="font-size:10px;font-weight:700;letter-spacing:.15em;color:rgba(255,255,255,.6);
    text-transform:uppercase;margin-bottom:6px">U.S. Macro Dashboard · Briefing Agent</div>
    <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px">Monthly Briefing — {today_str}</div>
    <div style="font-size:12px;color:rgba(255,255,255,.7)">{DASHBOARD_URL}</div>
  </div>

  <div style="background:{risk_col};padding:10px 28px">
    <span style="font-size:12px;font-weight:700;color:#fff;letter-spacing:.06em">RISK: {risk}</span>
    <span style="font-size:11px;color:rgba(255,255,255,.8);margin-left:16px">
      Posture: {kpis.get('risk_posture','—')} · Regime: {kpis.get('macro_regime','—')} · Fed: {kpis.get('fed_bias','—')}
    </span>
  </div>

  <div style="padding:24px 28px">
    <h2 style="font-size:13px;font-weight:700;color:#1E293B;margin:0 0 10px;
    border-bottom:1px solid #f1f5f9;padding-bottom:8px">📊 Macro Snapshot</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      {row('Fed Funds Rate',    fv('ffr',2,'%'))}
      {row('10Y Treasury',      fv('dgs10',2,'%'),   f"vs 2Y: {fv('spread_10_2_bp',0,'bp')}")}
      {row('IG OAS',            fv('ig_oas',0,'bp'),  'Investment grade spread')}
      {row('HY OAS',            fv('hy_oas',0,'bp'),  'High yield spread')}
      {row('Unemployment U-3',  fv('unrate',1,'%'))}
      {row('CPI YoY',           fv('cpi_yoy',1,'%'))}
      {row('Core PCE YoY',      fv('core_pce_yoy',1,'%'), "Fed target: 2.0%")}
      {row('WTI Crude',         '$' + fv('wti',1))}
      {row('30Y Mortgage',      fv('mortgage30',2,'%'))}
    </table>

    <h2 style="font-size:13px;font-weight:700;color:#1E293B;margin:0 0 10px;
    border-bottom:1px solid #f1f5f9;padding-bottom:8px">⚠️ Signal Flags</h2>
    <div style="margin-bottom:20px">{flag_html}</div>

    <h2 style="font-size:13px;font-weight:700;color:#1E293B;margin:0 0 10px;
    border-bottom:1px solid #f1f5f9;padding-bottom:8px">🔍 Tab Analysis</h2>
    <div style="margin-bottom:20px">{tab_html}</div>

    <div style="text-align:center;padding:16px 0">
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#1A56DB;color:#fff;
      text-decoration:none;padding:12px 28px;border-radius:24px;font-size:13px;font-weight:700">
        → Open Full Dashboard</a>
    </div>
  </div>

  <div style="background:#F8FAFC;padding:10px 28px;border-top:1px solid #f1f5f9">
    <p style="font-size:10px;color:#94A3B8;margin:0">
      5-agent pipeline · briefing_agent.py · claude-sonnet-4-6 · FRED · BLS · EIA · {utc}
    </p>
  </div>
</div></body></html>"""


# ── Resend API send ───────────────────────────────────────────────────

def send_email(html_body, today_str):
    """Send via Resend API — just an API key, no OAuth needed."""
    if not RESEND_API_KEY:
        print('  ⚠  RESEND_API_KEY not set — skipping email')
        return
    if not EMAIL_TO:
        print('  ⚠  EMAIL_TO not set — skipping email')
        return
    try:
        r = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {RESEND_API_KEY}',
                     'Content-Type': 'application/json'},
            json={
                'from':    EMAIL_FROM,
                'to':      [EMAIL_TO],
                'subject': f'📊 Macro Dashboard — {today_str}',
                'html':    html_body,
            },
            timeout=20,
        )
        if r.status_code in (200, 201):
            print(f'  ✅ Email sent to {EMAIL_TO} via Resend')
        else:
            print(f'  ⚠  Resend failed: {r.status_code} {r.text[:200]}')
    except Exception as e:
        print(f'  ⚠  Resend error: {e}')


# ══════════════════════════════════════════════════════════════════════

def publish(snapshot_only=False):
    print('[Agent 5 — Publisher] Starting...')
    today_str = datetime.date.today().strftime('%B %d, %Y')

    sig = json.loads(SIG_FILE.read_text())
    ana = json.loads(ANA_FILE.read_text()) if ANA_FILE.exists() else None

    save_log(sig, ana)

    if not snapshot_only:
        html_body = build_email(sig, ana, today_str)
        send_email(html_body, today_str)
    else:
        print("  ℹ  Snapshot-only mode — skipping email")

    print(f'[Agent 5] Done — {today_str}')
    return True


if __name__ == '__main__':
    snapshot_only = '--snapshot-only' in sys.argv
    sys.exit(0 if publish(snapshot_only=snapshot_only) else 1)
