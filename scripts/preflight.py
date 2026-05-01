#!/usr/bin/env python3
"""
Agent 0 — PRE-FLIGHT
Validates external dependencies (FRED series + Anthropic models) BEFORE the
briefing pipeline runs. Halts CI immediately on any 4xx so we never waste a
full pipeline run + commit + email send on a build whose data or AI calls
are already broken.

Concurrent path-of-defense to validator Pass 3h:
  - Agent 0 (this) — pre-emptive: fail before collector wastes a fetch
  - Pass 3h        — post-hoc: surface anything that slipped through

What gets checked:
  1. Every FRED series_id literal in collector.py (~52 IDs) — limit=1 ping
  2. Every Claude model ID in scripts/_models.py — verified against
     Anthropic's /v1/models catalog. Catches deprecated aliases (the
     class of bug that produced run #116's Agent 3 404).

Bypass: set PREFLIGHT_SKIP=1 to skip (useful in local dev w/o keys).
"""

import os, re, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _models import ALL_MODEL_IDS

ROOT = Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / 'scripts' / 'collector.py'

FRED_KEY = os.environ.get('FRED_API_KEY', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
SKIP = os.environ.get('PREFLIGHT_SKIP', '') == '1'

# IDs deliberately allowed to fail (e.g. legacy/optional series). Empty by
# default — every active ID should be live.
_ALLOWLIST_FAIL: set[str] = set()


def extract_fred_ids(src: str) -> list[str]:
    """Pull every FRED series_id literal out of collector.py source."""
    ids: set[str] = set()
    # fred_obs('XXX', ...)        — main data fetcher
    # fred_alfred_obs('XXX', ...) — vintage-pinned variant
    # fv('XXX')                   — single-latest helper
    for fn in ('fred_obs', 'fred_alfred_obs', 'fv'):
        ids |= set(re.findall(rf"{fn}\(\s*['\"]([A-Z0-9_]+)['\"]", src))
    return sorted(ids)


def check_anthropic_models(timeout: int = 10) -> tuple[bool, str, list[str]]:
    """Validate every model ID in _models.py against Anthropic's /v1/models.
    Returns (all_ok, status_msg, list_of_bad_ids). list_of_bad_ids is empty
    when all configured IDs are served."""
    if not ANTHROPIC_KEY:
        return True, 'skipped (no ANTHROPIC_API_KEY)', []
    try:
        r = requests.get(
            'https://api.anthropic.com/v1/models',
            headers={
                'x-api-key': ANTHROPIC_KEY,
                'anthropic-version': '2023-06-01',
            },
            timeout=timeout,
        )
    except Exception as e:
        return False, f'network error: {e}', []
    if r.status_code != 200:
        return False, f'{r.status_code} {r.reason}', []
    body = r.json()
    served_ids = {m.get('id') for m in body.get('data', []) if m.get('id')}
    if not served_ids:
        return False, 'empty model catalog returned', []
    bad = [mid for mid in ALL_MODEL_IDS if mid not in served_ids]
    if bad:
        return False, f'{len(bad)} configured model(s) not served', bad
    return True, f'{len(ALL_MODEL_IDS)} model(s) verified against {len(served_ids)} served', []


def check_fred_id(sid: str, timeout: int = 10) -> tuple[bool, str]:
    """Returns (ok, status_msg). True = series exists and returns data."""
    if not FRED_KEY:
        return True, 'skipped (no FRED_API_KEY)'
    try:
        r = requests.get(
            'https://api.stlouisfed.org/fred/series/observations',
            params={
                'series_id': sid,
                'api_key': FRED_KEY,
                'file_type': 'json',
                'limit': 1,
                'sort_order': 'desc',
            },
            timeout=timeout,
        )
    except Exception as e:
        return False, f'network error: {e}'

    if r.status_code != 200:
        return False, f'{r.status_code} {r.reason}'
    body = r.json()
    obs = body.get('observations', [])
    if not obs:
        return False, '200 OK but no observations'
    return True, f"200 OK (latest {obs[0].get('date', '?')})"


def main() -> int:
    if SKIP:
        print('[Agent 0] PREFLIGHT_SKIP=1 — skipping pre-flight checks')
        return 0

    if not FRED_KEY:
        print('[Agent 0] No FRED_API_KEY in env — pre-flight runs in dry mode '
              '(extracts IDs but cannot verify them). Set PREFLIGHT_SKIP=1 to '
              'silence this message in local dev.')
        ids = extract_fred_ids(COLLECTOR.read_text(encoding='utf-8'))
        print(f'[Agent 0] Would check {len(ids)} FRED series IDs in real run')
        return 0

    # ── Anthropic model ID validation ────────────────────────────────
    print(f'[Agent 0] Validating {len(ALL_MODEL_IDS)} Claude model ID(s) '
          f'against /v1/models...')
    ok, msg, bad_models = check_anthropic_models()
    if ok:
        print(f'  ✅ {msg}')
    else:
        print(f'  ❌ Anthropic models check: {msg}')
        for mid in bad_models:
            print(f'     - {mid} not in served catalog')
        if bad_models:
            print('\n[Agent 0] ❌ Halting pipeline — fix scripts/_models.py '
                  'with currently-served model IDs (see https://docs.anthropic.com'
                  '/en/docs/about-claude/models).')
            return 1
        # Non-fatal failures (network, no key) just print and continue.

    # ── FRED series ID validation ────────────────────────────────────
    src = COLLECTOR.read_text(encoding='utf-8')
    ids = extract_fred_ids(src)
    print(f'[Agent 0] Pre-flight: checking {len(ids)} FRED series IDs...')

    bad: list[tuple[str, str]] = []
    t0 = time.time()
    for sid in ids:
        ok, msg = check_fred_id(sid)
        if ok:
            print(f'  ✅ {sid}: {msg}')
        else:
            print(f'  ❌ {sid}: {msg}')
            if sid not in _ALLOWLIST_FAIL:
                bad.append((sid, msg))
        # FRED's documented limit is 120 req/min per key. Pre-flight + Agent 1
        # collector run back-to-back add up to ~130 calls in <60s, which trips
        # 429s on the last few. 700ms throttle = ≤86 req/min, leaves headroom
        # for the collector's ~80 calls in the same rolling window.
        time.sleep(0.7)

    elapsed = time.time() - t0
    print(f'[Agent 0] Checked {len(ids)} IDs in {elapsed:.1f}s')

    if bad:
        print(f'\n[Agent 0] ❌ {len(bad)} bad series ID(s) — halting pipeline:')
        for sid, msg in bad:
            print(f'  - {sid}: {msg}')
        print('\nFix: update scripts/collector.py with valid FRED IDs, or add '
              'them to _ALLOWLIST_FAIL in scripts/preflight.py if intentional.')
        return 1

    print(f'[Agent 0] ✅ All {len(ids)} series IDs valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
