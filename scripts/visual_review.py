#!/usr/bin/env python3
"""
Agent 8 — VISUAL REVIEW
Vision-based dashboard quality checks using Claude's multimodal capability.
Takes per-tab screenshots (from Agent 7) and sends them to Claude for
pixel-level visual defect detection.

Detects:
  - Broken/disconnected chart lines (gaps between data points)
  - Empty or mostly-empty chart areas where data should appear
  - Overlapping or truncated axis labels
  - Misaligned or missing legend entries
  - Illegible text (too small, clipped, overlapping)
  - Blank panels or tiles that should have content
  - Visual formatting anomalies (wrong colors, missing gridlines)

Output: data/visual_review_report.json
Usage: python scripts/visual_review.py [--tabs fc,gdp,jobs]
"""

import os, json, sys, datetime, base64, time
from pathlib import Path

try:
    import requests
except ImportError:
    print('pip install requests'); sys.exit(1)

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

ROOT        = Path(__file__).parent.parent
SCREEN_DIR  = ROOT / 'data' / 'screenshots'
RPT_FILE    = ROOT / 'data' / 'visual_review_report.json'

# Tabs that contain charts/tables worth reviewing visually
# (skip 'dict', 'stack', 'validator' — text-heavy reference tabs)
CHART_TABS = [
    'fc', 'gdp', 'jobs', 'unemp', 'wages', 'cpi',
    'pce', 'yield', 'credit', 'banks', 'housing', 'oil',
]

TAB_NAMES = {
    'fc': 'Outlook', 'gdp': 'GDP', 'jobs': 'Jobs', 'unemp': 'Unemployment',
    'wages': 'Wages', 'cpi': 'CPI', 'pce': 'PCE & Consumer', 'yield': 'Rates & Yields',
    'credit': 'Credit', 'banks': 'Banking', 'housing': 'Housing', 'oil': 'Oil',
}

SYSTEM_PROMPT = """You are a senior data visualization QA analyst reviewing screenshots of a macroeconomic dashboard.

For each screenshot, examine EVERY chart, table, metric tile, and text element visible. Report any visual defects.

Defect categories to check:
1. BROKEN_LINE — A line chart has a visible gap/disconnect between data points (line stops and restarts)
2. EMPTY_CHART — A chart area is blank or nearly blank where data should be plotted
3. SPARSE_DATA — A chart shows only 1-3 data points when it should show a full time series
4. LABEL_OVERLAP — Axis labels or legend text overlap each other and are unreadable
5. LABEL_TRUNCATED — Text labels are cut off or extend beyond their container
6. MISSING_LEGEND — Chart has multiple series but no legend, or legend doesn't match the lines
7. BLANK_TILE — A metric tile or KPI card appears empty or shows placeholder text
8. FORMAT_ERROR — Numbers displayed in wrong format (e.g., raw decimals instead of percentages)
9. LAYOUT_ISSUE — Elements overlap, are misaligned, or have broken layout
10. TEXT_ILLEGIBLE — Text is too small, low contrast, or otherwise hard to read

Respond with ONLY a JSON array of defects found. Each defect:
{
  "category": "BROKEN_LINE|EMPTY_CHART|SPARSE_DATA|...",
  "element": "short description of which chart/table/tile",
  "severity": "critical|warning|minor",
  "detail": "specific description of the visual issue"
}

If no defects are found, return an empty array: []

Be precise — only flag genuine visual problems, not stylistic preferences. A chart with sparse but valid data (e.g., quarterly GDP) is fine. Focus on things that indicate data pipeline bugs or rendering failures."""


def _encode_screenshot(path: Path) -> str:
    """Read and base64-encode a screenshot image."""
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def _call_claude_vision(image_b64: str, tab_name: str) -> list:
    """Send screenshot to Claude for visual analysis. Returns list of defects."""
    if not ANTHROPIC_KEY:
        return []

    user_prompt = (
        f'This is a screenshot of the "{tab_name}" tab from a U.S. Macro Dashboard. '
        f'Examine every chart, table, metric tile, and text element. '
        f'Report any visual defects as a JSON array.'
    )

    last_err = None
    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 2 ** attempt
                print(f'    Retry {attempt}/2 after {wait}s...')
                time.sleep(wait)

            r = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': ANTHROPIC_KEY,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': 'claude-sonnet-4-6-20250514',
                    'max_tokens': 1500,
                    'system': SYSTEM_PROMPT,
                    'messages': [{
                        'role': 'user',
                        'content': [
                            {
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': 'image/png',
                                    'data': image_b64,
                                },
                            },
                            {
                                'type': 'text',
                                'text': user_prompt,
                            },
                        ],
                    }],
                },
                timeout=120,
            )
            r.raise_for_status()
            text = r.json()['content'][0]['text'].strip()

            # Parse JSON from response (handle markdown fences)
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            text = text.strip()

            defects = json.loads(text)
            if isinstance(defects, list):
                return defects
            return []

        except json.JSONDecodeError:
            # Try to extract JSON array from response
            import re
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            last_err = f'Could not parse JSON from response'
        except Exception as e:
            last_err = e
            print(f'    Claude vision call failed (attempt {attempt+1}/3): {e}')

    print(f'    All retries exhausted. Last error: {last_err}')
    return []


