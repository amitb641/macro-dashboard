"""
Findings + fixes ledger.

A small append-only registry that tracks pipeline findings across runs
and pairs each one with a recommended fix. Powers the "Recommended
Fixes" section in run_report and parallel_compare reports so issues
surfaced during the parallel-run trial aren't just observed — they
have a concrete next-action and a status the team can track until
they're resolved.

Two files:
- `data/parallel_findings_ledger.json` — machine-readable canonical
  state. Read + written by this module.
- `data/parallel_findings_ledger.md` — human-readable rendering of
  the same data, grouped by status (open / monitoring / resolved).

Schema (per entry):
    {
      "fingerprint": str,         # stable identifier
      "source": str,              # "validator" | "editorial" | "ceo_grade"
                                  #   | "visual_review" | "parallel_compare"
      "severity": str,            # "critical" | "warning"
      "title": str,               # short human label
      "detail": str,              # one-line description
      "branches_seen": list[str], # ["main", "dev"] etc.
      "first_seen": str,          # ISO 8601 UTC
      "last_seen": str,           # ISO 8601 UTC
      "occurrence_count": int,    # bumps each time observed
      "status": str,              # "open" | "monitoring" | "resolved"
      "recommended_fix": str,     # action text, looked up from KB
      "resolution_notes": str,    # filled by human when status=resolved
      "resolution_commit": str    # commit SHA if relevant
    }

Status transitions are MANUAL (human edits the JSON or md file). The
ledger never auto-resolves — that's by design: a finding might stop
appearing because someone fixed it OR because it stopped triggering;
only a human knows which.

Read-only path: this module never modifies index.html, raw data, or
anything outside `data/parallel_findings_ledger.{json,md}`.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_JSON = "data/parallel_findings_ledger.json"
LEDGER_MD = "data/parallel_findings_ledger.md"

# ───────────────────────────────────────────────────────────────────────────
# Recommended-fix knowledge base.
#
# Keys are regex patterns matched against either the finding's "name"/"id"
# field or the first 200 chars of its "message"/"detail". Order matters
# — first matching pattern wins. Add new entries as new finding classes
# are identified during the parallel-run trial.
#
# Each entry: (regex, recommended_fix_text).
# ───────────────────────────────────────────────────────────────────────────
KNOWN_FIXES: list[tuple[str, str]] = [
    (
        r"transcript_archive_coverage",
        "Archive the missing earnings transcripts under "
        "`data/transcripts/<Quarter>/<TICKER>.txt`. Validator Pass 3c "
        "(verbatim gate) requires the transcript text be present for "
        "every quoted span in `data/bank_earnings.json`. See CLAUDE.md "
        "→ 'Update Workflow (Q2 2026 onward)' for the full flow.",
    ),
    (
        r"patch_kpi.*(failed|silent|not found)",
        "Retire the legacy `patch_kpi()` calls in `scripts/renderer.py` "
        "for the named tile. Modern `inject_kpi()` already owns those "
        "labels; the obsolete calls reference labels B7 renamed/removed, "
        "and `--strict` correctly flags them as silent injection failures.",
    ),
    (
        r"vision_review|visual_review",
        "Inspect the rendered chart in `index.html` against "
        "`data/style_guide.md`. If it's a genuine regression, log the "
        "specific tile/axis problem in `data/incident_reports/<date>.md`. "
        "If it's a vision-model false positive (palette drift, anti-"
        "aliasing artifact), add a one-line note to `data/style_guide.md` "
        "to teach the next review.",
    ),
    (
        r"editorial.*length|too (long|short)|words\b",
        "Edit the flagged commentary in `data/bank_earnings.json` or "
        "the per-tab commentary block in `index.html` to match "
        "`data/style_guide.md` §2 length rules (2–4 sentences, no "
        "hedging filler).",
    ),
    (
        r"editorial.*(hedging|forbidden|filler)",
        "Remove the hedging/forbidden vocabulary from the flagged "
        "commentary. See `data/style_guide.md` §2 for the vocabulary "
        "list. Prefer concrete numerics over qualifiers.",
    ),
    (
        r"editorial.*(fabricat|invented|unsourced)",
        "Critical: a numeric in commentary couldn't be matched against "
        "a KPI tile. Either correct the number to match the tile, or "
        "remove the sentence. **Never smooth fabricated numerics.** "
        "See CLAUDE.md → 'Earnings Commentary — Factuality Rule'.",
    ),
    (
        r"staleness|stale_data",
        "Verify the upstream source publishes on the cadence "
        "`data/playbook.md` claims. If genuinely stale (lag > "
        "documented baseline), record in `data/incident_reports/` and "
        "let it ride to next run. If the baseline is wrong, update "
        "`data/known_normal.json`.",
    ),
    (
        r"cross_source|cross-source|fred.*bls|bls.*fred",
        "Two sources disagree on the same anchor metric. Cross-check "
        "the latest published value at both source URLs. Update "
        "collector to prefer the canonical source (usually the agency "
        "publication, not the FRED mirror) and document the choice in "
        "`data/playbook.md` source-precedence table.",
    ),
    (
        r"schema_contract|schema_drift",
        "An expected key or shape changed in `data/raw_data.json` or "
        "`data/signals.json`. Either the collector schema or the "
        "validator's contract is out of date. Check the collector for "
        "a recent series-id change; if intentional, update validator "
        "Pass 3f's expected-schema dict.",
    ),
    (
        r"seed_drift",
        "A series' historical observations changed vs the prior snapshot. "
        "Common when an agency revises (CPI, NFP, GDP do this monthly). "
        "Compare against `data/snapshots/<prior-date>/raw_data.json` to "
        "confirm it's an upstream revision, not a collector bug. "
        "Document genuine revisions in `data/incident_reports/`.",
    ),
    (
        r"collector_error|fetch.*failed|api.*error",
        "An upstream API call failed. Re-run the briefing with "
        "`workflow_dispatch`. If the failure repeats, the API is likely "
        "down — check status pages for FRED/BLS/EIA/Anthropic. "
        "Persistent failures get a stub fixture per "
        "`data/playbook.md` §6 (offline fallback).",
    ),
    (
        r"ceo_grade|gate.*(fail|halt)",
        "Aggregated CEO-grade verdict is FAIL. Walk each layer "
        "(validator → visual_qa → vision_review → editorial → repair) "
        "and identify which one tripped. Fix the underlying finding; "
        "this aggregate clears automatically once the layers are green.",
    ),
    (
        r"divergence|delta|drift",
        "Dev and prod produced materially different outputs on the same "
        "upstream data. Capture the specific anchor metric or signal "
        "that diverged, screenshot both rendered pages, and decide: is "
        "dev's behaviour the desired one (then plan promotion to main) "
        "or a regression (then revert/fix on dev).",
    ),
]

DEFAULT_FIX = (
    "No recommended fix in the knowledge base for this finding class. "
    "Investigate manually, then if the finding recurs, add an entry to "
    "`scripts/_findings_ledger.py` → KNOWN_FIXES so the next session "
    "gets an actionable hint."
)


def lookup_recommended_fix(title: str, detail: str = "") -> str:
    """Match (title, detail) against KNOWN_FIXES regex table.

    Title is checked first (finding-class names are short + canonical).
    Detail is a fallback when titles are generic (e.g. "critical")."""
    haystack_title = title.lower() if title else ""
    haystack_detail = (detail or "").lower()[:200]
    for pattern, fix in KNOWN_FIXES:
        if re.search(pattern, haystack_title, re.IGNORECASE):
            return fix
        if re.search(pattern, haystack_detail, re.IGNORECASE):
            return fix
    return DEFAULT_FIX


# ───────────────────────────────────────────────────────────────────────────
# Fingerprint + persistence
# ───────────────────────────────────────────────────────────────────────────

def _fingerprint(source: str, title: str, detail: str) -> str:
    """Stable identifier for a finding class. The detail portion is
    truncated + lowercased so trivial wording variations (a trailing
    timestamp, a swapped number) still produce the same fingerprint."""
    normalized_detail = re.sub(r"\d", "", (detail or "").lower())[:80]
    raw = f"{source}|{title.lower().strip()}|{normalized_detail.strip()}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{source}:{title.lower().strip().replace(' ', '_')[:40]}:{h}"


def _load_ledger(repo_root: Path) -> dict:
    path = repo_root / LEDGER_JSON
    if not path.exists():
        return {"findings": [], "schema_version": 1}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Defensive: a malformed ledger should never crash a CI run.
        # Better to start fresh and log it than to halt reporting.
        return {"findings": [], "schema_version": 1}


def _save_ledger(repo_root: Path, ledger: dict) -> None:
    path = repo_root / LEDGER_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def record_finding(
    repo_root: Path,
    *,
    source: str,
    severity: str,
    title: str,
    detail: str,
    branch: str,
) -> dict:
    """Record one observation of a finding. Idempotent on fingerprint:
    a recurrence bumps `occurrence_count` and refreshes `last_seen` but
    never resets `first_seen` or downgrades `status`.

    Returns the updated entry (callers can render it immediately)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fp = _fingerprint(source, title, detail)
    ledger = _load_ledger(repo_root)
    by_fp = {e["fingerprint"]: e for e in ledger["findings"]}

    if fp in by_fp:
        entry = by_fp[fp]
        entry["last_seen"] = now
        entry["occurrence_count"] = entry.get("occurrence_count", 1) + 1
        if branch and branch not in entry.get("branches_seen", []):
            entry.setdefault("branches_seen", []).append(branch)
        # NEVER auto-resolve. A recurrence on a "resolved" finding is
        # important signal — keep status as-is, let the human re-open.
    else:
        entry = {
            "fingerprint": fp,
            "source": source,
            "severity": severity,
            "title": title,
            "detail": detail[:280],
            "branches_seen": [branch] if branch else [],
            "first_seen": now,
            "last_seen": now,
            "occurrence_count": 1,
            "status": "open",
            "recommended_fix": lookup_recommended_fix(title, detail),
            "resolution_notes": "",
            "resolution_commit": "",
        }
        ledger["findings"].append(entry)

    _save_ledger(repo_root, ledger)
    return entry


