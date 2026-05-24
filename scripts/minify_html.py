#!/usr/bin/env python3
"""Tier 2 post-processor: minify + mangle inline JS in index.html.

This script runs as a Vercel build step (declared in vercel.json
buildCommand). It is NOT part of the weekly renderer pipeline — the
renderer always writes readable source so its regex patches keep
working across runs.

Flow
----
1. Read index.html (renderer output).
2. Extract all inline <script> blocks (no src= attribute).
3. Concatenate them in document order, separated by semicolons.
4. Pipe through esbuild --minify (whitespace + identifiers + syntax).
5. Write a single <script>…</script> containing the minified bundle
   back into index.html, replacing the original inline blocks.
6. External script tags (chart.umd.min.js, theme-overlay.js, etc.)
   are preserved in-place.

Output: index.html overwritten with minified inline JS. The build
artefact is served by Vercel; the git-committed source is unchanged
(Vercel fetches a fresh copy for every deployment).

Safety notes
------------
- window.MD is preserved: every inline block opens with
  `var MD = window.MD = window.MD || {};` so the window assignment
  lands even after esbuild mangles the local `MD` binding.
- window.Chart is an external UMD global — never touched.
- _hydrationCallbacks, _hydrationDone: accessed via window.MD.*, safe.
- State-JSON keys (KPIS, SHOCK_TRACKER, …) are string-keyed object
  properties, never renamed by esbuild's identifier mangler.

Usage
-----
    python scripts/minify_html.py [--check]   # --check: dry-run, print size delta only
    python scripts/minify_html.py              # default: overwrite index.html
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_IN = ROOT / 'index.html'
HTML_OUT = ROOT / 'index.html'  # overwrite in place

# Inline block pattern — captures attrs and body separately.
# Matches <script ...>...</script> where the attrs group has no src=.
_SCRIPT_RE = re.compile(
    r'(<script)((?![^>]*\bsrc\s*=)[^>]*)>(.*?)</script>',
    re.DOTALL,
)

# Sentinel comment dropped into the HTML where the inline blocks lived,
# replaced at the end with a single minified <script> tag.
_SENTINEL = '<!--__MINIFIED_JS_SENTINEL__-->'


def _esbuild_minify(js: str) -> str:
    """Pipe JS through esbuild --minify and return minified output.

    On Windows npx resolves to a .cmd script which subprocess can only
    invoke via shell=True. On Linux/macOS npx is a regular executable.
    """
    import shutil, platform

    # Prefer a local node_modules/.bin/esbuild if present (avoids npx).
    local_esbuild = ROOT / 'node_modules' / '.bin' / 'esbuild'
    if sys.platform == 'win32':
        local_esbuild_win = ROOT / 'node_modules' / '.bin' / 'esbuild.cmd'
        if local_esbuild_win.exists():
            local_esbuild = local_esbuild_win

    if local_esbuild.exists():
        cmd_args = [str(local_esbuild)]
        use_shell = False
    else:
        # Fall back to npx. On Windows this is a .cmd file and needs
        # shell=True to be invocable without the full path.
        cmd_args = ['npx', '--yes', 'esbuild']
        use_shell = sys.platform == 'win32'

    cmd_args += [
        '--minify',
        '--platform=browser',
        '--target=es2018',
        '--log-level=warning',
    ]

    result = subprocess.run(
        cmd_args,
        input=js.encode('utf-8'),
        capture_output=True,
        timeout=120,
        shell=use_shell,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode('utf-8', errors='replace')
        raise RuntimeError(f'esbuild exited {result.returncode}:\n{stderr}')
    return result.stdout.decode('utf-8')


def minify(dry_run: bool = False) -> None:
    html = HTML_IN.read_text(encoding='utf-8')
    original_size = len(html.encode('utf-8'))

    # ── Step 1: strip all inline script blocks, collect their bodies. ──
    # External blocks (src=…) are left untouched.
    inline_chunks: list[str] = []

    def _strip_inline(m: re.Match) -> str:
        body = m.group(3)
        if not body.strip():
            return m.group(0)  # empty body — keep (shouldn't happen)
        inline_chunks.append(body)
        return ''  # remove from HTML

    html_sentinel = _SCRIPT_RE.sub(_strip_inline, html)

    # ── Step 2: clean up the blank lines left behind. ──
    html_sentinel = re.sub(r'\n{3,}', '\n\n', html_sentinel)

    # ── Step 3: insert sentinel at end-of-body. ──
    # chart.umd.min.js loads in <head> (line ~23) before the body, so
    # Chart is available globally when the consolidated block runs here.
    # Placing at end-of-body matches the original layout — most inline
    # scripts were near the end of the document and expected all DOM
    # elements to already exist when they ran. Moving them to <head>
    # would cause "Cannot set properties of null" for any code that
    # writes to body elements.
    first_body_close = html_sentinel.find('</body>')
    if first_body_close >= 0:
        html_sentinel = (
            html_sentinel[:first_body_close]
            + _SENTINEL + '\n'
            + html_sentinel[first_body_close:]
        )
    else:
        # Fallback: insert before </html>
        html_sentinel = html_sentinel.replace('</html>', _SENTINEL + '\n</html>', 1)

    if not inline_chunks:
        print('No inline script blocks found — nothing to do.')
        return

    js_concat = ';\n'.join(inline_chunks)
    original_js_size = len(js_concat.encode('utf-8'))

    print(f'Inline JS blocks : {len(inline_chunks)}')
    print(f'Inline JS size   : {original_js_size / 1024:.1f} KB')

    if dry_run:
        print('[dry-run] Skipping esbuild invocation.')
        return

    print('Running esbuild --minify …')
    minified_js = _esbuild_minify(js_concat)
    minified_js_size = len(minified_js.encode('utf-8'))

    reduction_pct = (1 - minified_js_size / original_js_size) * 100
    print(f'Minified JS size : {minified_js_size / 1024:.1f} KB  '
          f'({reduction_pct:.0f}% reduction)')

    # Splice the minified bundle back at the sentinel position.
    html_out = html_sentinel.replace(
        _SENTINEL,
        f'<script>{minified_js}</script>',
        1,
    )

    final_size = len(html_out.encode('utf-8'))
    page_reduction_pct = (1 - final_size / original_size) * 100
    print(f'Page size before : {original_size / 1024:.1f} KB')
    print(f'Page size after  : {final_size / 1024:.1f} KB  '
          f'({page_reduction_pct:.0f}% reduction)')

    HTML_OUT.write_text(html_out, encoding='utf-8')
    print(f'Written → {HTML_OUT}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Dry-run: report size delta without writing.')
    args = parser.parse_args()
    try:
        minify(dry_run=args.check)
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
