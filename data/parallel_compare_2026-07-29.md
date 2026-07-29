# Parallel-run comparison: prod (main) vs dev

_Generated 2026-07-29 04:53 UTC._

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
| status | WARN | PASS | changed |
| total_checks | 520 | 665 | +145 |
| passed | 505 | 665 | +160 |
| failed | 15 | 0 | -15 |
| skipped | 2 | 1 | -1 |
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
| risk_level | HIGH | ELEVATED | changed |
| alert_count | 3 | 2 | -1 |
| watch_count | 2 | 3 | +1 |
| flagged_count | 1 | 7 | +6 |
| total_signals | 0 | 0 | 0 |

### Raw data anchors (latest values)

| Metric | Prod (main) | Dev (parallel) | Delta |
|---|---|---|---|
| Core CPI YoY | 2.74 | 2.57 | -0.17 |
| UMich Sentiment | 44.8 | 54.4 | +9.6 |
| Personal Saving Rate | 2.6 | 3.0 | +0.4 |
| Fed Funds Rate | 3.64 | 3.63 | -0.01 |
| WTI Crude | 112.25 | 84.38 | -27.9 |
| 10Y Treasury | 4.5 | 4.65 | +0.15 |
| Unemployment Rate | 4.3 | 4.2 | -0.1 |

## Divergences detected

- **[WARNING]** validator_failed_count_divergence — prod_failed=15 dev_failed=0
- **[WARNING]** signal_alert_count_divergence — prod=3 dev=2
- **[WARNING]** signal_watch_count_divergence — prod=2 dev=3
- **[WARNING]** signal_flagged_count_divergence — prod=1 dev=7
- **[WARNING]** anchor_divergence:core_cpi_yoy — prod=2.74 dev=2.57
- **[WARNING]** anchor_divergence:umich_sentiment — prod=44.8 dev=54.4
- **[WARNING]** anchor_divergence:personal_saving_rate — prod=2.6 dev=3.0
- **[WARNING]** anchor_divergence:wti_crude — prod=112.25 dev=84.38
- **[WARNING]** anchor_divergence:10y_treasury — prod=4.5 dev=4.65
- **[WARNING]** anchor_divergence:unemployment_rate — prod=4.3 dev=4.2

## Recommended fixes

Looked up from `scripts/_findings_ledger.py` → `KNOWN_FIXES`. Full status tracking in `data/parallel_findings_ledger.md`.

### validator_failed_count_divergence  _(seen 3× · status: open)_

- **Detail:** prod_failed=15 dev_failed=30
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:validator_failed_count_divergence:60c2262a6006`

### signal_alert_count_divergence  _(seen 1× · status: open)_

- **Detail:** prod=3 dev=2
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:signal_alert_count_divergence:edd2bcba36e4`

### signal_watch_count_divergence  _(seen 1× · status: open)_

- **Detail:** prod=2 dev=3
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:signal_watch_count_divergence:b918bb542d23`

### signal_flagged_count_divergence  _(seen 3× · status: open)_

- **Detail:** prod=0 dev=2
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:signal_flagged_count_divergence:01dbd0e3130d`

### anchor_divergence:core_cpi_yoy  _(seen 1× · status: open)_

- **Detail:** prod=2.74 dev=2.57
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:core_cpi_yoy:38591c741134`

### anchor_divergence:umich_sentiment  _(seen 1× · status: open)_

- **Detail:** prod=44.8 dev=54.4
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:umich_sentiment:f8aff802d1bc`

### anchor_divergence:personal_saving_rate  _(seen 1× · status: open)_

- **Detail:** prod=2.6 dev=3.0
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:personal_saving_rate:87ef992dd5e2`

### anchor_divergence:wti_crude  _(seen 1× · status: open)_

- **Detail:** prod=112.25 dev=84.38
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:wti_crude:9cca8df435e3`

### anchor_divergence:10y_treasury  _(seen 1× · status: open)_

- **Detail:** prod=4.5 dev=4.65
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:10y_treasury:4ba751b5d744`

### anchor_divergence:unemployment_rate  _(seen 1× · status: open)_

- **Detail:** prod=4.3 dev=4.2
- **Fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).
- **Fingerprint:** `parallel_compare:anchor_divergence:unemployment_rate:4f6315f71595`

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