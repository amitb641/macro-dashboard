"""
Parallel-run comparison report (prod vs dev).

Generates a side-by-side diff of the structured artifacts each pipeline
produces — validator counts, CEO-grade verdicts, editorial criticals,
analyzer signal flags, raw-data anchor values — and writes the result
to data/parallel_compare_<YYYY-MM-DD>.md (plus a rolling -latest pointer).

Runs in CI from `.github/workflows/parallel-compare.yml` after either
briefing completes; the workflow gates on both branches having committed
within the last 24h so the comparison is apples-to-apples for the week.

Read-only: never modifies the source artifacts or index.html. Only emits
the report file.

Usage:
  python scripts/parallel_compare.py
  python scripts/parallel_compare.py --main-ref main --dev-ref dev/multi-expert-improvements

Exit codes:
  0 — report generated (or no-diff report written)
  1 — git fetch / read failed
  2 — neither branch has the expected artifact (likely path drift)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ───────────────────────────────────────────────────────────────────────────
# Artifacts compared. Each entry: (path-in-repo, short-name-for-report).
# Order matters — first ones appear first in the report.
# ───────────────────────────────────────────────────────────────────────────
ARTIFACTS = [
    ("data/ceo_grade_verdict.json", "CEO-grade verdict"),
    ("data/validation_report.json", "Validator"),
    ("data/editorial_report.json", "Editorial"),
    ("data/signals.json", "Signals"),
    ("data/raw_data.json", "Raw data (anchors)"),
]

# Anchor metrics extracted from raw_data.json for cross-source comparison.
# Format: (raw_data_key, label_for_report, extractor_fn or None for scalar).
def _latest_value(obj: Any) -> Any:
    """Extract latest observation value from FRED-shaped list or scalar."""
    if isinstance(obj, list) and obj:
        last = obj[-1]
        if isinstance(last, dict):
            return last.get("value", last)
        return last
    if isinstance(obj, dict):
        return obj.get("value", obj)
    return obj


RAW_ANCHORS = [
    ("core_cpi_yoy", "Core CPI YoY"),
    ("umcsent", "UMich Sentiment"),
    ("saving_rate", "Personal Saving Rate"),
    ("ffr", "Fed Funds Rate"),
    ("oil_wti", "WTI Crude"),
    ("dgs10", "10Y Treasury"),
    ("unrate", "Unemployment Rate"),
]


def git_show(ref: str, path: str) -> str | None:
    """Return file contents at `ref` or None if missing. Never raises on
    "path doesn't exist on that ref" — that's expected when an artifact
    only lives on one side."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception as e:
        print(f"[git_show] failed for {ref}:{path}: {e}", file=sys.stderr)
        return None


