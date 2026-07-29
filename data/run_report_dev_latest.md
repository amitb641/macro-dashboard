# Pipeline run report: `dev`

_Generated 2026-07-29 04:52 UTC._

- **Branch:** `dev`
- **Ref:** `dev/multi-expert-improvements`
- **Commit:** `825a5c5516bf` — Fix parallel-compare.yml: run-report push had no retry, failed outright on race
- **Deploy surface:** Vercel

Single-branch snapshot — emitted on every briefing completion so
we get a per-run record even when the counterpart branch hasn't
fired yet. The paired diff (when both branches are fresh) is in
`data/parallel_compare_latest.md`.

---

## Headline

- **CEO-grade verdict:** **—**
- **Validator:** 665 passed / 0 failed / 0 critical
- **Editorial:** 0 critical, 0 warning
- **Signals:** risk=ELEVATED, alerts=2, watch=3

## Findings that need attention

_None at critical severity._

---

## Detail

### CEO-grade verdict

| Metric | Value |
|---|---|
| verdict | — |
| strict_mode | — |
| layer_count | 5 |
| layers | validator=PASS, visual_qa=PASS, vision_review=PASS, editorial=PASS, repair_incident=PASS |
| reasons | (none) |

### Validator (10-pass)

| Metric | Value |
|---|---|
| status | PASS |
| total_checks | 665 |
| passed | 665 |
| failed | 0 |
| skipped | 1 |
| critical_divergences | 0 |

### Editorial review

| Metric | Value |
|---|---|
| total_findings | 0 |
| critical | 0 |
| warning | 0 |
| info | 0 |

### Analyzer signals

| Metric | Value |
|---|---|
| risk_level | ELEVATED |
| alert_count | 2 |
| watch_count | 3 |
| flagged_count | 7 |
| total_signals | 0 |

### Raw data anchors (latest values)

| Metric | Value |
|---|---|
| Core CPI YoY | — |
| UMich Sentiment | 69.7 |
| Personal Saving Rate | — |
| Fed Funds Rate | 3.63 |
| WTI Crude | — |
| 10Y Treasury | 4.65 |
| Unemployment Rate | 7.0 |

---

## What to do with this report

- **Dev branch run** → committed to `data/run_report_dev_latest.md`
  on every fire. If the verdict is `FAIL` or a finding here is new
  vs the previous week, leave a note in `.claude/PARALLEL_RUN.md` log.
- **Prod branch run** → uploaded as a workflow artifact only (not
  committed) so the bot never pushes to main.
- **Paired runs** (both branches fresh in 24h) → additionally see
  `data/parallel_compare_latest.md` for the side-by-side diff.