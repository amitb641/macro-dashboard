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
BLS_KEY  = os.environ.get('BLS_API_KEY', '')
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


def check_fred_id(sid: str, timeout: int = 10) -> tuple[str, str]:
    """Validate one FRED series_id. Returns (status, msg) where status is:
      'ok'      — 200 with observations, ID is valid
      'fatal'   — 4xx, ID is genuinely bad (halt pipeline)
      'warn'    — 5xx after retries, transient FRED server issue
      'skipped' — no API key (local dev mode)

    Retries 5xx up to 3 times with backoff so a transient FRED hiccup
    doesn't kill the pipeline (run #119 surfaced this — PCEPILFE and
    DGDSRG3M086SBEA both returned 500 mid-batch despite being live IDs)."""
    if not FRED_KEY:
        return 'skipped', 'skipped (no FRED_API_KEY)'

    params = {
        'series_id': sid, 'api_key': FRED_KEY,
        'file_type': 'json', 'limit': 1, 'sort_order': 'desc',
    }
    last_status = None
    for attempt in range(3):
        try:
            r = requests.get(
                'https://api.stlouisfed.org/fred/series/observations',
                params=params, timeout=timeout)
        except Exception as e:
            return 'warn', f'network error: {e}'

        if r.status_code == 200:
            obs = r.json().get('observations', [])
            if not obs:
                return 'fatal', '200 OK but no observations'
            return 'ok', f"200 OK (latest {obs[0].get('date', '?')})"

        if 400 <= r.status_code < 500:
            return 'fatal', f'{r.status_code} {r.reason}'

        # 5xx — transient, retry
        last_status = f'{r.status_code} {r.reason}'
        if attempt < 2:
            time.sleep(2 * (attempt + 1))  # 2s, 4s

    # Exhausted retries on 5xx — warn, don't halt
    return 'warn', f'{last_status} (after 3 attempts)'


def extract_bls_ids(src: str) -> list[str]:
    """Pull BLS series IDs out of bls_fetch([...]) calls in collector.py."""
    ids: set[str] = set()
    # Matches quoted IDs inside bls_fetch([...]) — e.g. 'LNU04032231'
    for m in re.finditer(r"bls_fetch\(\s*\[([^\]]+)\]", src, re.DOTALL):
        ids |= set(re.findall(r"['\"]([A-Z0-9]+)['\"]", m.group(1)))
    return sorted(ids)


def check_bls_ids(series_ids: list[str], timeout: int = 20) -> tuple[bool, list[str], list[str]]:
    """Validate BLS series IDs via API v2. Returns (all_ok, bad_ids, warn_msgs).
    Uses BLS_KEY if set; falls back to anonymous (lower rate limit, still works
    for pre-flight volume of ≤11 series). The 'Series does not exist' message
    in the API response is the canonical signal for an invalid ID."""
    if not series_ids:
        return True, [], []

    payload: dict = {'seriesid': series_ids, 'startyear': str(__import__('datetime').date.today().year), 'endyear': str(__import__('datetime').date.today().year)}
    if BLS_KEY:
        payload['registrationkey'] = BLS_KEY

    try:
        r = requests.post(
            'https://api.bls.gov/publicAPI/v2/timeseries/data/',
            json=payload, timeout=timeout)
        r.raise_for_status()
        body = r.json()
    except Exception as e:
        # Network/server error — warn, don't halt (BLS outages are transient)
        return True, [], [f'BLS API unreachable: {e}']

    # Collect "Series does not exist" from response messages
    messages = body.get('message', [])
    bad = [re.sub(r'.*Series (\S+).*', r'\1', msg) for msg in messages
           if 'does not exist' in msg.lower()]

    # Cross-check: series with 0 obs that aren't in the bad list (ambiguous)
    zero_obs = [s['seriesID'] for s in body.get('Results', {}).get('series', [])
                if not s.get('data') and s['seriesID'] not in bad]

    warns = []
    if zero_obs:
        warns.append(f'BLS series returned 0 obs (may be valid but empty for this year): {zero_obs}')

    return len(bad) == 0, bad, warns


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

    bad: list[tuple[str, str]] = []     # 4xx — real config error, halts pipeline
    transient: list[tuple[str, str]] = []  # 5xx after retries — warn, continue
    t0 = time.time()
    for sid in ids:
        status, msg = check_fred_id(sid)
        if status == 'ok' or status == 'skipped':
            print(f'  ✅ {sid}: {msg}')
        elif status == 'warn':
            print(f'  ⚠  {sid}: {msg} (transient, not halting)')
            transient.append((sid, msg))
        elif status == 'fatal':
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

    if transient:
        print(f'\n[Agent 0] ⚠  {len(transient)} transient FRED 5xx error(s) — '
              f'continuing (collector has its own 429/5xx retry logic):')
        for sid, msg in transient:
            print(f'  - {sid}: {msg}')

    print(f'[Agent 0] ✅ All {len(ids)} FRED series IDs valid')

    # ── BLS series ID validation ─────────────────────────────────────
    src_text = COLLECTOR.read_text(encoding='utf-8')
    bls_ids = extract_bls_ids(src_text)
    if bls_ids:
        print(f'[Agent 0] Pre-flight: checking {len(bls_ids)} BLS series IDs...')
        bls_ok, bls_bad, bls_warns = check_bls_ids(bls_ids)
        for w in bls_warns:
            print(f'  ⚠  {w}')
        if bls_ok:
            print(f'  ✅ {len(bls_ids)} BLS series verified')
        else:
            print(f'  ❌ {len(bls_bad)} BLS series do not exist:')
            for sid in bls_bad:
                if sid not in _ALLOWLIST_FAIL:
                    print(f'     - {sid}')
            real_bad = [s for s in bls_bad if s not in _ALLOWLIST_FAIL]
            if real_bad:
                print('\n[Agent 0] ❌ Halting pipeline — fix scripts/collector.py '
                      'BLS series IDs (BLS does not publish SA sector rates; use '
                      'LNU04 not-SA series, or add to _ALLOWLIST_FAIL if intentional).')
                return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