def load_json_ref(ref: str, path: str) -> dict | list | None:
    """Load and parse a JSON file from a git ref. Returns None on miss."""
    raw = git_show(ref, path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[load_json] {ref}:{path} not valid JSON: {e}", file=sys.stderr)
        return None


# ───────────────────────────────────────────────────────────────────────────
# Per-artifact summary functions. Each returns a short dict for table
# rendering. Robust to missing keys (returns "—" rather than KeyError).
# ───────────────────────────────────────────────────────────────────────────

def summarize_ceo_verdict(payload: dict | None) -> dict:
    if not payload:
        return {"verdict": "—", "reasons": "(artifact missing)"}
    return {
        "verdict": payload.get("verdict", "—"),
        "strict_mode": payload.get("strict_mode", "—"),
        "layer_count": len(payload.get("layers", {})) if isinstance(payload.get("layers"), dict) else "—",
        "reasons": "; ".join(payload.get("reasons", []))[:200] or "(none)",
    }


def summarize_validator(payload: dict | None) -> dict:
    if not payload:
        return {"summary": "(artifact missing)"}
    summary = payload.get("summary", {})
    if isinstance(summary, dict):
        return {
            "status": payload.get("status", "—"),
            "total_checks": summary.get("total_checks", "—"),
            "passed": summary.get("passed", "—"),
            "failed": summary.get("failed", "—"),
            "skipped": summary.get("skipped", "—"),
            "critical_divergences": summary.get("critical_divergences", "—"),
        }
    return {"summary": str(summary)[:200]}


def summarize_editorial(payload: dict | None) -> dict:
    if not payload:
        return {"summary": "(artifact missing)"}
    findings = payload.get("findings", payload.get("results", []))
    if not isinstance(findings, list):
        findings = []
    by_severity: dict[str, int] = {}
    for f in findings:
        sev = (f.get("severity") if isinstance(f, dict) else None) or "info"
        by_severity[sev] = by_severity.get(sev, 0) + 1
    return {
        "total_findings": len(findings),
        "critical": by_severity.get("critical", 0),
        "warning": by_severity.get("warning", 0),
        "info": by_severity.get("info", 0),
    }


def summarize_signals(payload: dict | None) -> dict:
    if not payload:
        return {"summary": "(artifact missing)"}
    if not isinstance(payload, dict):
        return {"summary": f"(unexpected schema: {type(payload).__name__})"}
    # signals.json carries top-level counters that the analyzer emits.
    # Prefer those over re-derived counts so the comparison matches what
    # the dashboard banner actually shows.
    signals_list = payload.get("signals", []) if isinstance(payload.get("signals"), list) else []
    return {
        "risk_level": payload.get("risk_level", "—"),
        "alert_count": payload.get("alert_count", "—"),
        "watch_count": payload.get("watch_count", "—"),
        "flagged_count": payload.get("flagged_count", "—"),
        "total_signals": len(signals_list),
    }


def summarize_raw_anchors(payload: dict | None) -> dict:
    """Pull latest value of each anchor metric for cross-branch comparison.

    raw_data.json structure is:
        {"collected_at": ..., "data": {"core_cpi_yoy": [...], ...}}
    so we descend into `data` before looking up keys.
    """
    if not payload or not isinstance(payload, dict):
        return {a[1]: "—" for a in RAW_ANCHORS}
    series = payload.get("data", payload)  # tolerate either nested or flat
    if not isinstance(series, dict):
        return {a[1]: "—" for a in RAW_ANCHORS}
    out: dict[str, Any] = {}
    for key, label in RAW_ANCHORS:
        if key in series:
            out[label] = _latest_value(series[key])
        else:
            out[label] = "—"
    return out


# ───────────────────────────────────────────────────────────────────────────
# Markdown rendering. Pure formatting; no logic.
# ───────────────────────────────────────────────────────────────────────────

def render_kv_table(prod: dict, dev: dict, title: str) -> str:
    """Render a 3-column table: key | prod | dev. Includes a delta column
    when both values are present and look comparable."""
    all_keys = list(prod.keys()) + [k for k in dev.keys() if k not in prod]
    lines = [f"### {title}", "", "| Metric | Prod (main) | Dev (parallel) | Delta |", "|---|---|---|---|"]
    for k in all_keys:
        p = prod.get(k, "—")
        d = dev.get(k, "—")
        delta = _delta_cell(p, d)
        lines.append(f"| {k} | {p} | {d} | {delta} |")
    lines.append("")
    return "\n".join(lines)


def _delta_cell(p: Any, d: Any) -> str:
    """Best-effort delta indicator. Numbers get arithmetic diff; otherwise
    a simple changed/same/—."""
    if p == "—" or d == "—":
        return "—"
    try:
        pf, df = float(p), float(d)
        diff = df - pf
        if abs(diff) < 1e-9:
            return "0"
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.3g}"
    except (TypeError, ValueError):
        return "same" if p == d else "changed"


