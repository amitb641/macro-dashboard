"""
Single-branch per-run report.

Generates a markdown summary of one pipeline run — the validator pass
counts, CEO-grade verdict, editorial criticals, analyzer signal flags,
and the latest values of the anchor metrics. Fires after every briefing
completion (prod or dev), even when the counterpart branch hasn't run
yet, so the parallel-run trial gets a report on every workflow fire
rather than only on paired Saturdays.

Read-only: never modifies the source artifacts or index.html. Only
emits the report file.

Usage:
  # Default: read working-tree artifacts, infer branch from `git`
  python scripts/run_report.py

  # Explicit ref + branch label
  python scripts/run_report.py --ref HEAD --branch dev
  python scripts/run_report.py --ref main --branch main

Exit codes:
  0 — report generated
  1 — git ref unresolvable
  2 — no expected artifacts present on the ref
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Findings ledger — recorded once per per-run report, surfaces a
# "Recommended Fixes" section with stable fingerprints + KB lookup.
# Lives next to this file; import is best-effort so older callers still
# work if the module hasn't landed yet.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _findings_ledger as _ledger  # type: ignore
except Exception:  # pragma: no cover - defensive
    _ledger = None  # type: ignore

# ───────────────────────────────────────────────────────────────────────────
# Artifacts surfaced in the per-run report. Order = report order.
# ───────────────────────────────────────────────────────────────────────────
ARTIFACTS = [
    ("data/ceo_grade_verdict.json", "CEO-grade verdict"),
    ("data/validation_report.json", "Validator"),
    ("data/editorial_report.json", "Editorial"),
    ("data/signals.json", "Signals"),
    ("data/raw_data.json", "Raw data (anchors)"),
]

# Anchors pulled from raw_data.json. Keep in lock-step with
# parallel_compare.py so the two reports use the same vocabulary.
RAW_ANCHORS = [
    ("core_cpi_yoy", "Core CPI YoY"),
    ("umcsent", "UMich Sentiment"),
    ("saving_rate", "Personal Saving Rate"),
    ("ffr", "Fed Funds Rate"),
    ("oil_wti", "WTI Crude"),
    ("dgs10", "10Y Treasury"),
    ("unrate", "Unemployment Rate"),
]


def _latest_value(obj: Any) -> Any:
    """Extract latest observation from FRED-shaped list or scalar."""
    if isinstance(obj, list) and obj:
        last = obj[-1]
        if isinstance(last, dict):
            return last.get("value", last)
        return last
    if isinstance(obj, dict):
        return obj.get("value", obj)
    return obj


def git_show(ref: str, path: str) -> str | None:
    """Return file contents at `ref` or None if missing/unreachable."""
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
    """Load JSON from a git ref. None on miss / parse error."""
    raw = git_show(ref, path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[load_json] {ref}:{path} not valid JSON: {e}", file=sys.stderr)
        return None


# ───────────────────────────────────────────────────────────────────────────
# Per-artifact summarisers. Defensive against missing keys.
# ───────────────────────────────────────────────────────────────────────────

def summarize_ceo_verdict(payload: dict | None) -> dict:
    if not payload:
        return {"verdict": "—", "reasons": "(artifact missing)"}
    layers = payload.get("layers", {})
    layer_summary = "—"
    if isinstance(layers, dict):
        per_layer = []
        for name, body in layers.items():
            if isinstance(body, dict):
                per_layer.append(f"{name}={body.get('status', '?')}")
            else:
                per_layer.append(f"{name}=?")
        layer_summary = ", ".join(per_layer) if per_layer else "—"
    return {
        "verdict": payload.get("verdict", "—"),
        "strict_mode": payload.get("strict_mode", "—"),
        "layer_count": len(layers) if isinstance(layers, dict) else "—",
        "layers": layer_summary,
        "reasons": "; ".join(payload.get("reasons", []))[:240] or "(none)",
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
    signals_list = payload.get("signals", []) if isinstance(payload.get("signals"), list) else []
    return {
        "risk_level": payload.get("risk_level", "—"),
        "alert_count": payload.get("alert_count", "—"),
        "watch_count": payload.get("watch_count", "—"),
        "flagged_count": payload.get("flagged_count", "—"),
        "total_signals": len(signals_list),
    }


def summarize_raw_anchors(payload: dict | None) -> dict:
    """Pull latest value of each anchor metric.

    raw_data.json structure: {"collected_at": ..., "data": {key: [...]}}.
    """
    if not payload or not isinstance(payload, dict):
        return {a[1]: "—" for a in RAW_ANCHORS}
    series = payload.get("data", payload)
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
# Critical-finding extraction (so the report leads with what needs review).
# ───────────────────────────────────────────────────────────────────────────

def extract_validator_criticals(payload: dict | None) -> list[dict]:
    """Return validator findings that are critical-and-failed, as
    {title, detail, severity} dicts.

    Validator schema: top-level dict keyed by pass name (e.g.
    `internal_consistency`, `cross_source`, `visual_qa`), each value a
    list of `{check, severity, pass, ...}` items. Critical failures are
    items where `pass is False` AND `severity == "critical"`.
    """
    if not payload:
        return []
    out: list[dict] = []
    SKIP_TOP_KEYS = {"validated_at", "status", "summary"}
    for pass_name, items in payload.items():
        if pass_name in SKIP_TOP_KEYS:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            sev = (it.get("severity") or "").lower()
            passed = it.get("pass")
            # `pass` is the canonical bool; treat missing as "no info, skip"
            if passed is True or passed is None:
                continue
            if sev != "critical":
                continue
            check = it.get("check") or it.get("name") or "(unnamed)"
            # Detail field varies by pass type; concatenate the
            # diagnostic fields that exist.
            detail_bits = []
            for k in ("note", "detail", "message", "metric",
                      "difference", "diff", "html_value", "source_value",
                      "age_days", "max_lag_days"):
                if k in it and it[k] not in (None, ""):
                    detail_bits.append(f"{k}={it[k]}")
            detail = "; ".join(detail_bits)[:240]
            out.append({
                "title": f"{pass_name}:{check}",
                "detail": detail,
                "severity": "critical",
            })
    return out[:10]  # cap to keep report readable


def extract_editorial_criticals(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    findings = payload.get("findings", payload.get("results", []))
    if not isinstance(findings, list):
        return []
    out: list[dict] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        if (f.get("severity") or "").lower() == "critical":
            target = f.get("target") or f.get("piece") or f.get("tab") or "(unknown piece)"
            msg = f.get("message") or f.get("detail") or ""
            out.append({
                "title": f"editorial:{target}",
                "detail": str(msg)[:240],
                "severity": "critical",
            })
    return out[:10]


def _fmt_finding(f: dict) -> str:
    """Render one finding as a bullet line for the 'needs attention' section."""
    if f.get("detail"):
        return f"{f['title']} — {f['detail'][:140]}"
    return f["title"]


# ───────────────────────────────────────────────────────────────────────────
# Rendering
# ───────────────────────────────────────────────────────────────────────────

def render_kv(d: dict, title: str) -> str:
    lines = [f"### {title}", "", "| Metric | Value |", "|---|---|"]
    for k, v in d.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    return "\n".join(lines)


def build_report(ref: str, branch: str, commit_sha: str, commit_msg: str,
                 *, repo_root: Path | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    surface = "GitHub Pages" if branch == "main" else "Vercel"
    sections: list[str] = [
        f"# Pipeline run report: `{branch}`",
        "",
        f"_Generated {now}._",
        "",
        f"- **Branch:** `{branch}`",
        f"- **Ref:** `{ref}`",
        f"- **Commit:** `{commit_sha[:12]}` — {commit_msg}",
        f"- **Deploy surface:** {surface}",
        "",
        "Single-branch snapshot — emitted on every briefing completion so",
        "we get a per-run record even when the counterpart branch hasn't",
        "fired yet. The paired diff (when both branches are fresh) is in",
        "`data/parallel_compare_latest.md`.",
        "",
        "---",
        "",
    ]

    ceo = summarize_ceo_verdict(load_json_ref(ref, "data/ceo_grade_verdict.json"))
    val_payload = load_json_ref(ref, "data/validation_report.json")
    val = summarize_validator(val_payload)
    ed_payload = load_json_ref(ref, "data/editorial_report.json")
    ed = summarize_editorial(ed_payload)
    sig = summarize_signals(load_json_ref(ref, "data/signals.json"))
    anchors = summarize_raw_anchors(load_json_ref(ref, "data/raw_data.json"))

    # Headline: verdict + most damning numbers up top so reviewers don't
    # have to scroll. Glanceable.
    headline = [
        "## Headline",
        "",
        f"- **CEO-grade verdict:** **{ceo['verdict']}**"
        + (f" (strict={ceo['strict_mode']})" if ceo.get("strict_mode") not in ("—", None) else ""),
        f"- **Validator:** {val.get('passed', '—')} passed / "
        f"{val.get('failed', '—')} failed / "
        f"{val.get('critical_divergences', '—')} critical",
        f"- **Editorial:** {ed.get('critical', 0)} critical, "
        f"{ed.get('warning', 0)} warning",
        f"- **Signals:** risk={sig.get('risk_level', '—')}, "
        f"alerts={sig.get('alert_count', '—')}, "
        f"watch={sig.get('watch_count', '—')}",
        "",
    ]
    sections.extend(headline)

    # Criticals — pulled to the top so they're impossible to miss
    val_crits = extract_validator_criticals(val_payload)
    ed_crits = extract_editorial_criticals(ed_payload)

    # Record into ledger so recurring findings accumulate occurrence count
    # and the markdown ledger stays current. Best-effort: a ledger failure
    # never aborts report generation.
    recorded: list[dict] = []
    if _ledger is not None and repo_root is not None:
        for f in val_crits:
            try:
                entry = _ledger.record_finding(
                    repo_root,
                    source="validator",
                    severity=f.get("severity", "critical"),
                    title=f["title"],
                    detail=f.get("detail", ""),
                    branch=branch,
                )
                recorded.append(entry)
            except Exception as e:  # pragma: no cover
                print(f"[ledger] record_finding failed: {e}", file=sys.stderr)
        for f in ed_crits:
            try:
                entry = _ledger.record_finding(
                    repo_root,
                    source="editorial",
                    severity="critical",
                    title=f["title"],
                    detail=f.get("detail", ""),
                    branch=branch,
                )
                recorded.append(entry)
            except Exception as e:  # pragma: no cover
                print(f"[ledger] record_finding failed: {e}", file=sys.stderr)
        # CEO-grade FAIL — record as its own finding so the ledger surfaces
        # the aggregate verdict alongside the layer-level findings.
        if str(ceo.get("verdict", "")).upper() == "FAIL":
            try:
                entry = _ledger.record_finding(
                    repo_root,
                    source="ceo_grade",
                    severity="critical",
                    title="ceo_grade_fail",
                    detail=ceo.get("reasons", "")[:240],
                    branch=branch,
                )
                recorded.append(entry)
            except Exception as e:  # pragma: no cover
                print(f"[ledger] record_finding failed: {e}", file=sys.stderr)

    if val_crits or ed_crits:
        sections.append("## Findings that need attention")
        sections.append("")
        if val_crits:
            sections.append("**Validator criticals:**")
            sections.append("")
            for c in val_crits:
                sections.append(f"- {_fmt_finding(c)}")
            sections.append("")
        if ed_crits:
            sections.append("**Editorial criticals:**")
            sections.append("")
            for c in ed_crits:
                sections.append(f"- {_fmt_finding(c)}")
            sections.append("")
    else:
        sections.append("## Findings that need attention")
        sections.append("")
        sections.append("_None at critical severity._")
        sections.append("")

    # Recommended fixes — paired with each finding above. Deduplicated by
    # fingerprint so a single fix never appears twice in one report.
    if recorded:
        sections.append("## Recommended fixes")
        sections.append("")
        sections.append(
            "Looked up from `scripts/_findings_ledger.py` → `KNOWN_FIXES`. "
            "Status tracking and resolution notes live in "
            "`data/parallel_findings_ledger.md` (open / monitoring / resolved)."
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
            sections.append(
                f"- **Detail:** {entry.get('detail', '—')}"
            )
            sections.append(
                f"- **Fix:** {entry.get('recommended_fix', '—')}"
            )
            sections.append(
                f"- **Fingerprint:** `{fp}`"
            )
            sections.append("")

    sections.append("---")
    sections.append("")
    sections.append("## Detail")
    sections.append("")

    sections.append(render_kv(ceo, "CEO-grade verdict"))
    sections.append(render_kv(val, "Validator (10-pass)"))
    sections.append(render_kv(ed, "Editorial review"))
    sections.append(render_kv(sig, "Analyzer signals"))
    sections.append(render_kv(anchors, "Raw data anchors (latest values)"))

    sections.extend([
        "---",
        "",
        "## What to do with this report",
        "",
        "- **Dev branch run** → committed to `data/run_report_dev_latest.md`",
        "  on every fire. If the verdict is `FAIL` or a finding here is new",
        "  vs the previous week, leave a note in `.claude/PARALLEL_RUN.md` log.",
        "- **Prod branch run** → uploaded as a workflow artifact only (not",
        "  committed) so the bot never pushes to main.",
        "- **Paired runs** (both branches fresh in 24h) → additionally see",
        "  `data/parallel_compare_latest.md` for the side-by-side diff.",
    ])

    return "\n".join(sections)


def resolve_commit(ref: str) -> tuple[str, str]:
    """Return (sha, subject) for the ref. Best-effort; empties on failure."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", ref],
            capture_output=True, text=True, check=False, encoding="utf-8",
        ).stdout.strip()
        msg = subprocess.run(
            ["git", "log", "-1", "--format=%s", ref],
            capture_output=True, text=True, check=False, encoding="utf-8",
        ).stdout.strip()
        return sha, msg
    except Exception:
        return "", ""