def render_markdown(repo_root: Path) -> str:
    """Render the full ledger as markdown, grouped by status."""
    ledger = _load_ledger(repo_root)
    findings = ledger.get("findings", [])
    if not findings:
        return (
            "# Parallel-run findings ledger\n\n"
            "_No findings recorded yet._\n"
        )

    open_f = [f for f in findings if f.get("status") == "open"]
    monitor_f = [f for f in findings if f.get("status") == "monitoring"]
    resolved_f = [f for f in findings if f.get("status") == "resolved"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "# Parallel-run findings ledger",
        "",
        f"_Generated {now}._",
        "",
        "Every detected critical or warning during the parallel-run trial",
        "is recorded here with a recommended fix. Status transitions are",
        "manual — when a fix lands, edit the JSON or this file to set",
        "`status: resolved` and fill `resolution_notes` + `resolution_commit`.",
        "",
        f"**Summary:** {len(open_f)} open · {len(monitor_f)} monitoring · {len(resolved_f)} resolved",
        "",
        "---",
        "",
    ]

    for status, items, heading in [
        ("open", open_f, "## Open"),
        ("monitoring", monitor_f, "## Monitoring"),
        ("resolved", resolved_f, "## Resolved"),
    ]:
        if not items:
            continue
        parts.append(heading)
        parts.append("")
        # Most-recently-seen first; helps readers spot what's hot.
        for f in sorted(items, key=lambda x: x.get("last_seen", ""), reverse=True):
            parts.extend(_render_entry(f))
            parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