def build_report(main_ref: str, dev_ref: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections: list[str] = [
        "# Parallel-run comparison: prod (main) vs dev",
        "",
        f"_Generated {now}._",
        "",
        f"- **Prod ref:** `{main_ref}`",
        f"- **Dev ref:** `{dev_ref}`",
        "",
        "Read this report week-over-week to track whether the dev branch's",
        "improvements (new gates, lexicon, transcript coverage check, etc.)",
        "are producing a meaningfully different pipeline verdict than prod.",
        "",
        "---",
        "",
    ]

    # CEO verdict
    p = summarize_ceo_verdict(load_json_ref(main_ref, "data/ceo_grade_verdict.json"))
    d = summarize_ceo_verdict(load_json_ref(dev_ref,  "data/ceo_grade_verdict.json"))
    sections.append(render_kv_table(p, d, "CEO-grade verdict"))

    # Validator
    p = summarize_validator(load_json_ref(main_ref, "data/validation_report.json"))
    d = summarize_validator(load_json_ref(dev_ref,  "data/validation_report.json"))
    sections.append(render_kv_table(p, d, "Validator (10-pass)"))

    # Editorial
    p = summarize_editorial(load_json_ref(main_ref, "data/editorial_report.json"))
    d = summarize_editorial(load_json_ref(dev_ref,  "data/editorial_report.json"))
    sections.append(render_kv_table(p, d, "Editorial review"))

    # Signals
    p = summarize_signals(load_json_ref(main_ref, "data/signals.json"))
    d = summarize_signals(load_json_ref(dev_ref,  "data/signals.json"))
    sections.append(render_kv_table(p, d, "Analyzer signals"))

    # Raw anchors
    p = summarize_raw_anchors(load_json_ref(main_ref, "data/raw_data.json"))
    d = summarize_raw_anchors(load_json_ref(dev_ref,  "data/raw_data.json"))
    sections.append(render_kv_table(p, d, "Raw data anchors (latest values)"))

    # Interpretation guide
    sections.extend([
        "---",
        "",
        "## Reading this report",
        "",
        "- **CEO-grade verdict row** is the single most important: if prod is",
        "  `PASS` and dev is `FAIL`, the dev branch is introducing a regression",
        "  that prod's gate doesn't catch yet — investigate before merge.",
        "- **Validator critical/warning counts**: dev should typically have",
        "  ≥ prod count, because dev's new gates (`transcript_archive_coverage`,",
        "  strict-mode-on-cron) surface findings prod doesn't.",
        "- **Editorial criticals**: should converge — both pipelines run the",
        "  same `_editorial_review.py`. A divergence means the underlying",
        "  commentary differs (different Agent 3 outputs).",
        "- **Signal flag counts**: same input data → same flags. Drift here",
        "  means one of the pipelines saw different upstream data (rare;",
        "  happens when one ran an hour before a fresh BLS print).",
        "- **Raw data anchors**: should be near-identical. Large gaps mean",
        "  one branch ran during an API hiccup; small gaps are normal hourly",
        "  drift if the runs were staggered.",
        "",
        "## Decision criteria after 2 weeks of parallel run",
        "",
        "1. **Promote dev → main** if: 2 consecutive weeks with verdict",
        "   `PASS` or `WARN`, no signals diverging on the same data, and",
        "   dev's new gates fired correctly (transcript coverage flagged",
        "   when expected; annotation-lexicon check stayed green).",
        "2. **Extend parallel run** if: any week shows `FAIL` on dev, or",
        "   the comparison surfaces an unexpected behavioural difference.",
        "3. **Roll back dev work** if: dev introduces a regression prod",
        "   doesn't have and the root cause requires a fundamental",
        "   redesign rather than a patch.",
    ])

    return "\n".join(sections)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main-ref", default="main")
    ap.add_argument("--dev-ref", default="dev/multi-expert-improvements")
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    # Verify both refs are reachable
    for ref in (args.main_ref, args.dev_ref):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"❌ Cannot resolve git ref: {ref}", file=sys.stderr)
            return 1

    # At minimum we need raw_data.json or validation_report.json on each side,
    # otherwise the comparison is empty
    main_has_artifacts = any(
        git_show(args.main_ref, p) is not None for p, _ in ARTIFACTS
    )
    dev_has_artifacts = any(
        git_show(args.dev_ref, p) is not None for p, _ in ARTIFACTS
    )
    if not (main_has_artifacts and dev_has_artifacts):
        print(
            f"❌ Neither {args.main_ref} nor {args.dev_ref} carries any of "
            f"the expected artifacts {[a[0] for a in ARTIFACTS]}",
            file=sys.stderr,
        )
        return 2

    report = build_report(args.main_ref, args.dev_ref)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated_path = out_dir / f"parallel_compare_{today}.md"
    latest_path = out_dir / "parallel_compare_latest.md"

    dated_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")

    print(f"✅ Wrote {dated_path}")
    print(f"✅ Wrote {latest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