def infer_branch_label() -> str:
    """Guess branch label from `git rev-parse --abbrev-ref HEAD`. Maps the
    long dev branch name down to a short token so file names stay sane."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=False, encoding="utf-8",
        )
        name = r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"
    if name == "main":
        return "main"
    if name.startswith("dev"):
        return "dev"
    return name.replace("/", "_")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="HEAD",
                    help="Git ref to read artifacts from (default: HEAD)")
    ap.add_argument("--branch", default=None,
                    help="Branch label for the filename (default: inferred from HEAD)")
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    # Verify ref resolves
    result = subprocess.run(
        ["git", "rev-parse", "--verify", args.ref],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"❌ Cannot resolve git ref: {args.ref}", file=sys.stderr)
        return 1

    # Need at least one expected artifact on the ref
    has_any = any(git_show(args.ref, p) is not None for p, _ in ARTIFACTS)
    if not has_any:
        print(
            f"❌ {args.ref} carries none of the expected artifacts "
            f"{[a[0] for a in ARTIFACTS]}",
            file=sys.stderr,
        )
        return 2

    branch = args.branch or infer_branch_label()
    sha, msg = resolve_commit(args.ref)

    # Repo root for the ledger; up one from scripts/.
    repo_root = Path(__file__).resolve().parent.parent

    report = build_report(args.ref, branch, sha, msg, repo_root=repo_root)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated = out_dir / f"run_report_{branch}_{today}.md"
    latest = out_dir / f"run_report_{branch}_latest.md"

    dated.write_text(report, encoding="utf-8")
    latest.write_text(report, encoding="utf-8")

    print(f"✅ Wrote {dated}")
    print(f"✅ Wrote {latest}")

    # Re-render the ledger markdown so the human-readable view reflects
    # what was just recorded. Best-effort — never abort the run report.
    if _ledger is not None:
        try:
            ledger_path = _ledger.write_markdown(repo_root)
            print(f"✅ Wrote {ledger_path}")
        except Exception as e:  # pragma: no cover
            print(f"[ledger] write_markdown failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