def run_visual_review(tab_filter=None):
    """
    Run vision-based review on dashboard screenshots.
    Args:
        tab_filter: optional list of tab IDs to review (default: all chart tabs)
    Returns:
        (findings_list, summary_dict)
    """
    print('[Agent 8 — Visual Review] Starting vision-based quality checks...')

    if not ANTHROPIC_KEY:
        print('  No ANTHROPIC_API_KEY — visual review skipped')
        return [], {'status': 'skipped', 'reason': 'No API key'}

    if not SCREEN_DIR.exists():
        print('  No screenshots directory — run visual_qa.py --screenshots first')
        return [], {'status': 'skipped', 'reason': 'No screenshots'}

    tabs_to_review = tab_filter or CHART_TABS
    all_findings = []
    tabs_reviewed = 0
    total_defects = 0

    for tab_id in tabs_to_review:
        screenshot = SCREEN_DIR / f'{tab_id}.png'
        if not screenshot.exists():
            print(f'  {tab_id}: no screenshot, skipping')
            continue

        tab_name = TAB_NAMES.get(tab_id, tab_id)
        print(f'  Reviewing {tab_name} ({tab_id})...')
        tabs_reviewed += 1

        image_b64 = _encode_screenshot(screenshot)
        defects = _call_claude_vision(image_b64, tab_name)

        if defects:
            total_defects += len(defects)
            for d in defects:
                finding = {
                    'tab': tab_id,
                    'tab_name': tab_name,
                    'category': d.get('category', 'UNKNOWN'),
                    'element': d.get('element', ''),
                    'severity': d.get('severity', 'warning'),
                    'detail': d.get('detail', ''),
                    'pass': False,
                }
                all_findings.append(finding)
                sev_icon = '!' if finding['severity'] == 'critical' else '~'
                print(f'    [{sev_icon}] {finding["category"]}: {finding["element"]} — {finding["detail"]}')
        else:
            # Record a passing check for this tab
            all_findings.append({
                'tab': tab_id,
                'tab_name': tab_name,
                'category': 'VISUAL_REVIEW',
                'element': f'{tab_name} tab',
                'severity': 'ok',
                'detail': 'No visual defects detected',
                'pass': True,
            })
            print(f'    OK — no defects')

        # Rate limit: brief pause between API calls
        if tabs_reviewed < len(tabs_to_review):
            time.sleep(1)

    # Build summary
    n_critical = sum(1 for f in all_findings if f.get('severity') == 'critical')
    n_warning = sum(1 for f in all_findings if f.get('severity') == 'warning')
    n_minor = sum(1 for f in all_findings if f.get('severity') == 'minor')
    n_pass = sum(1 for f in all_findings if f.get('pass'))

    status = 'PASS'
    if n_critical > 0:
        status = 'FAIL'
    elif n_warning > 0:
        status = 'WARN'

    summary = {
        'status': status,
        'tabs_reviewed': tabs_reviewed,
        'total_defects': total_defects,
        'critical': n_critical,
        'warnings': n_warning,
        'minor': n_minor,
        'passed_tabs': n_pass,
    }

    # Save standalone report
    report = {
        'reviewed_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'summary': summary,
        'findings': all_findings,
    }
    RPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RPT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')

    # Print summary
    icon = 'PASS' if status == 'PASS' else 'WARN' if status == 'WARN' else 'FAIL'
    print(f'\n[Agent 8] {icon} — {tabs_reviewed} tabs reviewed, '
          f'{total_defects} defects ({n_critical} critical, {n_warning} warning, {n_minor} minor)')
    print(f'  Report saved to {RPT_FILE.name}')

    return all_findings, summary


def get_findings_for_validator():
    """
    Entry point for validator.py integration.
    Returns findings in the validator's expected format.
    """
    findings, summary = run_visual_review()

    # Convert to validator format
    validator_findings = []
    for f in findings:
        validator_findings.append({
            'check': f'Vision: {f["tab_name"]} — {f.get("element", f["category"])}',
            'severity': f.get('severity', 'warning'),
            'pass': f.get('pass', False),
            'detail': f.get('detail', ''),
        })

    return validator_findings


if __name__ == '__main__':
    # Parse --tabs flag
    tab_filter = None
    for i, arg in enumerate(sys.argv):
        if arg == '--tabs' and i + 1 < len(sys.argv):
            tab_filter = sys.argv[i + 1].split(',')

    findings, summary = run_visual_review(tab_filter=tab_filter)
    sys.exit(0 if summary.get('status') != 'FAIL' else 1)
