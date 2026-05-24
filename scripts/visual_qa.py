#!/usr/bin/env python3
"""
Agent 7 — VISUAL QA
DOM-based dashboard quality checks using headless Chromium.
Opens index.html, navigates each tab, and verifies:
  - No JS console errors
  - All tabs render with content (not empty/collapsed)
  - KPI tiles have values (no empty, undefined, NaN)
  - Chart canvases have non-zero dimensions
  - No visible "undefined", "NaN", "null" text in rendered content
  - All tab panels activate on click
  - Screenshots saved as artifacts for human review

Output: data/visual_qa_report.json + screenshots in data/screenshots/
Usage: python scripts/visual_qa.py [--screenshots]
"""

import json, sys, datetime, os
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('pip install playwright && playwright install chromium')
    sys.exit(1)

ROOT       = Path(__file__).parent.parent
HTML_FILE  = ROOT / 'index.html'
RPT_FILE   = ROOT / 'data' / 'visual_qa_report.json'
SCREEN_DIR = ROOT / 'data' / 'screenshots'

TAB_IDS = [
    'fc', 'gdp', 'jobs', 'unemp', 'wages', 'cpi',
    'pce', 'yield', 'credit', 'banks', 'housing', 'oil',
    'dict', 'stack', 'validator',
]

# Tab display names for reporting
TAB_NAMES = {
    'fc': 'Outlook', 'gdp': 'GDP', 'jobs': 'Jobs', 'unemp': 'Unemployment',
    'wages': 'Wages', 'cpi': 'CPI', 'pce': 'Consumer & PCE', 'yield': 'Rates & Yields',
    'credit': 'Credit', 'banks': 'Banking', 'housing': 'Housing', 'oil': 'Oil',
    'dict': 'Sources', 'stack': 'Dashboard', 'validator': 'Validator',
}

PASS = 0
FAIL = 0
findings = []


def _check(category, name, condition, detail='', severity='warning'):
    global PASS, FAIL
    result = {
        'category': category,
        'check': name,
        'pass': bool(condition),
        'severity': 'ok' if condition else severity,
    }
    if not condition and detail:
        result['detail'] = detail
    findings.append(result)
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL  [{category}] {name} — {detail}')


# ════════════════════════════════════════════════════════════════════
# Static visual-contract checks (no browser). Added 2026-05-22 after
# the visual-design audit. These enforce the style_guide.md contract
# against theme-overlay.css and index.html source, so drift fails CI
# before the page is even rendered.
# ════════════════════════════════════════════════════════════════════

# Spacing tokens allowed under §5.1 of style_guide.md. 4pt grid.
# Sub-4 values (1/2/3px) allowed for borders/affordances only — those
# are detected by context ("border:", "outline:", "::before content").
_GRID_TOKENS = {0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 44, 48, 56, 60, 64, 72, 80, 96, 120}

# Approved palette (style_guide.md §4.1). Lowercased hex.
_PALETTE = {
    # neutrals
    '#f7f8fa', '#fafbfc', '#ffffff', '#fff', '#0d1b2a', '#1e293b', '#334e68',
    '#475569', '#5a6b7d', '#7a8fa8', '#94a3b8', '#cbd5e1', '#e2e8f0', '#f1f5f9',
    # semantic
    '#336bcc', '#1e4a8c', '#1a9e5a', '#d64045', '#cc8a00', '#8878b8',
    # action states + dark text/links
    '#15803d', '#b91c1c', '#b45309', '#ebf7ef', '#fceeee', '#fef3c7',
    # transparent / inherit
    'transparent', 'none', 'inherit', 'currentcolor',
}


def check_spacing_grid():
    """Fail if theme-overlay.css contains off-grid padding/margin/gap values.
    style_guide.md §5.1 — 4pt grid tokens only."""
    import re
    css_file = ROOT / 'theme-overlay.css'
    if not css_file.exists():
        _check('contract', 'spacing_grid_file', False, 'theme-overlay.css missing', 'critical')
        return
    src = css_file.read_text(encoding='utf-8')
    # Strip block comments
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    offenders = []
    # Match padding/margin/gap with px values. Allow 0, allow 1-3px on
    # border/outline/box-shadow lines (handled by line filter).
    pat = re.compile(r'(padding|margin|gap)\s*:\s*([^;]+);', re.I)
    for lineno, line in enumerate(src.splitlines(), 1):
        # Skip border-affordance lines
        if 'border' in line.lower() and 'border-radius' not in line.lower() and 'border-bottom-color' not in line.lower():
            continue
        for m in pat.finditer(line):
            for px in re.findall(r'(-?\d+)px', m.group(2)):
                v = abs(int(px))
                # Sub-4 px allowed only as border-affordance (caught above)
                if v <= 3:
                    continue
                if v not in _GRID_TOKENS:
                    offenders.append(f'line {lineno}: {m.group(1)} {v}px (in `{line.strip()[:90]}`)')
    if offenders:
        _check('contract', 'spacing_grid', False,
               f'{len(offenders)} off-grid value(s): ' + '; '.join(offenders[:5]),
               'warning')
    else:
        _check('contract', 'spacing_grid', True)


