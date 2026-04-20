# Macro Dashboard — Rollback Anchors

Dedicated registry of known-good baselines preserved as remote branches for
recovery. Use this as the source of truth for "what was working before X?"

## Convention
- Before any multi-commit refactor, create `backup/<tag>` at current HEAD and push it.
- Git tag pushes are sometimes blocked by the dev proxy — branches work reliably.
- Rollback: `git reset --hard backup/<tag>` then `git push --force-with-lease origin main`.
- Safer: `git revert <range>` on a fresh branch, PR it.

## Baselines

### `backup/v1.0-shock-tracker-complete` → commit `e433997` (2026-04-20)
**What this snapshot captures**:
- UMich Consumer Sentiment direct source (`sca.isr.umich.edu/files/tbcics.csv`)
  with prelim/final badge on KPI + chart
- Oil Impact Chain rewrite:
  - Regex fix for `update_shock_tracker` (single-line JSON match)
  - MMA-based confirmation (signed post-shock MoM ann. vs pre-shock 6-MMA)
  - Per-phase `status_reason`, `detail`, `commentary`, `source`, `base_effect_note`
  - Rich click-to-open popover (header, why, MMA comparison, base-effect
    callout, math, what's happening, source)
- Agent 6 (validator) Pass 3b: SHOCK_TRACKER structural + MMA consistency
- Agent 7 (visual QA): DOM-based SHOCK_TRACKER check
- `TREASURY_DATA.card90` wired from `cc_delinq` (108-obs DRCCLACBS, filled back to 2000)
- Staleness thresholds calibrated to actual BLS/BEA release cadences
- `SPARSE_OK` overrides for forecast-only fields (FFR dot plot, oil notes)
- Chart.js v4 post-destroy guard on daily oil annotation callback

**State when tagged**: 388/395 validator checks passing. Remaining 7 are
cosmetic (info-level PRELIM notice) or real-but-non-blocking (BLS release
lag within calibrated windows).

**Last verified before**: industry-grade roadmap kick-off (METHODOLOGY.md,
backtest harness, JSON-blob refactor, ALFRED vintage pinning).

**Rollback**:
```bash
git checkout main
git reset --hard backup/v1.0-shock-tracker-complete
git push --force-with-lease origin main
```

**Inspect without rollback**:
```bash
git show e433997 --stat
git diff HEAD..backup/v1.0-shock-tracker-complete --stat
```
