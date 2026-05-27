# Parallel-run comparison: prod (main) vs dev

_Generated 2026-05-27 17:13 UTC._

- **Prod ref:** `main`
- **Dev ref:** `dev/multi-expert-improvements`

Read this report week-over-week to track whether the dev branch's
improvements (new gates, lexicon, transcript coverage check, etc.)
are producing a meaningfully different pipeline verdict than prod.

---

### CEO-grade verdict

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| verdict | — | — | — |
| reasons | (artifact missing) | (none) | changed |
| strict_mode | — | — | — |
| layer_count | — | 5 | — |

### Validator (10-pass)

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| status | WARN | WARN | same |
| total_checks | 521 | 633 | +112 |
| passed | 504 | 628 | +124 |
| failed | 17 | 5 | -12 |
| skipped | 1 | 14 | +13 |
| critical_divergences | 0 | 0 | 0 |

### Editorial review

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| summary | (artifact missing) | — | — |
| total_findings | — | 0 | — |
| critical | — | 0 | — |
| warning | — | 0 | — |
| info | — | 0 | — |

### Analyzer signals

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| risk_level | HIGH | HIGH | same |
| alert_count | 3 | 3 | 0 |
| watch_count | 2 | 2 | 0 |
| flagged_count | 0 | 1 | +1 |
| total_signals | 0 | 0 | 0 |

### Raw data anchors (latest values)

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| Core CPI YoY | — | — | — |
| UMich Sentiment | 61.3 | 61.3 | 0 |
| Personal Saving Rate | — | — | — |
| Fed Funds Rate | 3.64 | 3.64 | 0 |
| WTI Crude | — | — | — |
| 10Y Treasury | 4.56 | 4.56 | 0 |
| Unemployment Rate | 7.2 | 7.2 | 0 |

## Divergences detected

- **[WARNING]** validator_failed_count_divergence — prod_failed=17 dev_failed=5
- **[WARNING]** signal_flagged_count_divergence — prod=0 dev=1

## Recommended fixes

Looked up from `scripts/_findings_ledger.py` → `KNOWN_FIXES`. Full status tracking in `data/parallel_findings_ledger.md`.

### validator_failed_count_divergence  _(seen 3× · status: open)_

- **Detail:** prod_failed=15 dev_failed=30
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:validator_failed_count_divergence:60c2262a6006`

### signal_flagged_count_divergence  _(seen 3× · status: open)_

- **Detail:** prod=0 dev=2
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:signal_flagged_count_divergence:01dbd0e3130d`

---

## Reading this report

- **CEO-grade verdict row** is the single most important: if prod is
  `PASS` and dev is `FAIL`, the dev branch is introducing a regression
  that prod's gate doesn't catch yet — investigate before merge.
- **Validator critical/warning counts**: dev should typically have
  ≥ prod count, because dev's new gates (`transcript_archive_coverage`,
  strict-mode-on-cron) surface findings prod doesn't.
- **Editorial criticals**: should converge — both pipelines run the
  same `_editorial_review.py`. A divergence means the underlying
  commentary differs (different Agent 3 outputs).
- **Signal flag counts**: same input data → same flags. Drift here
  means one of the pipelines saw different upstream data (rare;
  happens when one ran an hour before a fresh BLS print).
- **Raw data anchors**: should be near-identical. Large gaps mean
  one branch ran during an API hiccup; small gaps are normal hourly
  drift if the runs were staggered.

## Decision criteria after 2 weeks of parallel run

1. **Promote dev → main** if: 2 consecutive weeks with verdict
   `PASS` or `WARN`, no signals diverging on the same data, and
   dev's new gates fired correctly (transcript coverage flagged
   when expected; annotation-lexicon check stayed green).
2. **Extend parallel run** if: any week shows `FAIL` on dev, or
   the comparison surfaces an unexpected behavioural difference.
3. **Roll back dev work** if: dev introduces a regression prod
   doesn't have and the root cause requires a fundamental
   redesign rather than a patch.