def _render_entry(f: dict) -> list[str]:
    branches = ", ".join(f.get("branches_seen", [])) or "—"
    sev = f.get("severity", "?").upper()
    return [
        f"### `{f['fingerprint']}`",
        "",
        f"- **{f['title']}** ({sev}, source: `{f.get('source', '?')}`)",
        f"- Branches: {branches}",
        f"- First seen: {f.get('first_seen', '—')} · Last seen: {f.get('last_seen', '—')} · Occurrences: {f.get('occurrence_count', 1)}",
        f"- **Detail:** {f.get('detail', '—')}",
        f"- **Recommended fix:** {f.get('recommended_fix', '—')}",
        *([f"- **Resolution:** {f['resolution_notes']}" + (f" (`{f['resolution_commit']}`)" if f.get("resolution_commit") else "")] if f.get("resolution_notes") else []),
    ]


def write_markdown(repo_root: Path) -> Path:
    """Render + write the human-readable ledger. Returns the path."""
    out = repo_root / LEDGER_MD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(repo_root), encoding="utf-8")
    return out


# ───────────────────────────────────────────────────────────────────────────
# CLI: render the markdown from the current JSON (used after a manual JSON
# edit, e.g. flipping a finding to status="resolved").
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repo root (defaults to parent of scripts/)",
    )
    args = ap.parse_args()

    out = write_markdown(Path(args.repo_root))
    print(f"✅ Wrote {out}")
    sys.exit(0)
