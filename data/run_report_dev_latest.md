# Pipeline run report: `dev`

_Generated 2026-05-14 22:18 UTC._

- **Branch:** `dev`
- **Ref:** `dev/multi-expert-improvements`
- **Commit:** `d5253a8a9294` — 🌑 Shadow update (dev): 2026-05-14
- **Deploy surface:** Vercel

Single-branch snapshot — emitted on every briefing completion so
we get a per-run record even when the counterpart branch hasn't
fired yet. The paired diff (when both branches are fresh) is in
`data/parallel_compare_latest.md`.

---

## Headline

- **CEO-grade verdict:** **—**
- **Validator:** 533 passed / 30 failed / 1 critical
- **Editorial:** 0 critical, 0 warning
- **Signals:** risk=HIGH, alerts=3, watch=1

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
| layers | validator=FAIL, visual_qa=WARN, vision_review=PASS, editorial=WARN, repair_incident=PASS |
| reasons | (none) |

### Validator (10-pass)

| Metric | Value |
|---|---|
| status | WARN |
| total_checks | 563 |
| passed | 533 |
| failed | 30 |
| skipped | 8 |
| critical_divergences | 1 |

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
| risk_level | HIGH |
| alert_count | 3 |
| watch_count | 1 |
| flagged_count | 2 |
| total_signals | 0 |

### Raw data anchors (latest values)

| Metric | Value |
|---|---|
| Core CPI YoY | — |
| UMich Sentiment | 63.8 |
| Personal Saving Rate | — |
| Fed Funds Rate | 3.64 |
| WTI Crude | — |
| 10Y Treasury | 4.46 |
| Unemployment Rate | 7.2 |

---

## What to do with this report

- **Dev branch run** → committed to `data/run_report_dev_latest.md`
  on every fire. If the verdict is `FAIL` or a finding here is new
  vs the previous week, leave a note in `.claude/PARALLEL_RUN.md` log.
- **Prod branch run** → uploaded as a workflow artifact only (not
  committed) so the bot never pushes to main.
- **Paired runs** (both branches fresh in 24h) → additionally see
  `data/parallel_compare_latest.md` for the side-by-side diff.