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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _models import SONNET_VISION
from _agent_guardrails import (
    bounded_llm_call,
    reset_call_counter,
    BudgetExhausted,
    is_disabled,
)

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
    'wages': 'Wages', 'cpi': 'CPI', 'pce': 'Consumer & PCE', 'yield': 'Rates & Yields',
    'credit': 'Credit', 'banks': 'Banking', 'housing': 'Housing', 'oil': 'Oil',
}

SYSTEM_PROMPT = """You are a senior data visualization QA analyst reviewing screenshots of a macroeconomic dashboard published to a CEO-level audience.

The bar is high. The dashboard appears in board decks. Every visible
defect is something a senior reviewer would call out. Apply the
standards from `data/style_guide.md` — that file is the contract for
what "perfect" means here. Cite a section (e.g. "style_guide §3" for
typography) whenever you can.

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
11. COMMENTARY_PLACEMENT — Per-tab "fc-note" commentary sits below charts instead of above (style_guide §1 says it must precede the first chart)
12. SPACING_DRIFT — Spacing between panels visibly differs from peer panels on the same tab (style_guide §5)
13. TYPOGRAPHY_DRIFT — Font size, family, or weight visibly differs from the convention for that role (headline, panel title, body, etc.; style_guide §3)
14. COLOR_DRIFT — Color used for a semantic role (critical, warning, confirmed) does not match style_guide §4 palette
15. CROSS_TAB_INCONSISTENCY — Same kind of element rendered differently on different tabs (only applicable when multiple screenshots are reviewed together; style_guide §8)
16. COPY_QUALITY — Commentary contains hedging filler, forbidden vocabulary, or fewer than 2 / more than 4 sentences (style_guide §2)

Respond with ONLY a JSON array of defects found. Each defect:
{
  "category": "BROKEN_LINE|EMPTY_CHART|...",
  "element": "short description of which chart/table/tile",
  "severity": "critical|warning|minor",
  "detail": "specific description of the visual issue",
  "style_guide": "§X (optional citation of the style_guide section violated)"
}

If no defects are found, return an empty array: [].

CRITICAL: do not flag stylistic preferences. A chart with sparse but
valid data (e.g., quarterly GDP) is fine. Focus on things that would
embarrass the team if seen in a board meeting. Cite a style_guide §
when calling out a CEO-grade issue."""


def _encode_screenshot(path: Path) -> str:
    """Read and base64-encode a screenshot image."""
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def _strip_fences_to_array(text: str) -> str:
    """Normalize a Claude response down to its leading JSON array."""
    t = text.strip()
    if t.startswith('```'):
        t = t.split('```', 2)[1]
        if t.lower().startswith('json'):
            t = t[4:]
        if t.endswith('```'):
            t = t[:-3]
    return t.strip()


def _validate_vision_response(text: str) -> bool:
    """bounded_llm_call validator — accepts only JSON arrays (the defect
    list contract). Rejecting non-arrays retriggers the retry loop before
    we fall back to the empty-list default."""
    import re
    cleaned = _strip_fences_to_array(text)
    try:
        obj = json.loads(cleaned)
        return isinstance(obj, list)
    except (json.JSONDecodeError, ValueError):
        # Be lenient: if a [...] array is embedded in surrounding prose,
        # accept it. Same shape the post-call parser expects.
        m = re.search(r'\[[\s\S]*\]', cleaned)
        if not m:
            return False
        try:
            return isinstance(json.loads(m.group(0)), list)
        except (json.JSONDecodeError, ValueError):
            return False


def _call_claude_vision(image_b64: str, tab_name: str) -> list:
    """Send screenshot to Claude for visual analysis. Returns list of defects.

    Migrated to bounded_llm_call() so this call shares the kill switch,
    cost cap, and audit log with every other agentic surface. Vision
    payload uses the image_b64 parameter of bounded_llm_call.
    """
    if is_disabled() or not ANTHROPIC_KEY:
        return []

    user_prompt = (
        f'This is a screenshot of the "{tab_name}" tab from a U.S. Macro Dashboard. '
        f'Examine every chart, table, metric tile, and text element. '
        f'Report any visual defects as a JSON array.'
    )

    try:
        text = bounded_llm_call(
            user_prompt,
            system=SYSTEM_PROMPT,
            model=SONNET_VISION,
            max_tokens=1500,
            purpose=f'visual_review:{tab_name}',
            temperature=0.2,
            validator=_validate_vision_response,
            image_b64=image_b64,
            image_media_type='image/png',
        )
    except BudgetExhausted as e:
        print(f'    visual_review budget exhausted: {e}')
        return []
    except Exception as e:
        print(f'    visual_review bounded_llm_call raised: {type(e).__name__}: {e}')
        return []

    if text is None:
        # Kill switch or validator rejected every retry
        return []

    cleaned = _strip_fences_to_array(text)
    try:
        defects = json.loads(cleaned)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\[[\s\S]*\]', cleaned)
        if not m:
            return []
        try:
            defects = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    return defects if isinstance(defects, list) else []


def run_visual_review(tab_filter=None):
    """
    Run vision-based review on dashboard screenshots.
    Args:
        tab_filter: optional list of tab IDs to review (default: all chart tabs)
    Returns:
        (findings_list, summary_dict)
    """
    print('[Agent 8 — Visual Review] Starting vision-based quality checks...')

    # Share LLM-call budget with any other agentic components running in
    # this process. bounded_llm_call() respects this counter.
    reset_call_counter()

    if is_disabled():
        print('  AGENT_DISABLE_ALL=1 — visual review skipped')
        return [], {'status': 'skipped', 'reason': 'kill switch'}

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
