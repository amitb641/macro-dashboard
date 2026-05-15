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

# Findings ledger — best-effort import so an older repo missing the
# module still produces a comparison report.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _findings_ledger as _ledger  # type: ignore
except Exception:  # pragma: no cover
    _ledger = None  # type: ignore

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


# ───────────────────────────────────────────────────────────────────────────
# Divergence detection — produces stable-titled findings the ledger can
# fingerprint and deduplicate across runs.
#
# Tolerances chosen to filter noise without hiding real regressions:
# - ANCHOR_REL_TOL — 0.5% relative drift is normal for staggered fetches
#   (FRED/BLS update hourly; the two pipelines run minutes apart). Beyond
#   that, the branches saw different underlying data.
# - COUNT_DELTA — small int deltas in alert/watch counts are normal jitter;
#   any delta on critical counts is reportable.
# ───────────────────────────────────────────────────────────────────────────
ANCHOR_REL_TOL = 0.005   # 0.5%
ANCHOR_ABS_TOL = 0.05    # absolute floor for near-zero values


def _is_number(x: Any) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _materially_different(a: Any, b: Any,
                          rel_tol: float = ANCHOR_REL_TOL,
                          abs_tol: float = ANCHOR_ABS_TOL) -> bool:
    """True iff two values differ enough to be reportable. Handles None,
    strings, and floats. Returns False for any pair where one side is '—'
    (missing) since that's an artifact-presence issue, not a divergence."""
    if a in (None, "—") or b in (None, "—"):
        return False
    if _is_number(a) and _is_number(b):
        af, bf = float(a), float(b)
        diff = abs(af - bf)
        scale = max(abs(af), abs(bf), 1.0)
        return diff > max(abs_tol, rel_tol * scale)
    return str(a) != str(b)


def detect_divergences(
    ceo_p: dict, ceo_d: dict,
    val_p: dict, val_d: dict,
    ed_p: dict, ed_d: dict,
    sig_p: dict, sig_d: dict,
    anc_p: dict, anc_d: dict,
) -> list[dict]:
    """Walk each summarised artifact and emit a list of divergence
    findings. Each finding has a stable `title` so re-occurrences across
    weeks land on the same ledger fingerprint.

    Returns list of {title, detail, severity}."""
    out: list[dict] = []

    # CEO-grade verdict mismatch — most important signal.
    vp, vd = str(ceo_p.get("verdict", "—")), str(ceo_d.get("verdict", "—"))
    if vp != vd and "—" not in (vp, vd):
        out.append({
            "title": "ceo_grade_verdict_divergence",
            "detail": f"prod={vp} dev={vd}",
            "severity": "critical" if "FAIL" in (vp, vd) else "warning",
        })

    # Validator critical-count divergence.
    cp, cd = val_p.get("critical_divergences"), val_d.get("critical_divergences")
    if _is_number(cp) and _is_number(cd) and int(cp) != int(cd):
        out.append({
            "title": "validator_critical_count_divergence",
            "detail": f"prod_criticals={cp} dev_criticals={cd}",
            "severity": "warning",
        })

    # Validator failed-count divergence beyond noise (>2).
    fp, fd = val_p.get("failed"), val_d.get("failed")
    if _is_number(fp) and _is_number(fd) and abs(int(fp) - int(fd)) > 2:
        out.append({
            "title": "validator_failed_count_divergence",
            "detail": f"prod_failed={fp} dev_failed={fd}",
            "severity": "warning",
        })

    # Editorial criticals: any delta is reportable.
    ep, ed_c = ed_p.get("critical", 0), ed_d.get("critical", 0)
    if _is_number(ep) and _is_number(ed_c) and int(ep) != int(ed_c):
        out.append({
            "title": "editorial_critical_count_divergence",
            "detail": f"prod_critical={ep} dev_critical={ed_c}",
            "severity": "warning",
        })

    # Signal-flag drift — same upstream data should give same flags.
    for key in ("alert_count", "watch_count", "flagged_count"):
        sp, sd = sig_p.get(key), sig_d.get(key)
        if _is_number(sp) and _is_number(sd) and int(sp) != int(sd):
            out.append({
                "title": f"signal_{key}_divergence",
                "detail": f"prod={sp} dev={sd}",
                "severity": "warning",
            })

    # Anchor metric divergence — beyond 0.5% relative tolerance only.
    for label, prod_val in anc_p.items():
        dev_val = anc_d.get(label, "—")
        if _materially_different(prod_val, dev_val):
            out.append({
                "title": f"anchor_divergence:{label.lower().replace(' ', '_')}",
                "detail": f"prod={prod_val} dev={dev_val}",
                "severity": "warning",
            })

    return out


