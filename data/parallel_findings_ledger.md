# Parallel-run findings ledger

_Generated 2026-07-29 04:53 UTC._

Every detected critical or warning during the parallel-run trial
is recorded here with a recommended fix. Status transitions are
manual — when a fix lands, edit the JSON or this file to set
`status: resolved` and fill `resolution_notes` + `resolution_commit`.

**Summary:** 12 open · 0 monitoring · 0 resolved

---

## Open

### `parallel_compare:validator_failed_count_divergence:60c2262a6006`

- **validator_failed_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 3
- **Detail:** prod_failed=15 dev_failed=30
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:signal_flagged_count_divergence:01dbd0e3130d`

- **signal_flagged_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 3
- **Detail:** prod=0 dev=2
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:signal_alert_count_divergence:edd2bcba36e4`

- **signal_alert_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=3 dev=2
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:signal_watch_count_divergence:b918bb542d23`

- **signal_watch_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=2 dev=3
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:core_cpi_yoy:38591c741134`

- **anchor_divergence:core_cpi_yoy** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=2.74 dev=2.57
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:umich_sentiment:f8aff802d1bc`

- **anchor_divergence:umich_sentiment** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=44.8 dev=54.4
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:personal_saving_rate:87ef992dd5e2`

- **anchor_divergence:personal_saving_rate** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=2.6 dev=3.0
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:wti_crude:9cca8df435e3`

- **anchor_divergence:wti_crude** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=112.25 dev=84.38
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:10y_treasury:4ba751b5d744`

- **anchor_divergence:10y_treasury** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=4.5 dev=4.65
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:anchor_divergence:unemployment_rate:4f6315f71595`

- **anchor_divergence:unemployment_rate** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-07-29T04:53:02Z · Last seen: 2026-07-29T04:53:02Z · Occurrences: 1
- **Detail:** prod=4.3 dev=4.2
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:validator_critical_count_divergence:cfa5fd800344`

- **validator_critical_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-05-15T04:33:07Z · Occurrences: 2
- **Detail:** prod_criticals=0 dev_criticals=1
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `validator:earnings_verbatim:transcript_archive_cov:87fb43e0cdb7`

- **earnings_verbatim:transcript_archive_coverage** (CRITICAL, source: `validator`)
- Branches: dev, HEAD
- First seen: 2026-05-15T03:59:44Z · Last seen: 2026-05-15T04:32:54Z · Occurrences: 3
- **Detail:** 
- **Recommended fix:** Archive the missing earnings transcripts under `data/transcripts/<Quarter>/<TICKER>.txt`. Validator Pass 3c (verbatim gate) requires the transcript text be present for every quoted span in `data/bank_earnings.json`. See CLAUDE.md → 'Update Workflow (Q2 2026 onward)' for the full flow.

---