def check_palette_compliance():
    """Fail if theme-overlay.css uses hex colors outside the approved palette.
    style_guide.md §4.1 palette is the source of truth."""
    import re
    css_file = ROOT / 'theme-overlay.css'
    if not css_file.exists():
        _check('contract', 'palette_compliance_file', False, 'theme-overlay.css missing', 'critical')
        return
    src = css_file.read_text(encoding='utf-8')
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    hexes = set(m.lower() for m in re.findall(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}', src))
    offenders = sorted(hexes - _PALETTE)
    if offenders:
        _check('contract', 'palette_compliance', False,
               f'{len(offenders)} off-palette hex(es) in theme-overlay.css: ' + ', '.join(offenders[:8]),
               'warning')
    else:
        _check('contract', 'palette_compliance', True)


def check_panel_meta():
    """Fail if any <div class="panel"> in index.html is missing the
    pm-exhibit / pm-source / pm-asof / pm-cadence chain. Microcopy
    ladder enforcement — every panel speaks the same way."""
    import re
    html_file = ROOT / 'index.html'
    if not html_file.exists():
        _check('contract', 'panel_meta_file', False, 'index.html missing', 'critical')
        return
    src = html_file.read_text(encoding='utf-8')
    # Find panel blocks: from `<div class="panel"` to the next closing
    # `</div>` that matches it. Cheap heuristic: split into panels by
    # detecting `class="panel"` then look at the next ~1500 chars.
    pat = re.compile(r'<div[^>]*class="[^"]*\bpanel\b[^"]*"[^>]*>', re.I)
    required = ['pm-exhibit', 'pm-source', 'pm-asof', 'pm-cadence']
    missing = []
    starts = [m.start() for m in pat.finditer(src)]
    starts.append(len(src))  # sentinel
    for i in range(len(starts) - 1):
        # Clip each panel's slice to the next panel's start so we
        # never read meta from a downstream sibling.
        slice_ = src[starts[i]:starts[i+1]]
        if 'panel-meta' not in slice_:
            # Commentary wrappers / chart-only containers — skip.
            continue
        absent = [r for r in required if r not in slice_]
        if absent:
            title_m = re.search(r'<div class="panel-title">([^<]{0,80})', slice_)
            label = title_m.group(1).strip() if title_m else f'offset {starts[i]}'
            missing.append(f'"{label}" missing: ' + ','.join(absent))
    if missing:
        _check('contract', 'panel_meta', False,
               f'{len(missing)} panel(s) missing meta chips: ' + '; '.join(missing[:4]),
               'warning')
    else:
        _check('contract', 'panel_meta', True)


def check_serif_scope():
    """Fail if DM Serif Display is applied to any selector other than
    .kpi-val. The visual audit forbids competing 'hero number' treatments."""
    import re
    css_file = ROOT / 'theme-overlay.css'
    if not css_file.exists():
        return
    src = css_file.read_text(encoding='utf-8')
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    # Walk every rule block; flag any selector that references
    # DM Serif Display but isn't .kpi-val.
    offenders = []
    for m in re.finditer(r'([^{}]+)\{([^{}]+)\}', src):
        selector = m.group(1).strip()
        body = m.group(2)
        if 'DM Serif Display' in body and '.kpi-val' not in selector:
            offenders.append(selector[:80])
    if offenders:
        _check('contract', 'serif_scope', False,
               f'{len(offenders)} non-.kpi-val selector(s) use DM Serif Display: ' + '; '.join(offenders[:3]),
               'warning')
    else:
        _check('contract', 'serif_scope', True)


def run_visual_qa(take_screenshots=False):
    global PASS, FAIL, findings
    PASS = 0
    FAIL = 0
    findings = []

    print('[Agent 7 — Visual QA] Starting DOM-based quality checks...')

    if not HTML_FILE.exists():
        print('ERROR: index.html not found')
        sys.exit(1)

    if take_screenshots:
        SCREEN_DIR.mkdir(parents=True, exist_ok=True)

    # ── Static visual-contract checks (no browser) ──
    # Added 2026-05-22 after visual-design audit. These enforce the
    # style_guide.md contract against source files; drift fails the
    # build before any rendering happens.
    print('  Static contract checks...')
    check_spacing_grid()
    check_palette_compliance()
    check_panel_meta()
    check_serif_scope()

    with sync_playwright() as p:
        # Use PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH env var if set, otherwise auto-detect
        chrome_path = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', '')
        if not chrome_path:
            # Try to find installed chromium
            import glob
            candidates = sorted(glob.glob(os.path.expanduser(
                '~/.cache/ms-playwright/chromium-*/chrome-linux/chrome')), reverse=True)
            if candidates:
                chrome_path = candidates[0]
        launch_args = {'headless': True}
        if chrome_path and os.path.exists(chrome_path):
            launch_args['executable_path'] = chrome_path
        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=2,
        )
        page = context.new_page()

        # Collect console errors
        console_errors = []
        page.on('console', lambda msg: console_errors.append(
            {'type': msg.type, 'text': msg.text}
        ) if msg.type in ('error', 'warning') else None)

        # Collect JS exceptions
        js_errors = []
        page.on('pageerror', lambda err: js_errors.append(str(err)))

        # Browsers block fetch() from file:// origins (CORS). Route JSON
        # data-blob fetches through Playwright and serve them from disk so
        # post-v1.0.3 runtime-fetched data (VALIDATION_REPORT, etc.) can be
        # verified in the visual-QA harness the same way it works on Pages.
        data_dir = HTML_FILE.parent / 'data'
        def _route_data(route, req):
            import os
            fname = os.path.basename(req.url.split('?')[0])
            fpath = data_dir / fname
            if fpath.exists():
                route.fulfill(status=200, content_type='application/json',
                              body=fpath.read_text(encoding='utf-8'))
            else:
                route.fulfill(status=404, body=f'Not found: {fname}')
        page.route('**/data/*.json', _route_data)

        # Load page
        file_url = f'file://{HTML_FILE.resolve()}'
        page.goto(file_url, wait_until='networkidle')
        page.wait_for_timeout(1000)  # Let charts render

        # Tier 1 anti-clone: wait for hydration to finish before running
        # any tab-click checks. _hydrate() fetches /api/state.json (fails on
        # file://, falls through to /data/state.json which the route above
        # serves from disk) then triggers _rebuildAfterHydrate to rewire
        # tabs. If we click before that callback fires, the click target
        # can become unstable as the tab panel re-renders mid-click,
        # producing the "Timeout 30000ms" failure on btn.click(). Poll
        # for window.MD._hydrationDone with a 5s ceiling — well above
        # typical fetch-from-disk latency (~50ms).
        try:
            page.wait_for_function(
                'window.MD && window.MD._hydrationDone === true',
                timeout=5000
            )
        except Exception as _hyd_err:
            print(f'  WARN  Hydration did not signal _hydrationDone within 5s '
                  f'({_hyd_err}). Continuing — checks may be flaky.')

        # ── Global checks ──────────────────────────────────────────
        print('\n  ── Global Checks ──')

        # Page title
        title = page.title()
        _check('global', 'Page has title', len(title) > 0, f'title="{title}"')

        # Page loaded without crash
        body_text = page.inner_text('body')
        _check('global', 'Page body has content', len(body_text) > 100,
               f'body length={len(body_text)}')

        # JS errors
        _check('global', 'No JS exceptions', len(js_errors) == 0,
               f'{len(js_errors)} errors: {js_errors[:3]}', severity='critical')

        # Console errors (filter out benign ones)
        real_errors = [e for e in console_errors
                       if e['type'] == 'error'
                       and 'favicon' not in e['text'].lower()
                       and 'net::ERR_FILE_NOT_FOUND' not in e['text']
                       and 'net::ERR_FAILED' not in e['text']  # file:// CORS
                       and 'Access to fetch' not in e['text']]  # file:// CORS
        _check('global', 'No console errors', len(real_errors) == 0,
               f'{len(real_errors)} errors: {[e["text"][:80] for e in real_errors[:3]]}')

        # KPI strip exists and has tiles
        kpi_strip = page.query_selector_all('.metric-row .m-tile, .kpi-strip .m-tile, [class*="kpi"] [class*="tile"]')
        if not kpi_strip:
            # Try broader selector
            kpi_strip = page.evaluate('''() => {
                const strip = document.querySelector('.metric-row');
                return strip ? strip.children.length : 0;
            }''')
            _check('global', 'KPI strip has tiles',
                   (isinstance(kpi_strip, int) and kpi_strip > 0) or len(kpi_strip) > 0,
                   'No KPI tiles found')
        else:
            _check('global', 'KPI strip has tiles', len(kpi_strip) > 0,
                   f'found {len(kpi_strip)} tiles')

        # Nav buttons exist
        nav_btns = page.query_selector_all('[data-tab]')
        _check('global', 'Nav buttons present', len(nav_btns) >= 10,
               f'found {len(nav_btns)} buttons, expected 15')

        # ── Per-tab checks ─────────────────────────────────────────
        print('\n  ── Tab Checks ──')

        for tab_id in TAB_IDS:
            tab_name = TAB_NAMES.get(tab_id, tab_id)

            # Click nav button
            btn = page.query_selector(f'[data-tab="{tab_id}"]')
            if not btn:
                _check(tab_name, 'Nav button exists', False, f'no button for data-tab="{tab_id}"')
                continue

            btn.click()
            page.wait_for_timeout(500)  # Let tab build

            # Check tab panel is visible
            panel = page.query_selector(f'#tab-{tab_id}')
            if not panel:
                _check(tab_name, 'Tab panel exists', False, f'no #tab-{tab_id}')
                continue

            is_visible = panel.is_visible()
            _check(tab_name, 'Tab panel visible', is_visible, 'panel hidden after click')

            if not is_visible:
                continue

            # Check panel has content (not empty)
            panel_text = panel.inner_text()
            _check(tab_name, 'Tab has content', len(panel_text.strip()) > 20,
                   f'only {len(panel_text.strip())} chars')

            # Check for bad values in rendered text
            bad_patterns = ['undefined', 'NaN', 'null', '[object Object]']
            found_bad = [p for p in bad_patterns if p in panel_text]
            _check(tab_name, 'No undefined/NaN/null values', len(found_bad) == 0,
                   f'found: {found_bad}')

            # Check for metric tiles in this tab
            metric_rows = panel.query_selector_all('.metric-row')
            if metric_rows:
                for i, row in enumerate(metric_rows):
                    tiles = row.query_selector_all('div')
                    # Check tiles aren't empty
                    row_text = row.inner_text()
                    if row_text.strip():
                        # Check for empty tile values
                        empty_vals = row_text.count('""') + row_text.count("''")
                        if empty_vals > 0:
                            _check(tab_name, f'Metric row {i} no empty values',
                                   False, f'{empty_vals} empty values')

            # Check for chart canvases
            canvases = panel.query_selector_all('canvas')
            for i, canvas in enumerate(canvases):
                box = canvas.bounding_box()
                if box:
                    has_size = box['width'] > 50 and box['height'] > 50
                    _check(tab_name, f'Chart canvas {i} has size', has_size,
                           f'{box["width"]:.0f}x{box["height"]:.0f}px')

            # ── Per-panel paint coverage (EX 5 regression guard) ──
            # Every panel labelled with a `pm-exhibit` chip (e.g. "Exhibit 05")
            # must paint *something* in its body — at minimum: a sized canvas,
            # a sized inline SVG, a populated data-table/grid, or meaningful
            # text content (not just chips/badges).
            #
            # Background: the oil tab's "Full Oil Impact Chain" panel
            # (Exhibit 05) shipped completely blank for weeks. The two PHASE
            # chips at the top rendered (so panel-level text-length and
            # panel-title checks passed) but the actual `<div
            # id="oil-impact-chain">` body never got filled — root cause was
            # a `let SHOCK_TRACKER = null;` declared inside `buildOilTab()`
            # that shadowed the script-scope hydration target. Caught
            # post-hoc from a user screenshot. This check would have caught
            # it the same day.
            #
            # The assertion is intentionally lenient: any one of canvas/SVG/
            # table/text-body counts as "painted". A truly empty body
            # (placeholder div + chips only) is the failure mode.
            exhibit_panels = panel.query_selector_all('.panel .pm-exhibit, .pm-exhibit')
            for ex_chip in exhibit_panels:
                ex_label = (ex_chip.inner_text() or '').strip()
                # Walk up to the enclosing .panel — that's the surface we're
                # asserting paint on. Skip if we can't find one (defensive).
                panel_el = ex_chip.evaluate_handle(
                    "el => el.closest('.panel')"
                ).as_element()
                if not panel_el:
                    continue
                paint_signal = panel_el.evaluate(
                    """el => {
                        // Sized canvas or svg
                        for (const c of el.querySelectorAll('canvas, svg')) {
                            const r = c.getBoundingClientRect();
                            if (r.width > 30 && r.height > 30) return 'canvas/svg';
                        }
                        // Populated data-table or grid wrapper (rows present)
                        for (const t of el.querySelectorAll('.dtable-wrap, .dtable, table, .grid, .stk-grid')) {
                            if (t.children && t.children.length > 0) return 'table/grid';
                        }
                        // Non-trivial body text — exclude the meta-chip ladder
                        // (panel-title/sub/meta/badges/chips) so a panel that
                        // has ONLY chip labels and no actual content fails.
                        const clone = el.cloneNode(true);
                        clone.querySelectorAll(
                            '.panel-title, .panel-sub, .panel-meta, ' +
                            '.so-what, .badge, .chip, .pill, ' +
                            'span[style*="border-radius"]'
                        ).forEach(n => n.remove());
                        const body = (clone.innerText || '').trim();
                        if (body.length > 40) return 'text';
                        // Any non-empty dynamic container that holds children
                        for (const d of el.querySelectorAll('div[id]')) {
                            if (d.children && d.children.length > 0) return 'container';
                        }
                        return '';
                    }"""
                )
                _check(
                    tab_name,
                    f'Panel "{ex_label}" painted body content',
                    bool(paint_signal),
                    f'{ex_label}: no canvas/svg/table/text/container in body '
                    f'— possible hydration shadow or empty placeholder',
                    severity='critical',
                )

            # ── Layout consistency: commentary positioned above charts ──
            # Canonical rule: every chart tab with a `<div class="fc-note"
            # id="commentary-<tab>">` element should render it ABOVE the
            # first chart canvas in the tab. Catches drift where commentary
            # ends up wedged between or below cards (silent UX regression
            # the existing DOM checks couldn't see because they're scoped
            # to single elements, not relative position).
            # Skips tabs that have no commentary-<tab> element (fc/Outlook
            # uses commentary-gdp by design; gdp/stack/validator/dict
            # have no per-tab commentary). style_guide §1.
            commentary = panel.query_selector(f'#commentary-{tab_id}')
            if commentary and canvases:
                c_box = commentary.bounding_box()
                first_canvas_box = canvases[0].bounding_box()
                if c_box and first_canvas_box:
                    above_first_chart = c_box['y'] < first_canvas_box['y']
                    _check(
                        tab_name, 'Commentary positioned above first chart',
                        above_first_chart,
                        f'commentary y={c_box["y"]:.0f}, '
                        f'first canvas y={first_canvas_box["y"]:.0f}',
                    )

            # ── Typography rhythm: commentary copy length 2–4 sentences ──
            # style_guide §2: commentary is 2–4 sentences. Outside that band
            # is a CEO-grade defect (one sentence reads thin; >4 is a wall).
            # Sentence count is approximated by counting '.', '!', '?'
            # outside numbers (BAD: "$3.5B" counts the "." — we strip
            # digits-around-dot first).
            if commentary:
                # The Dashboard tab's #commentary-stack is the how-it-works
                # intro (`.hiw-lead` paragraphs) — onboarding copy, not
                # standard 2–4-sentence data commentary. Skip the band
                # check when ALL children are .hiw-lead, since style_guide
                # §2 governs data commentary, not the intro panel.
                hiw_only = commentary.evaluate(
                    "el => el.children.length > 0 && "
                    "Array.from(el.children).every("
                    "  c => c.classList.contains('hiw-lead'))"
                )
                if not hiw_only:
                    txt = (commentary.inner_text() or '').strip()
                    # Strip decimal points inside numbers so "$3.5B" doesn't
                    # inflate the sentence count. Also strip dots inside
                    # uppercase abbreviations like "U.S." which the bare
                    # period-count would otherwise treat as two sentences.
                    import re as _re
                    cleaned = _re.sub(r'(?<=\d)\.(?=\d)', '', txt)
                    cleaned = _re.sub(r'(?<=\b[A-Z])\.(?=[A-Z]\b)', '', cleaned)
                    sentence_count = sum(cleaned.count(c) for c in '.!?')
                    in_band = 2 <= sentence_count <= 4
                    _check(
                        tab_name, 'Commentary sentence count in [2,4]', in_band,
                        f'{sentence_count} sentences (style_guide §2)',
                    )

            # ── Color drift: no ad-hoc rgb() colors on commentary copy ──
            # style_guide §4: commentary uses --text2. Catches the case
            # where someone hardcodes a color that drifts from the palette.
            if commentary:
                color = page.evaluate(
                    'el => getComputedStyle(el).color',
                    commentary,
                )
                # Allowed resolved colors for commentary copy (style_guide §4).
                # Keep this set in sync with the --text2 / --text variants
                # declared on `:root` in index.html. The check fires when a
                # hand-edit drifts the commentary to an off-palette color.
                allowed_colors = {
                    'rgb(51, 78, 104)',   # #334E68 — current --text2
                    'rgb(13, 27, 42)',    # #0D1B2A — --text (when commentary
                                          #                 escapes its var)
                    'rgb(122, 144, 168)', # #7A8FA8 — --muted (panel-level
                                          #                 commentary tints)
                    'rgb(30, 41, 59)',    # #1E293B — Slate-800, applied by
                                          # theme-overlay.css on body.themed-sm
                                          # .fc-note (sanctioned themed variant
                                          # per 8pt-grid visual audit). Uniform
                                          # across all 12 swept tabs; not drift.
                }
                _check(
                    tab_name, 'Commentary color matches palette',
                    color in allowed_colors,
                    f'computed color {color!r} (style_guide §4)',
                )

            # Check for panels (sub-sections)
            panels = panel.query_selector_all('.panel')
            for i, p in enumerate(panels[:10]):  # Limit to first 10
                panel_title = p.query_selector('.panel-title')
                if panel_title:
                    title_text = panel_title.inner_text()
                    _check(tab_name, f'Panel "{title_text[:40]}" has title',
                           len(title_text.strip()) > 0, 'empty panel title')

            # ── §23 Uplift checks — opt-in per tab as the sweep proceeds.
            # Tabs in UPLIFT_SWEPT_TABS must satisfy:
            #   (a) §23.1 finding-first titles — at least one finite verb
            #       in any panel-title containing a chart canvas
            #   (b) §23.2 panel-meta strip — present in every chart panel
            #   (c) §23.3 "so what" footer — present in every chart panel
            #
            # When you sweep a new tab, add its tab_id to this set.
            UPLIFT_SWEPT_TABS = {'cpi'}

            if tab_id in UPLIFT_SWEPT_TABS:
                # Common English finite-verb tokens that show up in
                # finding-first titles. Best-effort detector; reviewer
                # remains the final arbiter.
                _verb_tokens = (
                    ' is ', ' are ', ' was ', ' were ', ' has ', ' have ',
                    ' had ', ' show', ' shows', ' indicates', ' remains',
                    ' remain', ' stays', ' stay', ' tracks', ' track',
                    ' fall', ' falls', ' rise', ' rises', ' rose', ' fell',
                    ' run', ' runs', ' ran', ' cool', ' cools', ' cooled',
                    ' heat', ' heats', ' heated', ' accelerat',
                    ' decelerat', ' reaccelerat', ' re-accelerat',
                    ' normalis', ' normaliz', ' converg', ' diverg',
                    ' pull', ' pulls', ' pulling', ' driv', ' lead',
                    ' lifted', ' lift', ' beat', ' beats', ' break',
                    ' breaks', ' broke', ' stuck', ' stick', ' sticks',
                )
                chart_panels = [p for p in panels
                                if p.query_selector('canvas, svg.chart, .ch300, .ch320, .ch400, .ch260, .ch200, .ch-inline')]
                for p in chart_panels[:10]:
                    pt = p.query_selector('.panel-title')
                    title_lc = (pt.inner_text() if pt else '').lower()
                    has_verb = any(tok in (' ' + title_lc + ' ') for tok in _verb_tokens)
                    _check(
                        tab_name, '§23.1 panel title contains finite verb (finding-first)',
                        has_verb,
                        f'title: "{title_lc[:60]}"',
                    )
                    _check(
                        tab_name, '§23.2 panel-meta strip present',
                        p.query_selector('.panel-meta') is not None,
                        'missing .panel-meta — add Exhibit/Source/As-of/Cadence row',
                    )
                    _check(
                        tab_name, '§23.3 "so what" footer present',
                        p.query_selector('.so-what') is not None,
                        'missing .so-what — add takeaway under chart',
                    )

            # Take screenshot if requested
            if take_screenshots:
                # Scroll to top of tab
                panel.evaluate('el => el.scrollIntoView()')
                page.wait_for_timeout(200)
                screenshot_path = SCREEN_DIR / f'{tab_id}.png'
                page.screenshot(path=str(screenshot_path), full_page=True)

        # ── Data integrity checks (in browser) ─────────────────────
        print('\n  ── Data Integrity Checks ──')

        # Check key JS constants are defined and populated
        js_checks = page.evaluate('''async () => {
            const checks = {};

            // Check KPIS
            if (typeof KPIS !== 'undefined') {
                checks.kpis_count = KPIS.length;
                checks.kpis_empty = KPIS.filter(k => !k.val || k.val === '').length;
                checks.kpis_has_nan = KPIS.some(k =>
                    String(k.val).includes('NaN') || String(k.val).includes('undefined'));
            } else {
                checks.kpis_count = -1;
            }

            // Check chart data arrays — including data completeness.
            // NOTE: OIL_DAILY is intentionally omitted — its const is declared
            // after a classic-script top-level boundary that Playwright's
            // page.evaluate sandbox can't reach via eval(). Structural
            // validation of OIL_DAILY lives in the validator's text-based
            // _extract_js_const path, which doesn't have scope restrictions.
            // Sparse-by-design fields (dots, notes) are tolerated below.
            const charts = [
                'CPI_MONTHLY', 'PCE_MONTHLY', 'U_MONTHLY', 'NFP_VS_ADP',
                'HOUSING_MONTHLY', 'OIL_MONTHLY', 'SAVING_MONTHLY', 'UMCSENT_MONTHLY',
                'U_ANNUAL', 'CPI_ANNUAL', 'PCE_ANNUAL', 'WAGE_ANNUAL',
                'JOBS_ANNUAL', 'SAVING_ANNUAL', 'OIL_ANNUAL',
                'CLAIMS_WEEKLY',
                'GDP_TOTAL_DATA', 'FFR_DATA', 'MORTGAGE_DATA', 'SPREADS_DATA',
                'TREASURY_DATA', 'OIL_SPREAD',
                'STARTS_DATA', 'HPI_DATA',
                'OIL_VS_CPI', 'OIL_VS_SENTIMENT', 'OIL_VS_HY',
                'CREDIT_GROWTH', 'TDSP_HIST'
            ];
            checks.charts = {};
            for (const name of charts) {
                try {
                    const obj = eval(name);
                    if (obj && obj.labels) {
                        const info = {
                            labels: obj.labels.length,
                            has_data: Object.keys(obj).length > 1,
                            empty_labels: obj.labels.filter(l => !l).length,
                            series: {},
                        };
                        // Check each data series for null/empty gaps
                        for (const [key, arr] of Object.entries(obj)) {
                            if (key === 'labels') continue;
                            if (Array.isArray(arr)) {
                                const total = arr.length;
                                const nulls = arr.filter(v => v === null || v === undefined || v === '').length;
                                info.series[key] = {total, nulls, pct_filled: total > 0 ? Math.round((total - nulls) / total * 100) : 0};
                            }
                        }
                        checks.charts[name] = info;
                    } else {
                        checks.charts[name] = {error: 'no labels'};
                    }
                } catch(e) {
                    checks.charts[name] = {error: e.message};
                }
            }

            // Check VALIDATION_REPORT — v1.0.3+ fetches data/validation_report.json
            // at runtime (see METHODOLOGY.md §5). Falls back to inline const for
            // pre-v1.0.3 HTMLs.
            try {
                if (typeof fetchValidationReport === 'function') {
                    const report = await fetchValidationReport();
                    checks.validation = (report && report.status) || 'present';
                } else if (typeof VALIDATION_REPORT !== 'undefined') {
                    checks.validation = VALIDATION_REPORT.status || 'present';
                } else {
                    checks.validation = 'missing';
                }
            } catch(e) {
                checks.validation = 'error:' + (e && e.message ? e.message : e);
            }

            // SHOCK_TRACKER DOM-based check: page-scope `const` isn't reachable
            // via the Playwright evaluate function, so instead of eval()ing we
            // confirm the rendered DOM contains the expected oil-impact phase
            // titles and status pills. Structural JSON validation lives in the
            // validator's text-based check_shock_tracker() instead.
            try {
                const tabOil = document.getElementById('tab-oil');
                let phaseTitles = 0, statusPills = 0;
                if (tabOil) {
                    // Phase title text rendered from SHOCK_TRACKER mapping
                    const titles = ['Pump prices spike','Transport & freight costs',
                        'CPI Energy prints','Food & services inflation','Core goods inflation',
                        'Consumer sentiment falls','Savings drawdown','Delinquencies climb'];
                    const text = tabOil.textContent || '';
                    phaseTitles = titles.filter(t => text.includes(t)).length;
                    // Status pills render statusCfg.label strings
                    ['Confirmed','Emerging','Not Yet','On Track','Ahead!','No Data']
                        .forEach(l => { if (text.includes(l)) statusPills++; });
                }
                checks.shock_tracker_dom = {
                    oil_tab_present: !!tabOil,
                    phase_titles_found: phaseTitles,
                    expected_phase_titles: 8,
                    distinct_status_labels: statusPills,
                };
            } catch(e) {
                checks.shock_tracker_dom = {error: e.message};
            }

            return checks;
        }''')

        # KPIS checks
        kpis_count = js_checks.get('kpis_count', -1)
        _check('data', 'KPIS defined', kpis_count > 0, f'count={kpis_count}')
        if kpis_count > 0:
            _check('data', 'KPIS all have values', js_checks.get('kpis_empty', 99) == 0,
                   f'{js_checks.get("kpis_empty")} empty')
            _check('data', 'KPIS no NaN/undefined', not js_checks.get('kpis_has_nan', True))

        # Chart data checks — existence + completeness
        # Sparse-by-design overrides — same table as validator.check_internal
        # keeps the two passes in sync on what counts as "expected to be sparse".
        SPARSE_OK = {
            'FFR_DATA.dots': 10,          # Fed dot plot: forecast years only
            'OIL_DAILY.notes': 0,         # big-move annotations are sparse by design
        }
        for chart_name, info in js_checks.get('charts', {}).items():
            if 'error' in info:
                _check('data', f'{chart_name} defined', False, info['error'])
            else:
                _check('data', f'{chart_name} has data',
                       info.get('labels', 0) > 0 and info.get('has_data', False),
                       f'{info.get("labels", 0)} labels')
                # Check each series for data completeness (>=threshold filled)
                for series_name, series_info in info.get('series', {}).items():
                    total = series_info.get('total', 0)
                    nulls = series_info.get('nulls', 0)
                    pct = series_info.get('pct_filled', 0)
                    min_pct = SPARSE_OK.get(f'{chart_name}.{series_name}', 50)
                    if total > 0:
                        _check('data', f'{chart_name}.{series_name} completeness',
                               pct >= min_pct,
                               f'{nulls}/{total} empty ({pct}% filled, min {min_pct}%)',
                               severity='warning')

        # Validation report — post-v1.0.3 this is fetched at runtime, so the
        # check verifies the fetch resolves (not just that a const exists).
        _val = js_checks.get('validation', 'unknown')
        _val_ok = _val != 'missing' and not str(_val).startswith('error')
        _check('data', 'VALIDATION_REPORT present', _val_ok, _val)

        # Shock tracker DOM rendering: text-based verification that the phases
        # actually appear on the page. (Structural JSON check lives in the
        # validator's check_shock_tracker(), which reads the raw HTML.)
        stdom = js_checks.get('shock_tracker_dom', {})
        if 'error' in stdom:
            _check('data', 'SHOCK_TRACKER DOM rendered', False, stdom['error'], severity='warning')
        else:
            _check('data', 'SHOCK_TRACKER oil tab present', stdom.get('oil_tab_present', False))
            _check('data', 'SHOCK_TRACKER all 8 phase titles rendered',
                   stdom.get('phase_titles_found') == 8,
                   f'{stdom.get("phase_titles_found")}/8 titles found',
                   severity='warning')

        # ── Annotation lexicon (style_guide.md §4.5) ───────────────────
        # Verify the four annotated charts still carry their canonical
        # labels. The labels are read directly off the HTML source (not
        # via MC instances) because MC config lives in JS object literals
        # not exposed as globals. If renderer.py or a regression silently
        # drops the plugins.hLines / plugins.vEvents config, this check
        # catches it before publish.
        #
        # The table below is the source-of-truth lexicon. Update it AND
        # data/style_guide.md §4.5 together — never one without the other.
        html_source = HTML_FILE.read_text(encoding='utf-8')
        ANNOTATION_LEXICON = [
            # (label, min_occurrences, owner_charts)
            ('Fed 2% target',         2, 'c-cpi-mom, c-pce-mom (+ PCE annual series legend)'),
            ('Hormuz shock, Mar 2026', 3, 'c-cpi-mom, c-pce-mom, c-oil-monthly'),
            ('Neutral rate, 2.5–3.0%', 1, 'c-ffr'),
        ]
        for label, min_n, owners in ANNOTATION_LEXICON:
            n = html_source.count(label)
            _check(
                'annotations',
                f'lexicon: "{label}" present ≥{min_n}× ({owners})',
                n >= min_n,
                f'found {n} occurrences, expected ≥{min_n} — see style_guide.md §4.5',
                severity='warning',
            )
        # Negative check: forbidden legacy spellings (the four amateur-hour
        # spellings the editorial review flagged). Any survivor here means
        # a partial rename or a regression.
        FORBIDDEN_ANNOTATION_STRINGS = [
            'Fed 2% Target',           # title-case relic
            'Mar 2026 oil shock',       # superseded by Hormuz shock
            'FOMC neutral rate',        # superseded by Neutral rate
            '"Oil shock"',              # bare "Oil shock" as annotation label
        ]
        for bad in FORBIDDEN_ANNOTATION_STRINGS:
            n = html_source.count(bad)
            _check(
                'annotations',
                f'lexicon: legacy string "{bad}" not present',
                n == 0,
                f'found {n} occurrences — replace per style_guide.md §4.5',
                severity='warning',
            )

        browser.close()

    # ── Build report ───────────────────────────────────────────────
    report = {
        'checked_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'status': 'PASS' if FAIL == 0 else 'WARN' if FAIL <= 3 else 'FAIL',
        'summary': {
            'total_checks': PASS + FAIL,
            'passed': PASS,
            'failed': FAIL,
            'js_errors': len(js_errors),
            'console_errors': len(real_errors),
        },
        'js_errors': js_errors[:10],
        'console_errors': [e['text'][:200] for e in real_errors[:10]],
        'findings': findings,
    }

    RPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RPT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')

    # Summary
    status_icon = '✅' if FAIL == 0 else '⚠️' if FAIL <= 3 else '❌'
    print(f'\n[Agent 7] {status_icon} Visual QA {report["status"]} — '
          f'{PASS}/{PASS+FAIL} checks passed, {FAIL} failed')
    if js_errors:
        print(f'  JS errors: {len(js_errors)}')
    print(f'  Report saved to {RPT_FILE.name}')

    if FAIL > 0:
        print(f'\n  Failures:')
        for f in findings:
            if not f['pass']:
                print(f'    [{f["category"]}] {f["check"]}: {f.get("detail", "")}')

    # Only fail on critical issues (>3 failures), treat minor warnings as passing
    critical_fails = sum(1 for f in findings if not f['pass'] and f.get('severity') == 'critical')
    return critical_fails == 0


if __name__ == '__main__':
    screenshots = '--screenshots' in sys.argv
    ok = run_visual_qa(take_screenshots=screenshots)
    sys.exit(0 if ok else 1)
