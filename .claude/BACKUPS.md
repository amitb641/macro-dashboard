# Macro Dashboard — Rollback Registry

Dedicated registry of known-good baselines for this repo. Each entry is a
remote branch at a specific commit SHA, preserved before a multi-commit
refactor so we can recover cleanly if a direction doesn't pan out.

Convention:
- Branch name: `backup/<version-tag>`
- Push the branch before starting the refactor (tags are sometimes blocked
  by the dev git proxy; branches go through)
- Never rebase or force-push these branches
- Keep at least the last 3 baselines; archive older ones by prefixing
  `archive/backup/...`

Rollback commands:
```bash
# Inspect what's in a baseline
git show <sha> --stat
git log backup/<tag> -10

# Hard rollback main (irreversible — only if you're sure)
git checkout main
git reset --hard backup/<tag>
git push --force-with-lease origin main

# Safe rollback via revert commits (keeps history)
git checkout main
git revert --no-commit <sha>..HEAD
git commit -m "Revert to backup/<tag> baseline"
git push origin main

# Explore from a rescue branch without touching main
git checkout -b rescue backup/<tag>
```

---

## Baselines

### `backup/v1.0-shock-tracker-complete` — commit `e433997` (2026-04-20)

**Captured state** — full shock tracker rebuild + data validation rigor pass:

- UMich Consumer Sentiment pulled direct from `sca.isr.umich.edu/files/tbcics.csv`
  with preliminary / final `status` field; KPI badge + chart bar color reflect
  release status; validator emits informational finding when latest is prelim.
- Oil Impact Chain (SHOCK_TRACKER) auto-updates on every render — regex bug
  in `update_shock_tracker` fixed; confirmation logic switched from YoY (which
  was base-effect contaminated) to signed MMA comparison: latest post-shock
  single-month annualized vs pre-shock 6-month compound annualized, confirm at
  +1.5pp, emerging at +0.5pp.
- Every phase dict carries: `status_reason`, `detail` (math inputs),
  `commentary` (macro color), `source` (FRED series ID + cadence), optional
  `base_effect_note` (auto-emitted when YoY > MMA by a material margin).
- Rich click-to-open popover on each status badge / ⓘ icon with header, why,
  pre-vs-post MMA card, base-effect callout, underlying data, commentary, source.
- Agent 6 (validator) Pass 3b: `check_shock_tracker()` validates structure,
  required fields, MMA-delta vs status consistency. Critical finding if const
  is unparseable (prevents silent regex regression).
- Agent 7 (visual QA): DOM text check counts 8 phase titles + distinct status
  labels rendered in `#tab-oil`.
- `TREASURY_DATA.card90` line wired from `cc_delinq` (DRCCLACBS, collector
  fetches 108 obs = ~27 yrs); 27/27 filled back to 2000.
- Staleness thresholds calibrated to actual BLS / Case-Shiller release
  cadences (unrate/payems 55d, cs_hpi 120d).
- `SPARSE_OK` overrides for forecast-only / annotation fields (`FFR_DATA.dots`,
  `OIL_DAILY.notes`) in both validator and visual QA, kept in sync.
- Chart.js v4 post-destroy guard on the daily-oil annotation setTimeout
  callback (was throwing `getDatasetMeta is not a function` after re-mounts).

**Why preserved**: last verified state before the industry-grade roadmap —
METHODOLOGY.md + backtest harness, JSON-blob data pattern refactor, ALFRED
vintage pinning for historical charts. Those changes touch many files and
may need to be revisited.

**Smoke test at baseline**: 24/25 pass locally (the 1 failure is Playwright
in the sandbox, passes in CI). Validator: 388/395 pass, 0 critical.

**Rollback**:
```bash
git reset --hard backup/v1.0-shock-tracker-complete
git push --force-with-lease origin main
```
