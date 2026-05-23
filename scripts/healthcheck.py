#!/usr/bin/env python3
"""
Post-Deploy Health Check
Verifies the live dashboard page is accessible and contains expected content.
Runs after GitHub Pages deployment.

Usage: python scripts/healthcheck.py <page_url>
"""

import sys, time

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)


REQUIRED_MARKERS = [
    'Macro Dashboard',          # Page title
    # KPIS migrated to /api/state.json (Tier 1 anti-clone) —
    # inline declaration is now `let KPIS = null;`. Match either
    # shape so the marker still proves the renderer ran.
    ('const KPIS', 'let KPIS'),
    'const CPI_MONTHLY',        # CPI chart data
    'const U_MONTHLY',          # Unemployment chart data
    'tab-panel',                # Tab structure present
]

# Minimum page size (bytes) — a valid dashboard is at least 100KB
MIN_PAGE_SIZE = 100_000

# Max retries (Pages deployment can take a moment to propagate)
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


def healthcheck(url):
    """Verify deployed page is healthy. Returns True if all checks pass."""
    print(f'[Health Check] Verifying: {url}')

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=30, headers={'Cache-Control': 'no-cache'})

            # Check HTTP status
            if r.status_code != 200:
                last_err = f'HTTP {r.status_code}'
                if attempt < MAX_RETRIES - 1:
                    print(f'  Attempt {attempt + 1}: {last_err}, retrying in {RETRY_DELAY}s...')
                    time.sleep(RETRY_DELAY)
                    continue
                break

            body = r.text
            size = len(body.encode('utf-8'))

            # Check page size
            if size < MIN_PAGE_SIZE:
                print(f'  FAIL: Page too small ({size:,} bytes, expected >= {MIN_PAGE_SIZE:,})')
                return False

            # Check required content markers. A marker can be a single
            # string OR a tuple of acceptable alternatives (any-of) — the
            # tuple form lets us tolerate `const KPIS` → `let KPIS = null;`
            # migration without breaking the gate.
            def _matched(marker):
                if isinstance(marker, tuple):
                    return any(alt in body for alt in marker)
                return marker in body
            missing = [m for m in REQUIRED_MARKERS if not _matched(m)]
            if missing:
                print(f'  FAIL: Missing content markers: {missing}')
                return False

            # Check for error indicators
            error_signs = ['Traceback (most recent call last)', 'Internal Server Error', '503 Service']
            found_errors = [e for e in error_signs if e in body]
            if found_errors:
                print(f'  FAIL: Error content detected: {found_errors}')
                return False

            print(f'  OK: HTTP 200, {size:,} bytes, all {len(REQUIRED_MARKERS)} markers present')
            return True

        except requests.exceptions.Timeout:
            last_err = 'timeout'
            if attempt < MAX_RETRIES - 1:
                print(f'  Attempt {attempt + 1}: timeout, retrying in {RETRY_DELAY}s...')
                time.sleep(RETRY_DELAY)
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES - 1:
                print(f'  Attempt {attempt + 1}: {last_err}, retrying in {RETRY_DELAY}s...')
                time.sleep(RETRY_DELAY)

    print(f'  FAIL: Could not reach page after {MAX_RETRIES} attempts ({last_err})')
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/healthcheck.py <page_url>')
        sys.exit(1)

    url = sys.argv[1].rstrip('/')
    ok = healthcheck(url)

    if ok:
        print('[Health Check] PASSED')
    else:
        print('[Health Check] FAILED — dashboard may be broken')

    # Exit 1 on failure to trigger auto-rollback in CI
    sys.exit(0 if ok else 1)
