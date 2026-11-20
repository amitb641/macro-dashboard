"""Manual data overrides (data/overrides.json) — one implementation shared by
the renderer and the validator.

An override adds an observation the upstream API does not have yet. It never
replaces an existing date. Both the renderer (what gets drawn) and the
validator (what the drawing is checked against) must see exactly the same
merged data, otherwise Pass 3j would flag every overridden point as having
"no source" (found 2026-11-20).
"""
import json
from pathlib import Path


def apply_overrides(data, ovr_file):
    """Merge overrides into data in place. Returns {key: n_added}."""
    ovr_file = Path(ovr_file)
    added_by_key = {}
    if not ovr_file.exists():
        return added_by_key
    ovr = json.loads(ovr_file.read_text(encoding='utf-8'))
    for key, entries in ovr.items():
        series = data.get(key, [])
        existing = {e['date'] for e in series}
        new = [e for e in entries if e['date'] not in existing]
        if new:
            series = series + new
            series.sort(key=lambda e: e['date'], reverse=True)
            data[key] = series
            added_by_key[key] = len(new)
    return added_by_key
