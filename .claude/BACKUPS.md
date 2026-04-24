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

### `backup/pre-agent-9` — commit `cf1573e` (2026-04-24)

**Captured state** — main immediately before Agent 9 (autonomous earnings
agent) landed. Tier 2 + Tier 4 of the earnings refactor are included
(bank_earnings.json, validator Pass 3c), but:

- `scripts/earnings_agent.py` does NOT exist.
- `.github/workflows/earnings_agent.yml` does NOT exist.
- `data/earnings_calendar.json` does NOT exist.
- Dashboard still reads "8 agents" / "5-pass validator".
- Quarterly earnings updates are still manual: human edits
  `data/bank_earnings.json` + drops transcript into
  `data/transcripts/<Q>/<TICKER>.txt`, then renderer + validator
  locally before commit.

**Why preserved**: restore point if Agent 9 misbehaves in production
(e.g. fetches the wrong transcript, Claude's extraction loops, or the
daily cron conflicts with the weekly briefing pipeline). Since Agent 9
runs on its own workflow, disabling it in the GitHub UI is usually
sufficient — this branch is for the rare case where the validator or
renderer changes it carries need to be reverted too.

**Smoke test at baseline**: 24/25 pass locally (1 pre-existing Playwright
failure, unchanged through all recent work).

**Rollback**:
```bash
# Disable Agent 9 workflow only (preferred — preserves the validator gate)
# via GitHub UI: Actions → Agent 9 — Earnings Agent → ⋯ → Disable workflow

# Or revert the Agent 9 commit while keeping everything else
git checkout main
git revert <agent-9-sha>
git push origin main

# Or hard-rollback to pre-Agent-9 state
git checkout main
git reset --hard backup/pre-agent-9
git push --force-with-lease origin main
```

---

### `backup/pre-earnings-refactor-2026-04-24` — commit `9c7c6ea` (2026-04-24)

**Captured state** — main at CI Weekly Update 2026-04-24, immediately before the
earnings commentary structural refactor lands.

- `BANK_COMMENTARY` is still a 101-line multi-line JS literal embedded in
  `index.html` (lines ~3544–3645). Every bank card's quote/economy/lending/
  cards_loans/macro/tech_ai/credit/outlook is hand-edited directly in HTML.
- Validator is 5-pass (no earnings factuality gate). Paraphrased quotes and
  fabricated figures can ship undetected — exactly the failure mode found in
  Q1 2026 and corrected in commits `1763dff` and `efcfe79`.
- `data/bank_earnings.json` does NOT exist.
- `data/transcripts/` does NOT exist.
- CLAUDE.md's Earnings Commentary Factuality Rule is present (added in
  `43c3a62`) but enforcement is manual/review-only.

**Why preserved**: restore point in case the data-driven refactor
(`d7edd0a` onward) introduces a regression in how bank cards render, the
validator blocks a legitimate weekly update, or we need to revert to the
hand-edit flow for an emergency update.

**Smoke test at baseline**: 24/25 pass locally (1 pre-existing Playwright
failure, unchanged).

**Rollback** (if the refactor has a latent bug we can't fix forward):
```bash
# Safe — preserves history with revert commits
git checkout main
git revert --no-commit 9c7c6ea..HEAD
git commit -m "Revert to backup/pre-earnings-refactor-2026-04-24 baseline"
git push origin main

# Or hard — faster but rewrites history
git checkout main
git reset --hard backup/pre-earnings-refactor-2026-04-24
git push --force-with-lease origin main
```

---

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
