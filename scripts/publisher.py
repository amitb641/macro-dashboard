#!/usr/bin/env python3
"""
Agent 5 — PUBLISHER  (publisher.py)
• Saves last_update.json  →  Agent 2's memory for next run
• Sends daily HTML email via Resend with:
    - Key macro headlines (what moved today)
    - Macro snapshot table
    - Signal flags
    - Dashboard attached as HTML file
No LLM used. Final stage.
"""

import os, json, base64, datetime, sys, re
from pathlib import Path

try:
    import requests
except ImportError:
    print('pip install requests'); sys.exit(1)

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
EMAIL_FROM     = os.environ.get('EMAIL_FROM', 'onboarding@resend.dev')
EMAIL_TO       = os.environ.get('EMAIL_TO', '')

ROOT          = Path(__file__).parent.parent
SIG_FILE      = ROOT / 'data' / 'signals.json'
ANA_FILE      = ROOT / 'data' / 'analysis.json'
LOG_FILE      = ROOT / 'data' / 'last_update.json'
HTML_FILE     = ROOT / 'macro_dashboard_v6.html'

DASHBOARD_URL = 'https://amitb641.github.io/macro-dashboard/macro_dashboard_v6.html'


# ── Snapshot / run log ────────────────────────────────────────────────

def save_log(sig, ana):
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
        'values': sig.get('values', {}),
    }
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))
    print('  ✅ last_update.json saved')


# ── Headlines — derive from signals what actually moved today ─────────

def build_headlines(sig, prev_log):
    """
    Compare today's values vs yesterday's last_update.json snapshot.
    Return list of dicts: {emoji, label, value, change, note}
    """
    v    = sig.get('values', {})
    prev = prev_log.get('values', {}) if prev_log else {}

    ITEMS = [
        # (key,          label,              fmt,    emoji, threshold)
        ('ffr',          'Fed Funds Rate',   '{:.2f}%',  '🏦', 0.01),
        ('dgs10',        '10Y Treasury',     '{:.2f}%',  '📈', 0.05),
        ('dgs2',         '2Y Treasury',      '{:.2f}%',  '📈', 0.05),
        ('spread_10_2_bp','10Y–2Y Spread',   '{:+.0f}bp','📐', 5),
        ('ig_oas',       'IG Spread',        '{:.0f}bp', '💳', 5),
        ('hy_oas',       'HY Spread',        '{:.0f}bp', '⚡', 15),
        ('unrate',       'Unemployment',     '{:.1f}%',  '👷', 0.1),
        ('cpi_yoy',      'CPI YoY',          '{:.1f}%',  '🛒', 0.1),
        ('core_pce_yoy', 'Core PCE YoY',     '{:.1f}%',  '💵', 0.1),
        ('wti',          'WTI Crude',        '${:.1f}',  '🛢️', 1.0),
        ('brent',        'Brent Crude',      '${:.1f}',  '🛢️', 1.0),
        ('mortgage30',   '30Y Mortgage',     '{:.2f}%',  '🏠', 0.05),
        ('gdp_growth_q', 'GDP Growth (Q)',   '{:.1f}%',  '📊', 0.1),
    ]

    headlines = []
    for key, label, fmt, emoji, thresh in ITEMS:
        cur = v.get(key)
        if cur is None:
            continue
        old = prev.get(key)
        cur_str = fmt.format(cur)

        if old is not None and abs(cur - old) >= thresh:
            chg = cur - old
            sign = '+' if chg > 0 else ''
            if '%' in fmt:
                chg_str = f'{sign}{chg:.2f}pp'
            elif 'bp' in fmt:
                chg_str = f'{sign}{chg:.0f}bp'
            else:
                chg_str = f'{sign}{chg:.1f}'
            headlines.append({
                'emoji': emoji, 'label': label,
                'value': cur_str, 'change': chg_str, 'moved': True,
            })
        else:
            # Include key metrics even if unchanged
            if key in ('ffr', 'dgs10', 'unrate', 'cpi_yoy', 'wti'):
                headlines.append({
                    'emoji': emoji, 'label': label,
                    'value': cur_str, 'change': '—', 'moved': False,
                })

    # Sort: movers first, then stable
    headlines.sort(key=lambda x: (0 if x['moved'] else 1, x['label']))
    return headlines


# ── Email body ────────────────────────────────────────────────────────

