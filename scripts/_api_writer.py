"""Tier 1 anti-clone scaffolding — state bundle writer.

The dashboard's data layer is being migrated from inline JS consts in
``index.html`` to an Origin-gated ``/api/state.json`` endpoint. This
module is the renderer-side half of that migration.

Usage
-----
Inside each renderer patch function that previously wrote a full JSON
literal into ``index.html``, call::

    from scripts import _api_writer
    _api_writer.register('KPIS', kpi_cards_list)

Then patch the inline declaration to a ``null`` placeholder instead of
the full literal, e.g.::

    const KPIS = [...lots of data...];   # before
    let KPIS = null;                     # after — boot loader hydrates

At the end of ``render()``, call ``_api_writer.flush()`` once. That
writes ``data/state.json`` containing every registered payload. The
``api/state.js`` serverless function reads that file at request time.

Why a module-level accumulator
------------------------------
Renderer patches are spread across ~20 functions. Threading a
container dict through every call signature would be invasive. The
single-process renderer model (one ``python scripts/renderer.py``
invocation per pipeline run) makes module-level mutable state safe
here; the alternative (a class threaded through the pipeline) is
strictly more code for no behavioural difference.

Idempotency
-----------
``register`` overwrites by key. ``flush`` overwrites the output file.
Both behaviours match the renderer's existing "rebuild each run from
raw data" contract — there's no incremental-update mode to worry
about.

``read_prior(key)`` reads the previous run's value for a key from
``data/state.json`` — used by rebuild functions that preserve a
manually-curated field across runs (e.g. NFP_VS_ADP.adp). All other
behaviour is write-only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# In-memory accumulator. Module-scope is fine — one renderer run,
# one Python process.
_STATE: Dict[str, Any] = {}

# Where the state bundle lands. Resolved against repo root, not CWD,
# so the renderer can be invoked from anywhere.
# Override via MACRO_STATE_FILE env var for test isolation — without this,
# test runs that call renderer.render() write synthetic data into the real
# data/state.json and blank Tier-1 charts until the next CI run rebuilds it.
_ROOT = Path(__file__).resolve().parent.parent
_STATE_FILE = Path(os.environ['MACRO_STATE_FILE']) if 'MACRO_STATE_FILE' in os.environ \
    else _ROOT / 'data' / 'state.json'


def register(key: str, payload: Any) -> None:
    """Record ``payload`` under ``key`` for inclusion in ``data/state.json``.

    Overwrites any previous value for the same key. Caller is
    responsible for passing JSON-serializable data — we don't coerce
    or validate, mirroring how the renderer's inline-JSON writes work
    today.
    """
    if not isinstance(key, str) or not key:
        raise ValueError('register: key must be a non-empty string')
    _STATE[key] = payload


def flush(meta: Dict[str, Any] | None = None) -> Path:
    """Write the accumulated state bundle to ``data/state.json``.

    The bundle has the shape::

        {
          "_meta": {
            "written_at": "<ISO-8601 UTC>",
            "writer": "scripts/_api_writer.py",
            "version": <build version from env, or null>
          },
          "<key1>": ...,
          "<key2>": ...,
          ...
        }

    ``_meta`` is reserved — registering a key called ``_meta``
    raises. Other keys are written verbatim.

    Returns the resolved output path so the caller can log it.
    """
    if '_meta' in _STATE:
        raise ValueError('flush: "_meta" is a reserved key')

    import datetime
    out = {
        '_meta': {
            'written_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'writer': 'scripts/_api_writer.py',
            'version': os.environ.get('BUILD_V') or None,
            'keys': sorted(_STATE.keys()),
        }
    }
    # Sort keys for deterministic diffs in git.
    for k in sorted(_STATE.keys()):
        out[k] = _STATE[k]

    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(out, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8',
    )
    return _STATE_FILE


def keys() -> list[str]:
    """Return the list of currently-registered keys (for logging)."""
    return sorted(_STATE.keys())


# Cache of the prior on-disk state.json, loaded lazily on first
# read_prior() call. Used by rebuild functions that need to preserve
# manually-curated fields (e.g. NFP_VS_ADP.adp, SECTOR_MOM.sectors
# ordering, FC_MACRO actNN seed history) across runs without scraping
# them out of the live HTML via regex.
_PRIOR_LOADED = False
_PRIOR_CACHE: Dict[str, Any] = {}


def _ensure_prior_loaded() -> None:
    """Load ``data/state.json`` into the prior-cache on first access.

    Idempotent — subsequent calls are no-ops. Missing file or invalid
    JSON yields an empty cache (so callers get ``None`` from
    ``read_prior`` and fall through to their own defaults).
    """
    global _PRIOR_LOADED
    if _PRIOR_LOADED:
        return
    _PRIOR_LOADED = True
    try:
        if _STATE_FILE.exists():
            obj = json.loads(_STATE_FILE.read_text(encoding='utf-8'))
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k != '_meta':
                        _PRIOR_CACHE[k] = v
    except (OSError, json.JSONDecodeError):
        # Treat any read/parse failure as "no prior state" — the
        # renderer's fall-back paths handle that case.
        pass


def read_prior(key: str, default: Any = None) -> Any:
    """Return the previous run's payload for ``key`` from ``data/state.json``.

    First call lazily loads the file. Subsequent calls hit an in-memory
    cache. Returns ``default`` if the file is missing, unreadable, or
    doesn't contain the key.

    This is the round-trip half of state.json: lets rebuild functions
    that previously regex-scraped preserved fields from the live HTML
    (e.g. manually-curated ADP entries on NFP_VS_ADP) read them from
    the canonical state instead.
    """
    if not isinstance(key, str) or not key:
        return default
    _ensure_prior_loaded()
    return _PRIOR_CACHE.get(key, default)


def reset() -> None:
    """Drop all registered state. Used by tests; never by the renderer."""
    _STATE.clear()
    global _PRIOR_LOADED
    _PRIOR_LOADED = False
    _PRIOR_CACHE.clear()