def build_report(main_ref: str, dev_ref: str,
                 *, repo_root: Path | None = None) -> str:
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
    ceo_p = summarize_ceo_verdict(load_json_ref(main_ref, "data/ceo_grade_verdict.json"))
    ceo_d = summarize_ceo_verdict(load_json_ref(dev_ref,  "data/ceo_grade_verdict.json"))
    sections.append(render_kv_table(ceo_p, ceo_d, "CEO-grade verdict"))

    # Validator
    val_p = summarize_validator(load_json_ref(main_ref, "data/validation_report.json"))
    val_d = summarize_validator(load_json_ref(dev_ref,  "data/validation_report.json"))
    sections.append(render_kv_table(val_p, val_d, "Validator (10-pass)"))

    # Editorial
    ed_p = summarize_editorial(load_json_ref(main_ref, "data/editorial_report.json"))
    ed_d = summarize_editorial(load_json_ref(dev_ref,  "data/editorial_report.json"))
    sections.append(render_kv_table(ed_p, ed_d, "Editorial review"))

    # Signals
    sig_p = summarize_signals(load_json_ref(main_ref, "data/signals.json"))
    sig_d = summarize_signals(load_json_ref(dev_ref,  "data/signals.json"))
    sections.append(render_kv_table(sig_p, sig_d, "Analyzer signals"))

    # Raw anchors
    anc_p = summarize_raw_anchors(load_json_ref(main_ref, "data/raw_data.json"))
    anc_d = summarize_raw_anchors(load_json_ref(dev_ref,  "data/raw_data.json"))
    sections.append(render_kv_table(anc_p, anc_d, "Raw data anchors (latest values)"))

    # ── Divergences + recommended fixes ────────────────────────────
    divergences = detect_divergences(
        ceo_p, ceo_d, val_p, val_d, ed_p, ed_d, sig_p, sig_d, anc_p, anc_d
    )

    recorded: list[dict] = []
    if divergences and _ledger is not None and repo_root is not None:
        for f in divergences:
            try:
                entry = _ledger.record_finding(
                    repo_root,
                    source="parallel_compare",
                    severity=f.get("severity", "warning"),
                    title=f["title"],
                    detail=f.get("detail", ""),
                    branch="dev",  # divergences are observed on the dev side
                )
                recorded.append(entry)
            except Exception as e:  # pragma: no cover
                print(f"[ledger] record_finding failed: {e}", file=sys.stderr)

    if divergences:
        sections.append("## Divergences detected")
        sections.append("")
        for d_ in divergences:
            sev = d_.get("severity", "warning").upper()
            sections.append(
                f"- **[{sev}]** {d_['title']} — {d_.get('detail', '')}"
            )
        sections.append("")
    else:
        sections.append("## Divergences detected")
        sections.append("")
        sections.append("_None — pipelines produced equivalent outputs within tolerance._")
        sections.append("")

    if recorded:
        sections.append("## Recommended fixes")
        sections.append("")
        sections.append(
            "Looked up from `scripts/_findings_ledger.py` → `KNOWN_FIXES`. "
            "Full status tracking in `data/parallel_findings_ledger.md`."
        )
        sections.append("")
        seen_fp: set[str] = set()
        for entry in recorded:
            fp = entry.get("fingerprint", "")
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            sections.append(
                f"### {entry.get('title', '?')}  "
                f"_(seen {entry.get('occurrence_count', 1)}× · "
                f"status: {entry.get('status', 'open')})_"
            )
            sections.append("")
            sections.append(f"- **Detail:** {entry.get('detail', '—')}")
            sections.append(f"- **Fix:** {entry.get('recommended_fix', '—')}")
            sections.append(f"- **Fingerprint:** `{fp}`")
            sections.append("")

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

    repo_root = Path(__file__).resolve().parent.parent
    report = build_report(args.main_ref, args.dev_ref, repo_root=repo_root)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated_path = out_dir / f"parallel_compare_{today}.md"
    latest_path = out_dir / "parallel_compare_latest.md"

    dated_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")

    print(f"✅ Wrote {dated_path}")
    print(f"✅ Wrote {latest_path}")

    # Re-render ledger markdown after divergence findings recorded.
    if _ledger is not None:
        try:
            ledger_path = _ledger.write_markdown(repo_root)
            print(f"✅ Wrote {ledger_path}")
        except Exception as e:  # pragma: no cover
            print(f"[ledger] write_markdown failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
