# Parallel-run findings ledger

_Generated 2026-05-15 04:33 UTC._

Every detected critical or warning during the parallel-run trial
is recorded here with a recommended fix. Status transitions are
manual — when a fix lands, edit the JSON or this file to set
`status: resolved` and fill `resolution_notes` + `resolution_commit`.

**Summary:** 4 open · 0 monitoring · 0 resolved

---

## Open

### `parallel_compare:validator_critical_count_divergence:cfa5fd800344`

- **validator_critical_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-05-15T04:33:07Z · Occurrences: 2
- **Detail:** prod_criticals=0 dev_criticals=1
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:validator_failed_count_divergence:60c2262a6006`

- **validator_failed_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-05-15T04:33:07Z · Occurrences: 2
- **Detail:** prod_failed=15 dev_failed=30
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `parallel_compare:signal_flagged_count_divergence:01dbd0e3130d`

- **signal_flagged_count_divergence** (WARNING, source: `parallel_compare`)
- Branches: dev
- First seen: 2026-05-15T04:02:45Z · Last seen: 2026-05-15T04:33:07Z · Occurrences: 2
- **Detail:** prod=0 dev=2
- **Recommended fix:** Dev and prod produced materially different outputs on the same upstream data. Capture the specific anchor metric or signal that diverged, screenshot both rendered pages, and decide: is dev's behaviour the desired one (then plan promotion to main) or a regression (then revert/fix on dev).

### `validator:earnings_verbatim:transcript_archive_cov:87fb43e0cdb7`

- **earnings_verbatim:transcript_archive_coverage** (CRITICAL, source: `validator`)
- Branches: dev, HEAD
- First seen: 2026-05-15T03:59:44Z · Last seen: 2026-05-15T04:32:54Z · Occurrences: 3
- **Detail:** 
- **Recommended fix:** Archive the missing earnings transcripts under `data/transcripts/<Quarter>/<TICKER>.txt`. Validator Pass 3c (verbatim gate) requires the transcript text be present for every quoted span in `data/bank_earnings.json`. See CLAUDE.md → 'Update Workflow (Q2 2026 onward)' for the full flow.

---
