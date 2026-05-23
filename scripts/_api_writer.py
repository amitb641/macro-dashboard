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

This module never reads ``data/state.json``. It's write-only.
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
_ROOT = Path(__file__).resolve().parent.parent
_STATE_FILE = _ROOT / 'data' / 'state.json'


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


def reset() -> None:
    """Drop all registered state. Used by tests; never by the renderer."""
    _STATE.clear()