def build_email(sig, ana, today_str, prev_log):
    v     = sig.get('values', {})
    risk  = sig.get('risk_level', 'MODERATE')
    kpis  = (ana or {}).get('kpi_updates', {})
    tabs  = (ana or {}).get('tabs', {})
    flags = (ana or {}).get('signal_flags', [])

    risk_col = {
        'LOW':      '#0D7A4A',
        'MODERATE': '#B45309',
        'ELEVATED': '#C0392B',
        'HIGH':     '#7F1D1D',
    }.get(risk, '#B45309')

    def fv(k, dec=2, sfx=''):
        val = v.get(k)
        return f'{val:.{dec}f}{sfx}' if val is not None else '—'

    def row(lbl, val, note=''):
        return (
            f'<tr>'
            f'<td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:12px;color:#475569">{lbl}</td>'
            f'<td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:12px;font-weight:700;color:#1E293B">{val}</td>'
            f'<td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:11px;color:#94A3B8">{note}</td>'
            f'</tr>'
        )

    # ── Headlines block ──────────────────────────────────────────────
    headlines = build_headlines(sig, prev_log)
    moved     = [h for h in headlines if h['moved']]
    stable    = [h for h in headlines if not h['moved']]

    def hl_row(h):
        chg_col = '#0D7A4A' if h['change'].startswith('+') else '#C0392B' if h['change'].startswith('-') else '#94A3B8'
        return (
            f'<tr>'
            f'<td style="padding:5px 10px;font-size:13px;width:24px">{h["emoji"]}</td>'
            f'<td style="padding:5px 10px;font-size:12px;color:#334E68;width:140px">{h["label"]}</td>'
            f'<td style="padding:5px 10px;font-size:12px;font-weight:700;color:#1E293B">{h["value"]}</td>'
            f'<td style="padding:5px 10px;font-size:11px;font-weight:700;color:{chg_col}">{h["change"]}</td>'
            f'</tr>'
        )

    movers_html = ''.join(hl_row(h) for h in moved) if moved else (
        '<tr><td colspan="4" style="padding:10px;font-size:12px;color:#94A3B8">'
        'No significant moves vs prior session.</td></tr>'
    )
    stable_html = ''.join(hl_row(h) for h in stable)

    # ── Signal flags ─────────────────────────────────────────────────
    flag_html = ''.join(
        f'<div style="padding:7px 12px;margin-bottom:5px;background:#FEF3C7;'
        f'border-left:3px solid #B45309;border-radius:4px">'
        f'<b style="font-size:11px;color:#92400E">{f["metric"]}: {f["reading"]}</b>'
        f'<p style="margin:2px 0 0;font-size:11px;color:#78350F">{f["note"]}</p></div>'
        for f in flags
    ) or '<p style="font-size:12px;color:#94A3B8;margin:0">No active signal alerts.</p>'

    # ── Tab commentary (monthly AI only — may be empty on daily runs) ─
    tab_html = ''.join(
        f'<div style="margin-bottom:10px">'
        f'<b style="font-size:11px;color:#1E293B;text-transform:uppercase;letter-spacing:.05em">{k}</b>'
        f'<p style="margin:3px 0 0;font-size:12px;color:#475569;line-height:1.6">{txt}</p></div>'
        for k, txt in tabs.items() if txt
    )

    utc = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    run_type = 'Monthly AI Briefing' if tabs else 'Daily Data Update'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F0F4F8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:660px;margin:24px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.10)">

  <!-- Header -->
  <div style="background:#1A56DB;padding:24px 28px">
    <div style="font-size:10px;font-weight:700;letter-spacing:.15em;color:rgba(255,255,255,.55);text-transform:uppercase;margin-bottom:6px">U.S. Macro Dashboard · {run_type}</div>
    <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:6px">📊 {today_str}</div>
    <a href="{DASHBOARD_URL}" style="font-size:11px;color:rgba(255,255,255,.7);text-decoration:none">
      🔗 {DASHBOARD_URL}
    </a>
  </div>

  <!-- Risk banner -->
  <div style="background:{risk_col};padding:10px 28px;display:flex;align-items:center">
    <span style="font-size:13px;font-weight:800;color:#fff;letter-spacing:.08em">⚠️ RISK: {risk}</span>
    <span style="font-size:11px;color:rgba(255,255,255,.85);margin-left:20px">
      Posture: {kpis.get('risk_posture','—')} &nbsp;·&nbsp;
      Regime: {kpis.get('macro_regime','—')} &nbsp;·&nbsp;
      Fed: {kpis.get('fed_bias','—')}
    </span>
  </div>

  <div style="padding:24px 28px">

    <!-- TODAY'S MOVERS -->
    <h2 style="font-size:12px;font-weight:700;color:#1E293B;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;border-bottom:2px solid #1A56DB;padding-bottom:6px">
      📰 Today's Market Moves
    </h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:6px;background:#F8FAFF;border-radius:8px">
      {movers_html}
    </table>

    <!-- STABLE KEY RATES -->
    <details style="margin-bottom:20px">
      <summary style="font-size:11px;color:#94A3B8;cursor:pointer;padding:4px 0">
        Show all key rates ({len(stable)} unchanged)
      </summary>
      <table style="width:100%;border-collapse:collapse;margin-top:6px">
        {stable_html}
      </table>
    </details>

    <!-- FULL SNAPSHOT TABLE -->
    <h2 style="font-size:12px;font-weight:700;color:#1E293B;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #f1f5f9;padding-bottom:6px">
      📋 Full Macro Snapshot
    </h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      {row('Fed Funds Rate',    fv('ffr',2,'%'))}
      {row('10Y Treasury',      fv('dgs10',2,'%'),      f"vs 2Y: {fv('dgs2',2,'%')} · Spread: {fv('spread_10_2_bp',0,'bp')}")}
      {row('IG OAS',            fv('ig_oas',0,'bp'),    'Investment grade spread')}
      {row('HY OAS',            fv('hy_oas',0,'bp'),    'High yield spread')}
      {row('Unemployment U-3',  fv('unrate',1,'%'))}
      {row('CPI YoY',           fv('cpi_yoy',1,'%'))}
      {row('Core PCE YoY',      fv('core_pce_yoy',1,'%'), 'Fed target: 2.0%')}
      {row('WTI Crude',         '$' + fv('wti',1))}
      {row('Brent Crude',       '$' + fv('brent',1))}
      {row('30Y Mortgage',      fv('mortgage30',2,'%'))}
      {row('GDP Growth (QoQ)',  fv('gdp_growth_q',1,'%'))}
    </table>

    <!-- SIGNAL FLAGS -->
    <h2 style="font-size:12px;font-weight:700;color:#1E293B;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #f1f5f9;padding-bottom:6px">
      ⚠️ Signal Flags
    </h2>
    <div style="margin-bottom:20px">{flag_html}</div>

    {"<!-- TAB ANALYSIS (monthly AI run) --><h2 style='font-size:12px;font-weight:700;color:#1E293B;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #f1f5f9;padding-bottom:6px'>🔍 AI Tab Analysis</h2><div style='margin-bottom:20px'>" + tab_html + "</div>" if tab_html else ""}

    <!-- CTA -->
    <div style="text-align:center;padding:16px 0 8px">
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#1A56DB;color:#fff;text-decoration:none;padding:12px 32px;border-radius:24px;font-size:13px;font-weight:700;letter-spacing:.02em">
        → Open Full Dashboard
      </a>
    </div>
    <p style="text-align:center;font-size:11px;color:#94A3B8;margin:8px 0 0">
      Dashboard HTML attached · open locally for full interactive view
    </p>

  </div>

  <!-- Footer -->
  <div style="background:#F8FAFC;padding:10px 28px;border-top:1px solid #f1f5f9">
    <p style="font-size:10px;color:#94A3B8;margin:0">
      5-agent pipeline · claude-sonnet-4-6 · FRED · BLS · EIA · {utc}
    </p>
  </div>

</div></body></html>"""


# ── Resend API send (with HTML attachment) ────────────────────────────

def send_email(html_body, today_str):
    if not RESEND_API_KEY:
        print('  ⚠  RESEND_API_KEY not set — skipping email'); return
    if not EMAIL_TO:
        print('  ⚠  EMAIL_TO not set — skipping email'); return

    # Read dashboard HTML for attachment
    attachment = None
    if HTML_FILE.exists():
        raw_bytes  = HTML_FILE.read_bytes()
        b64_content = base64.b64encode(raw_bytes).decode('utf-8')
        fname = f"macro_dashboard_{datetime.date.today().strftime('%Y%m%d')}.html"
        attachment = [{'filename': fname, 'content': b64_content}]
        print(f'  📎 Attaching {fname} ({len(raw_bytes):,} bytes)')
    else:
        print('  ⚠  Dashboard HTML not found — sending without attachment')

    payload = {
        'from':    EMAIL_FROM,
        'to':      [EMAIL_TO],
        'subject': f'📊 Macro Dashboard — {today_str}',
        'html':    html_body,
    }
    if attachment:
        payload['attachments'] = attachment

    try:
        r = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {RESEND_API_KEY}',
                     'Content-Type': 'application/json'},
            json=payload,
            timeout=30,
        )
        if r.status_code in (200, 201):
            print(f'  ✅ Email sent to {EMAIL_TO} via Resend')
        else:
            print(f'  ⚠  Resend failed: {r.status_code} {r.text[:300]}')
    except Exception as e:
        print(f'  ⚠  Resend error: {e}')


# ══════════════════════════════════════════════════════════════════════

def publish(snapshot_only=False):
    print('[Agent 5 — Publisher] Starting...')
    today_str = datetime.date.today().strftime('%B %d, %Y')

    sig = json.loads(SIG_FILE.read_text())
    ana = json.loads(ANA_FILE.read_text()) if ANA_FILE.exists() else None

    # Load prior snapshot for headline diffing
    prev_log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else {}

    save_log(sig, ana)

    if not snapshot_only:
        html_body = build_email(sig, ana, today_str, prev_log)
        send_email(html_body, today_str)
    else:
        print('  ℹ  Snapshot-only mode — skipping email')

    print(f'[Agent 5] Done — {today_str}')
    return True


if __name__ == '__main__':
    snapshot_only = '--snapshot-only' in sys.argv
    sys.exit(0 if publish(snapshot_only=snapshot_only) else 1)
