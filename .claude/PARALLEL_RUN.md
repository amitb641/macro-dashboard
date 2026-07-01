# Parallel Run: prod (main) vs dev/multi-expert-improvements

> **Start date:** 2026-05-14
> **Planned merge-decision date:** ~~2026-06-14~~ **INDEFINITE (per user
> directive 2026-05-23)**
> **Status:** Active — observation mode, **no scheduled promotion**

## ⚠️ Active policy (2026-05-23 — durable across sessions)

The user explicitly directed: **"keep the dev dashboard independent
from main"** and **"we're going to run dev dashboard indefinitely
separate until further notice."**

What this means for any Claude session resuming this trial:

- **Do NOT** cherry-pick, merge, or rebase any `dev/multi-expert-improvements`
  commit into `main` without an explicit, in-session user instruction
  authorizing the specific change.
- The original T+1 month merge-decision date (2026-06-14) is **paused**.
  Treat the trial window as open-ended.
- Visual + editorial enhancements (typography, reading bar, delta block,
  print stylesheet, skeleton states, color-blind alt, vintage badges,
  sparklines, footnote ladder, etc.) all land on **dev only**.
- The Vercel preview at `macro-dashboard-dev.vercel.app` is the dev
  surface; `main` continues to serve the conservative production page.
- If a bug fix is genuinely critical and needs to land on `main`, ask
  the user before pushing — do not autopilot.

Promotion criteria, if/when the user re-opens the question: still
gated on smoke 29/29, validator 208/208, visual_qa static-check sweep
4/4, plus ≥4 consecutive Saturday cycles of clean dev runs.

This document tracks the parallel-run trial of the
`dev/multi-expert-improvements` branch against production (`main`).
Both branches now operate independent, parallel CI pipelines against
the same upstream data sources (FRED / BLS / EIA / Anthropic /
Resend). Neither inherits state from the other.

---

## Plan + state snapshot (2026-05-14)

> Durable memory for future Claude sessions resuming this trial. Update
> whenever the plan changes; do not delete past entries.

**Goal:** observe dev's expert-bundle changes against fresh live data
for ≥4 weekly cycles, then decide promote / extend / roll-back.

**Architecture (already landed):**

- `main` branch → prod pipeline (`briefing.yml`) → GitHub Pages.
  Cron: Sat 12:00 UTC. Email: prod subscriber list. Hard gates: ON.
- `dev/multi-expert-improvements` → dev pipeline (`briefing-dev.yml`)
  → Vercel (`macro-dashboard-dev.vercel.app`). Cron: Sat 12:00 UTC.
  Email: `EMAIL_TO_DEV` only (subscriber-safe). Gates: **observation
  mode** for renderer `--strict` (Agent 4b) and CEO-grade gate.
- `Parallel Compare (prod vs dev)` workflow (lives on **main** so
  `workflow_run` registers, plus a copy on dev) → fires on either
  briefing completion. Emits:
  - `data/run_report_<branch>_latest.md` — every fire, committed to
    dev when branch=dev, artifact-only when branch=main.
  - `data/parallel_compare_latest.md` — only when BOTH branches
    have a fresh (<24h) commit; committed to dev.

**Key commits backing the trial:**

| Branch | Commit | What |
|---|---|---|
| dev | `5db06e8` | Initial briefing-dev.yml + parallel-compare.yml + parallel_compare.py |
| dev | `952c477` | Agent 4b (renderer --strict) → observation mode |
| dev | `f6ae4d5` | Wired Vercel URL + optional health-check |
| dev | `45fa273` | CEO-grade gate → observation mode |
| dev | `371ad55` | scripts/run_report.py + restructured parallel-compare.yml + this doc extended to 1 month |
| main | `016c02a` | Listener-only landing: parallel-compare.yml + run_report.py + parallel_compare.py. **Zero prod-pipeline mods.** |

**Why landing 3 files on main was necessary:** GitHub Actions registers
`workflow_run` listeners only from workflow files on the repo's default
branch. Without `parallel-compare.yml` on main, the listener never
fires, so per-run reports and paired comparisons would silently never
generate. Main's commit is *listener-only* — no `briefing.yml`, `data/`,
or `index.html` touches; prod's Saturday cron behaviour is unchanged.

**Open known issues (block promotion to main):**

1. Renderer `--strict` flags 24 obsolete `patch_kpi()` calls — modern
   `inject_kpi()` already owns those tiles; legacy calls reference
   labels B7 renamed/removed. Workaround in place (observation mode
   on dev). Long-term fix: retire `patch_kpi()` calls in
   `scripts/renderer.py`.
2. CEO-grade gate flags 6 criticals on dev (1 validator
   `transcript_archive_coverage` + 5 vision_review). Observed, not
   blocked on dev. Either resolve or accept-as-WARN before promotion.

**Pending operator actions:**

- [ ] Set `DEV_URL` repo secret to activate Vercel health-check step.
- [ ] Set `EMAIL_TO_DEV` repo secret if you want dev email previews.
- [ ] Confirm Vercel "Production Branch" is set to
      `dev/multi-expert-improvements` (Vercel → Project Settings →
      Git → Production Branch).

**Decision date:** 2026-06-14 (T+1 month). Promotion checklist lives
in the "Decision criteria" section further down this doc.

**Resume instructions for future Claude sessions:**

1. Read this section first.
2. Check `data/run_report_dev_latest.md` and (if present)
   `data/parallel_compare_latest.md` for the most recent verdict.
3. Walk the weekly review checklist below — do not invent a different
   process.
4. Append to the Log table at the bottom of this doc; never edit
   prior log entries.

**Independent analysis snapshot (2026-05-15):**

> Full writeup: `data/prod_vs_dev_independent_analysis_2026-05-15.md`.

- **Anchor data identical** between prod and dev (UMich, FFR, 10Y, UE
  all Δ=0). Every divergence is in pipeline interpretation, not
  upstream data.
- **Dev is right in every divergence:** dev catches missing transcripts
  (1 critical), 11 palette warnings, 2 analyzer signal flags (WTI
  Δ−3.98, wages_yoy Δ−0.3) that prod's older gates silently pass.
- **`collector_errors`** delta is a sampling artifact (dev hit an
  ALFRED 429 window prod didn't); both pipelines correct.
- **CEO-grade + editorial artifacts absent on prod** by design — they
  are dev-only features in this trial.
- **Promotion blockers remain:** archive 9 missing transcripts;
  reconcile 11 palette warnings vs `data/style_guide.md`; retire
  legacy `patch_kpi()` calls; **rotate FRED API key (security)**.

**Security guardrail landed (2026-05-15):**

- `scripts/collector.py` `errors` list is now an `_ErrList` that
  scrubs `?api_key=…` / `&token=…` query params on append. All
  existing `errors.append(…)` call sites benefit with no per-site
  change. See `_scrub_secrets()` in that file.
- Validator **Pass 3k — Secret-Leak Guard** scans every JSON under
  `data/` (excluding `snapshots/`) for the same patterns. Build-
  blocking on any hit. The validator's own report redacts the match
  so the report itself can never ship the secret.
- Working-tree `data/signals.json`, `data/raw_data.json`, and
  `data/validation_report.json` were scrubbed of the existing leak.
  **The key is still in 101 historical commits — rotation is the
  only real remediation.**

**Working principles (memorized from user feedback, 2026-05-15):**

- **Experienced-coding bar.** When fixing pipeline issues, apply the
  full discipline: defensive imports, schema tolerance, stable
  fingerprints, smoke-test before commit, prefer per-pass-aware
  extractors over flat assumptions. No "good enough" patches that
  paper over schema mismatches — fix the data model first.
- **Independent analysis on divergence.** When prod and dev produce
  different outputs, **do not assume prod is right**. The dev branch
  may be the correct one (it carries the newer gates). Run a fresh
  artifact-level comparison from `origin/main` vs `HEAD`, walk each
  divergence individually, and make a per-finding ruling: prod-correct,
  dev-correct, or both-wrong. Record the verdict in this doc's log
  before promoting either way.
- **Findings ledger is the single source of truth for "what to fix
  next."** Every per-run report and every parallel comparison now
  records criticals + divergences into
  `data/parallel_findings_ledger.{json,md}` with stable fingerprints,
  occurrence counts, and KB-looked-up recommended fixes. Status
  transitions (open → monitoring → resolved) are manual — edit the
  JSON directly when a fix lands.

---

## Why parallel

The dev branch carries ~38 commits of expert-driven improvements (B1–B7
series, Tier 1/2/3 audit follow-ups, CI hardening, tier-A annotation
+ gate fixes). Rather than land it all in one large PR, we exercise
both pipelines side-by-side for **at least four weekly cycles** to
surface any regression that would only show up against fresh live
data — then decide whether to fast-forward `main` to dev or extend
the trial further.

**Observation posture on dev:** the new gates (`renderer --strict`,
CEO-grade gate) run in *observation mode* on dev — they record verdicts
without halting the pipeline. This lets us watch end-to-end behaviour
(commit-back → Vercel deploy → health-check) on every run while still
collecting every finding. On prod the same gates remain hard blocks.

## The mechanics

**Three new files own the parallel arrangement:**

| File | Role |
|---|---|
| `.github/workflows/briefing-dev.yml` | Mirrors `briefing.yml` exactly — same agents, same gates, same `--strict` — but checks out `dev/multi-expert-improvements`, commits weekly updates back to dev, skips GitHub Pages deploy, emails only if `EMAIL_TO_DEV` is set, and runs the renderer-strict + CEO-grade gates in observation mode. |
| `.github/workflows/parallel-compare.yml` | Fires on `workflow_run` completion of *either* briefing. Always emits a single-branch `run_report.md` snapshot, and when the other branch also has a fresh (<24h) successful run, additionally runs `scripts/parallel_compare.py` and commits the side-by-side comparison to dev. |
| `scripts/parallel_compare.py` | Reads `ceo_grade_verdict.json` / `validation_report.json` / `editorial_report.json` / `signals.json` / `raw_data.json` from both refs and renders a markdown comparison. |
| `scripts/run_report.py` | Per-run summary report. Reads the current ref's artifacts and writes `data/run_report_<branch>_<date>.md` + `data/run_report_<branch>_latest.md`. Fires after every briefing completion (prod or dev), even when its counterpart hasn't run yet. |

**Two intentional asymmetries vs prod:**

1. **No email to prod subscribers.** The dev publisher runs only if
   `EMAIL_TO_DEV` is configured in repo secrets — otherwise the email
   step is skipped. This prevents the production subscriber list
   from ever receiving two emails per Saturday.
2. **Separate deploy surface (Vercel, not GitHub Pages).** GitHub Pages
   is repo-restricted to `main` and a repo can serve only one Pages
   site. **Prod publishes to GitHub Pages; dev publishes to Vercel.**
   Vercel auto-deploys on every push to the dev branch, so the dev
   workflow does not run a deploy step itself — it just commits to
   dev and Vercel reacts. The workflow also uploads the rendered
   `index.html` as a downloadable artifact (14-day retention) for
   forensic review.

### Vercel setup (one-time)

1. Vercel dashboard → Add New Project → import `amitb641/macro-dashboard`
2. Production branch: `dev/multi-expert-improvements`
3. Build command: _(none — static `index.html`)_
4. Output directory: `/`
5. Once deployed, the dev URL is something like
   `macro-dashboard-dev.vercel.app`. Store it in repo secrets as
   `DEV_URL` to enable the optional Vercel health-check step.

| Deploy surface | Branch | URL |
|---|---|---|
| GitHub Pages (prod) | `main` | https://amitb641.github.io/macro-dashboard/ |
| Vercel (parallel dev) | `dev/multi-expert-improvements` | https://macro-dashboard-dev.vercel.app/ |

## How to review

### Per-run (every time either workflow fires)

Both prod and dev workflows trigger `parallel-compare.yml` on
completion. That workflow always emits:

- `data/run_report_<branch>_latest.md` — single-branch snapshot for the
  ref that just fired. Captures the verdict, validator pass counts,
  signal counters, anchor metrics, and any visual/editorial criticals.
  Committed to dev (for dev fires) or attached as an artifact only (for
  prod fires — we don't want the bot pushing to main).

Additionally, when both branches have a fresh (<24h) successful run, it
also emits:

- `data/parallel_compare_latest.md` — side-by-side diff: verdict-vs-
  verdict, pass-count delta, signals delta, anchor-metric drift.

### Weekly Saturday review checklist

After both crons fire each Saturday, walk through:

- [ ] **GitHub Actions tab** — `Weekly Macro Update` (prod) and `Weekly
      Macro Update (DEV — parallel)` both completed. Red on dev
      surfaces in a `[dev]` prefixed pipeline-failure issue.
- [ ] **`data/run_report_dev_latest.md`** — dev verdict + finding
      counts. Investigate any criticals not seen on prod.
- [ ] **`data/run_report_main_latest.md`** (artifact) — prod verdict for
      cross-check.
- [ ] **`data/parallel_compare_latest.md`** — anchor-metric drift,
      verdict mismatch, signal count delta. Anything > noise floor
      gets a note in the log below.
- [ ] **Vercel dev URL** loads, charts render, KPIs match the
      committed `index.html` artifact.
- [ ] **`data/repair_log.md`** tail — any recurring findings escalated
      by the diagnostician.
- [ ] **Log entry below** — week N: PASS/WARN/FAIL on each branch,
      anything notable.

## Decision criteria after 1 month (≥4 weekly cycles)

| Path | Trigger |
|---|---|
| **Promote dev → main** | At least 3 of the 4 weekly cycles end `PASS` or `WARN` on dev with no diverging signals on same-day data; dev's new gates (`transcript_archive_coverage`, annotation lexicon, `--strict`-on-cron, CEO-grade gate) fired correctly across the trial; legacy `patch_kpi()` calls in `scripts/renderer.py` retired so `--strict` can return to blocking mode before promotion. |
| **Extend trial** | Multiple weeks show `FAIL` on dev, comparison surfaces unexpected behavioural difference, or the renderer `--strict` cleanup work isn't done. Default extension is +2 weeks per round. |
| **Roll back dev work** | Dev introduces a regression prod doesn't have, and the root cause requires a fundamental redesign rather than a patch. |

## Tear-down (when trial completes)

If promoted to main:

1. Fast-forward `main` to dev/multi-expert-improvements (or rebase
   if main has weekly auto-commits ahead of dev)
2. Delete `.github/workflows/briefing-dev.yml`
3. Delete `.github/workflows/parallel-compare.yml`
4. Delete `scripts/parallel_compare.py`
5. Archive `data/parallel_compare_*.md` files (move to
   `data/archive/parallel_run_<date_range>/`)
6. Update this file's status to `Completed — promoted YYYY-MM-DD`

If extended or rolled back: update **Planned merge-decision date**
at the top of this file and add a short note in the log below
explaining what triggered the change.

## Known issues (active)

- **Renderer `--strict` failure on dev** (discovered 2026-05-14): the
  legacy `patch_kpi()` calls in `scripts/renderer.py` reference KPI tile
  labels that B7 either renamed or removed; the modern `inject_kpi()`
  path already owns those tiles, but the obsolete calls remain in the
  renderer and `--strict` correctly flags them as silent injection
  failures. Workaround: Agent 4b runs `--strict` as observation only
  on dev (`continue-on-error: true`). The verdict is preserved in the
  workflow log. Long-term fix: retire the legacy `patch_kpi()` calls
  before promoting dev → main. Prod is unaffected — main's `index.html`
  still carries those tiles with their original labels.
- **CEO-grade gate failure on dev** (discovered 2026-05-14): the gate
  is correctly flagging real issues — 1 validator critical
  (`transcript_archive_coverage` aggregate from the tier-A bundle) and
  5 vision-review criticals. On prod the gate halts publish; on dev we
  run it in observation mode (commit `45fa273`) so the rest of the
  pipeline (snapshot → commit-back → Vercel deploy → health-check) can
  exercise. The verdict JSON is committed to dev for every run so
  findings are preserved for the comparison report. Promotion to main
  requires resolving these or accepting them as documented WARN-level.
- **NFP_VS_ADP.adp always sparse** (data contract — NPPTTL discontinued
  2022-05-01): the 12-month ADP array will always have only ~2 filled
  values (adp_latest + _ADP_VERIFIED hardcodes). The 50% completeness
  threshold in visual_qa.py + validator.py caused a CEO gate FAIL every
  run. Fixed 2026-06-04: `SPARSE_OK['NFP_VS_ADP.adp'] = 8` in both
  files. Not a regression — data is correct; the threshold was set
  before the discontinuation.
- ~~**PCE panel title-data drift** (Pass 3d — recurring, 2026-06-04+)~~
  **RESOLVED 2026-06-04**: Root cause was a string-mismatch in the
  `pce_rebuilt` gate in `render_inflation()`. It checked
  `startswith('PCE_CAT_MOM rebuilt')` but `rebuild_pce_cat_mom()`
  appended `'PCE_CAT_MOM registered to state.json...'`. Gate was always
  False → PCE panel-sub frozen at last Agent 3 commentary month.
  Fix: one-char change to `startswith('PCE_CAT_MOM registered')`.
  Confirmed cleared in run #130: **CEO gate PASS, validator 649/649,
  0 criticals**. Commit `afc1bcf`.

## Log

| Date | Event | Note |
|---|---|---|
| 2026-05-14 | Trial started | Tier-A bundle landed on dev (`75226dd`); parallel scaffolding added. |
| 2026-05-14 | First run failed | Renderer `--strict` caught 24 obsolete `patch_kpi()` calls. Converted Agent 4b to observation mode on dev only (`952c477`). |
| 2026-05-14 | Second run failed | CEO-grade gate FAIL with 6 criticals (1 validator + 5 vision_review). Converted CEO-grade gate to observation mode on dev (`45fa273`). |
| 2026-05-14 | Trial extended | Observation window lengthened from 2 weeks to 1 month (new decision date 2026-06-14). Per-run report (`scripts/run_report.py`) added so every workflow fire emits a summary, not just paired runs. |
| 2026-05-14 | Listener landed on main | `parallel-compare.yml` + `run_report.py` + `parallel_compare.py` cherry-picked to `main` (`016c02a`) so `workflow_run` listener registers. Pure listener-only commit; no `briefing.yml` / `data/` / `index.html` changes. `Parallel Compare (prod vs dev)` workflow now `active` in repo. |
| 2026-05-14 | Gate fix verified | Run #2 (`25885014012`) completed past the CEO-grade gate in observation mode — all 11 agents ran, `ceo_grade_verdict.json` committed, snapshot created. Push failed only due to a concurrent manual push race (`45fa273` landed mid-run). Not a pipeline regression; expected to vanish once trial settles into Saturday-only cron. |
| 2026-05-14 | Plan persisted | Plan + state snapshot section added near top of this doc; `CLAUDE.md` pointer added so future Claude sessions read this first when touching CI / dev / parallel-compare. |
| 2026-05-30 | Blank chart prevention — 3-layer fix | Root cause: smoke test writing to real `data/state.json` via `_api_writer._STATE_FILE` (hardcoded path, not isolated). Fix: added `MACRO_STATE_FILE` env var override in `_api_writer.py`; smoke test save/restores the real path; `U_SECTOR_MOM` hydration assignment added to bootloader. Chart.js instance check added to `visual_qa.py` (§QA-chartjs). Commits `78af324`, `6fd4e5a`. |
| 2026-05-30 | Observability layer (4-component) | Added: (1) `window.MD._errors[]` global JS error accumulator + onerror/onunhandledrejection hooks; (2) `_safeBuild(tabName, fn)` wraps all 15 tab dispatch calls so per-tab crashes are isolated and recorded; (3) visual_qa runtime sweep reads `window.MD._errors` after tab loop; (4) `observability.yml` — 6-hour cron healthcheck against prod+dev, opens/updates/closes GitHub issues on failure. Also: `version_tracker.py` extended with `pipeline_metrics.json` lightweight timeseries + `MAX_HISTORY` 20→52. Commit `4a844f0`. |
| 2026-05-30 | Preflight 429 fix | FRED rate-limit (429) was incorrectly treated as a fatal bad-series error. Fixed: 429 now retries with 5s/10s backoff, returns `warn` (not `fatal`) after exhaustion. Commit `ba6dfa4`. |
| 2026-05-30 | observability.yml YAML fix | `if: secrets.DEV_URL != ''` is invalid in GitHub Actions — secrets context forbidden in `if:` expressions. Moved to shell guard inside `run:` step. Commit `fc553d6`. |
| 2026-06-04 | Jobs tab blank — NFP_VS_ADP cold-start bootstrap | Root cause: FRED `NPPTTL` discontinued 2022-05-01 → all three renderer fallbacks (NPPTTL stale-filtered → `read_prior` returns None → inline placeholder is `null`) exhausted simultaneously → `adp_arr = None` → `_ADP_VERIFIED` patches never ran → `NFP_VS_ADP` never registered in `state.json` → `buildJobsTab()` early return on null guard → all 4 charts blank, zero error signal. Fix: final fallback `adp_arr = [None] * len(lbl_12)` ensures `_ADP_VERIFIED` + `adp_latest` always patch in. Commit `5ca2a7d`. |
| 2026-06-04 | CEO gate FAIL fix — NFP_VS_ADP.adp completeness | 50% threshold in `visual_qa.py` + `validator.py` SPARSE_OK tables caused FAIL every run (only 2/13 months filled = 15%). Updated to 8% in both files, matching the permanent NPPTTL-discontinued data contract. Commit `9a06c51` / `832d3a7`. |
| 2026-06-04 | Stale KPIS bug — Dec'25 showing on dashboard | Root cause: rebase conflict `--theirs` on state.json picked up a pre-collection shadow CI version (10 keys, Dec'25 data) while raw_data.json already had April 2026. Fix: regenerated state.json locally (20 keys, Apr'26 data), committed directly. Commit `a65d802`. |
| 2026-06-04 | Add Pass 3l: KPI date drift guard | New validator pass compares KPI embedded month labels to raw_data latest dates. Jobs/Unemp: max 1-month lag; CPI: max 2-month lag. Critical severity — the Dec'25 bug would have triggered 3/3 FAIL with a 4-month lag. Prevents silent stale KPIS in future. Commit `2ff8f89`. |
| 2026-06-04 | Fix dev pipeline run pile-up (concurrency group) | Multiple rapid pushes during a session queued 5+ simultaneous pipeline runs, each racing to push state.json back. Root cause of the Dec'25 stale KPIS. Added `concurrency: group: dev-pipeline-push` to `briefing-dev.yml` — new push cancels in-progress push-triggered run; scheduled + workflow_dispatch runs complete uninterrupted. Commit `5a677db`. |
| 2026-06-04 | Fix preflight 429 backoff: global window-clear sleep | Saturated FRED window (from stale runs) caused per-series 5s+10s backoff to multiply to 7-16 min (63 series × 15s). Replaced with 60s first-429 sleep + 90s second — one global wait clears the window for all remaining series. Normal runs: unchanged (no 429s = 45s total). Commit `57b91b8`. |
| 2026-06-04 | Upgrade all GitHub Actions to Node.js 24 native versions | All 8 workflow files (briefing-dev, briefing, earnings_agent, observability, parallel-compare, smoke-tests, api-contract, backtest) updated: checkout v4→v6, setup-python v5→v6, upload-artifact v4→v7, github-script v7→v9. Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'` belt-and-suspenders env var. Eliminates Node.js 20 deprecation warnings ahead of GitHub's June 16 forced-upgrade deadline. Run #128 verified: 7m 11s, no deprecation warnings, Pass 3l 3/3 PASS, visual_qa 433/433 PASS. Commit `67d9af4`. |
| 2026-06-04 | Fix PCE panel subtitle frozen (Pass 3d — pce_rebuilt gate string mismatch) | `render_inflation()` gated the PCE panel-sub month update on `startswith('PCE_CAT_MOM rebuilt')` but `rebuild_pce_cat_mom()` appended `'PCE_CAT_MOM registered...'`. Gate always False → subtitle frozen at last Agent 3 commentary → Pass 3d critical every run. One-char fix: `'rebuilt'` → `'registered'`. Run #130: CEO gate PASS, validator 649/649, 0 criticals. Commit `afc1bcf`. |
| 2026-06-04 | Fix 3 more broken subtitle gates + regression smoke test | Same `'rebuilt'` vs `'registered'` mismatch in `u_rebuilt`, `sector_rebuilt`, `cpi_rebuilt` gates. Not visible in Pass 3d today (Agent 3 kept those in sync) but would drift if Agent 3 falls back to static. Fixed all 3. Added `test_panel_subtitle_gates` smoke test (8 checks) to guard the gate string contract permanently — if a rebuild function renames its message, smoke fails immediately. Smoke count 38→46. Also documented in CLAUDE.md Known Gotchas. Commit `a1da3ef`. |
| 2026-06-30 | Dark mode visual audit — §24.33/§24.34/§24.35 text + table fixes | Comprehensive dark-mode visual sweep across all tabs. §24.33: lifted `--text2` 6.1→10.6:1, `--muted` 4.2→8.3:1, `--dim` 2.6→5.6:1; chart tick opacity 0.62→0.90; weight-sharpness block for labels/tables. §24.34: card bg #0E1726→#152233 (reduces extreme halation); body `text-rendering:geometricPrecision`; `font-weight:450` via DM Sans variable font. §24.35: dtable narrative column min-widths — without `body.themed-sm`, Key View column collapsed to ~83px causing 200px row heights in Outlook/Credit/Housing/Oil tabs; mirrored all 4 constraints from `theme-overlay.css` lines 564-592 under `:root[data-theme="dark"]`. Commits `8f9a2ba`, `e2f62ca`, `0c3ac23`. |
| 2026-06-30 | Pulse/KPI-strip reorganization — economic-transmission clustering | Reorganized the existing 12-card `KPIS` strip into 4 flywheel clusters (Policy & Rates, Labor Market, Consumer & Sentiment, Inflation) grouped by stable label prefix, each with a hero tile (Fed Funds, Sahm Rule, UMich Sentiment, Core PCE) at 1.2x size. Preceded by an independent-agent data-availability audit against `collector.py`/`state.json` before any code changed — Financial Stress cluster was dropped from scope entirely because none of the 12 existing KPI cards map to it (HY spread/WTI/Card DPD live on Credit/Oil tabs, never part of this KPI array); ISM PMI confirmed uncollectable (no free FRED series). Discovered mid-build: `body.themed-sm` (not `data-theme`) is the page's actual default skin, and its `!important` rules in read-only `theme-overlay.css` silently absorbed the new unscoped hero font-size rule — required a `body.themed-sm .kpi.hero .kpi-val{...!important}` mirror in `index.html`, same pattern as the dark-mode orphan gotcha but not dark-mode-specific. Also discovered `tests/test_smoke.py`'s snapshot/rollback phase writes fixture data onto real `data/state.json` + screenshots (pre-existing, confirmed via stash-diff against committed HEAD, unrelated to this change) — flagged as a follow-up via spawn_task, not fixed this session. Verified: 54/55 smoke (1 pre-existing failure), 446/446 visual_qa.py including dark-mode sweep, live DOM inspection in both themed-sm and real dark-mode-toggle states. Commit `7e060ce`. Documented in CLAUDE.md Known Gotchas (both the themed-sm-is-default-skin finding and the smoke-test isolation gap). |
| 2026-06-30 | Fix orphaned KPI tile stretching full row on live dev site | User screenshot of `macro-dashboard-dev.vercel.app` showed Wage Growth stretched across the entire row at ~960-1100px viewport — flexbox `flex:1` fills all remaining space when a cluster's tile count wraps unevenly (Labor's 5 tiles wrap 4+1 in that width range). Added `max-width:280px` (`380px` hero) scoped to `.kpi-cluster .kpi`. Verified across 960/1100/1280px and both themes. Commit `62305ae`. |
| 2026-06-30 | Extract What Changed / calendar / KPI clusters into the Outlook tab (was global) | User caught a real gap: the earlier reorganization moved the KPI strip's *internal* layout into clusters but never actually made it a dedicated "Pulse" tab as originally requested — the block sat above the entire tab-panel system (before `#main-content`, before `nav-two-tier`), visible on every tab. Moved it inside `#tab-fc` (Outlook), directly above the pre-existing `macro-state-card` (four-pillar bars + risk badge — already matched the hero-banner concept from earlier design mockups, no new component needed). Verified `buildFCTab()` only attaches Chart.js to existing canvases via `getElementById`, never does an `innerHTML` replace, so static content nested inside `#tab-fc` survives render. Verified tab switching hides/shows the whole block correctly, other tabs start cleanly with zero gap, read-progress-bar section/word counts unaffected (nav-btn-based and `.panel`-class-based respectively, neither touches this block's classes). 55/56 smoke, 446/446 visual_qa. Commit `796f690`. Landed alongside an independently-spawned session's fix for the smoke-test isolation bug flagged in the prior log entry (commit `964318e` — root cause was `test_renderer_idempotent()`'s missing `_STATE_FILE` redirect + `validator.validate()`'s real Playwright calls, sharper diagnosis than the snapshot/rollback path originally suspected). |
| 2026-07-01 | Split Pulse into its own tab, separate from Outlook | Renamed Outlook→Pulse first (commit `e40fc01`), then user asked for a real split instead: new `id="pulse"` tab (default landing, first in Overview group) holds only What Changed + calendar + KPI clusters + macro-state banner; Outlook (`id="fc"`, relabeled back) keeps everything else it already had — GDP charts, consensus tables, forecast scenarios, sector cards, six-themes synthesis. Required updating ~9 separate locations for full wiring (now documented as a standing gotcha in CLAUDE.md): `_GRP`/`_GRPS` nav arrays ×2, `_IC` icon maps ×2 (new ECG-line icon for pulse), `_b52_activateTab('fc')`→`'pulse'` + `_nsb_sync('fc')`→`'pulse'` (default-tab activation), `TAB_NAMES`/`TAB_IDS` in `index.html` (PDF export feature), and `TAB_NAMES`/`TAB_IDS` in `scripts/visual_qa.py` **separately** — the last one matters because visual_qa.py's own tab list drives which tabs its 446 checks actually visit; without adding 'pulse' there, the suite would report a clean pass while never inspecting the new tab at all. Added it and re-ran: 449/449 (3 new checks now covering pulse). 55/56 smoke (1 pre-existing fixture-data failure, unrelated). Commit `9bc80ad`. |
| 2026-07-01 | 3-expert dark/light theme review + 5 fixes | Dispatched 3 independently-briefed expert-persona agents (terminal-grade financial UX veteran, modern SaaS design-systems director, WCAG/accessibility lead) against a precise dossier (properly alpha-composited WCAG contrast ratios, computed CSS token values, measured typography — not screenshots, which timed out consistently in this environment for this page). All 3 independently converged on the same top issues, giving high confidence. Fixed 5: (1) light-mode `.kpi-cluster-hdr` contrast 3.32:1→8.64:1, WCAG 1.4.3 fail, missing `body.themed-sm` mirror of dark mode's existing `--text2` fix; (2) `.kpi-val` font-family unified to DM Serif Display both themes — traced dark mode's stale "Instrument Serif" to an unscoped base rule inside an untitled "MACROLENS COMMERCIAL THEME v2" block (~line 2384) that dark mode falls through to since it never overrides font-family itself; (3) `.panel-title` size unified to 17px both themes, same fall-through-to-base-block root cause; (4) hero KPI tiles get a 3px accent-color left border (padding-left 24→21px to compensate) since font-size alone is the weakest pre-attentive hierarchy cue; (5) STALE badge gets a dashed border (other badge types keep solid) as a redundant non-color cue, since it's the one badge where misreading a delayed value as current has real consequences. Findings #2 and #3 revealed a **recurring pattern**: `theme-overlay.css` (external, read-only) has had newer, deliberately-reasoned fixes (each with its own explanatory comment) that were never backported to dark mode, and `style_guide.md` still documented the stale dark-mode values — both times resolved by treating themed-sm as canonical and updating dark mode + docs to match, not the reverse. `style_guide.md` corrected in 4 places. Verified via live DOM/computed-style re-inspection post-fix in both themes (not just re-reading CSS), zero `window.MD._errors`. 55/56 smoke, 449/449 visual_qa including `check_serif_scope`. Commit `1374cea`. New standing CLAUDE.md gotchas: the themed-sm-has-newer-decisions pattern, and the unscoped-base-block fall-through mechanism. |
| 2026-07-01 | Monitored dev CI pipeline post-push, confirmed healthy | User asked to "monitor PR and confirm" — no PR exists for this branch (dev trial pushes directly, per this doc's own plan); watched the push-triggered "Weekly Macro Update (DEV — parallel)" run to completion instead (`gh run watch`). CEO-grade gate showed overall FAIL but critical=0, warning=1 — `--strict` mode elevating a single warning to gate-blocking. 4-agent parallel investigation (exact warning root cause, historical recurrence check, live deployment verification, CI screenshot spot-check) confirmed: the warning is `Staleness: cs_hpi` (Case-Shiller HPI 122d old vs 120d limit), unrelated to this session's HTML/CSS work, recurring since mid-May 2026 (chronic publish-lag, not a regression). Deployment independently re-verified via direct fetch of the live dev URL (confirmed "Pulse" present in response body, not just a generic 200). Two unrelated ops items surfaced and flagged to user (not fixed, outside this session's scope): the Repair Diagnostician's LLM calls are failing on an Anthropic billing error ("credit balance too low"), and `cs_hpi` has no baseline entry in `playbook.md`/`known_normal.json`. |
| 2026-07-01 | Comprehensive theme font/canvas-width audit — 6 real bugs found and fixed | User reported light/dark fonts still look different post-review, plus dark mode has a visibly wider content canvas than light. Ran a 2-agent extraction workflow (all 244 `body.themed-sm` rules in `theme-overlay.css` vs all 248 `:root[data-theme="dark"]` rules + fallback base-block values in `index.html`) + a cross-reference synthesis, which produced ~17 claimed divergences. **Critical methodology finding: the workflow's cascade reasoning was wrong for most claims** — it assumed a dark-scoped `!important` rule and a later unscoped `!important` rule have equal specificity (tie-broken by source order), but `:root[data-theme="dark"] X` is objectively more specific than bare `X` (attribute selector adds real specificity), so dark-scoped rules correctly win regardless of order. It incorrectly claimed the session's own earlier §24.12/§24.35 fixes were being "silently cancelled" — direct `getComputedStyle` checks showed both fully intact. Empirically re-verified all ~17 claims in a live browser before touching any code; only 6 were real: (1) `h1` font-family (DM Sans light / Instrument Serif dark — §24.31 set size/weight but never font-family); (2) `body` padding (32/48/80px light vs 20/28/60px dark, no dark override existed at all — this was the actual "wider canvas" cause, ~28px extra width at desktop; added full parity including 1920px/2400px/900px/720px breakpoints); (3) `.panel-sub` font-family/size/weight (3 properties, one selector); (4) `.kpi-val` font-weight (400 light / 600 dark, §24.31 drifted from its own stated "parity" goal); (5) `.m-lbl` font-weight (700 light / 500 dark); (6) `.sort-btn` padding (no dark override existed). Findings #3 and #5 share a root cause: §24.33's halation-compensation pass assumed a 400/500 light-mode baseline and bumped dark up — but `.m-lbl`/`.panel-sub`'s actual light baseline is 700, so the "boost" to 500 undershot, making dark *lighter* than light, the opposite of the intended effect. Checked every other §24.33-touched selector (m-sub, panel-meta, sm-dc-*, spark-tile-label) against light's current weights — all correctly bolder in dark, no fix needed there. Verified via live re-measurement post-fix: every property matches exactly between themes, content width matches exactly (1334px both), zero `window.MD._errors`. 55/56 smoke, 449/449 visual_qa. Commit `3615a28`. New standing CLAUDE.md gotcha: never trust an LLM's textual CSS-cascade analysis without empirical `getComputedStyle` verification — of 17 claims, only 6 (35%) were real. |
| 2026-07-01 | KPI value semantic colors were dead in light mode | User posted side-by-side light/dark screenshots (no text) — comparison showed Initial Claims/Unemployment/Sahm Rule/Wage Growth rendering in green/amber in dark mode but plain near-black in light. Root cause: `theme-overlay.css`'s `body.themed-sm .kpi-val{color:#0D1B2A!important}` — a class-selector `!important` — always beats a non-`!important` inline style regardless of specificity, so `_kpiColor()`'s correctly-computed per-tile hex (verified present in every tile's inline `style` attribute) was silently overridden to uniform near-black on every KPI value in light mode. Fix: added `!important` to the inline style itself (`style="color:${col}!important"`) — inline `!important` outranks a class-selector `!important`, restoring color without touching read-only `theme-overlay.css`. Unexpected bonus: dark mode was also not rendering its exact authored hex before this fix (some other non-`!important` rule was shifting it slightly, never tracked down) — the same one-line fix corrected that too, so both themes now render pixel-identical semantic colors. Verified via `getComputedStyle` + `getAttribute('style')` side-by-side for every tile in both themes. 55/56 smoke, 449/449 visual_qa. Commit `8f9267a`. Same bug class as the font/padding cascade issues logged above — added to the standing CLAUDE.md gotcha list: suspect a forced-color `!important` rule whenever a value looks washed-out/monochrome in one theme only. |
| 2026-07-01 | **Regression**: dark-mode sidebar overlapping main content, from earlier same-day fix | User screenshot showed the sidebar covering the left ~220px of page content in dark mode — a direct regression introduced by the body-padding parity fix earlier this same session (commit `3615a28`). That fix's own comment incorrectly claimed the 901px+ sidebar-active 240px left-offset was "theme-agnostic and already matches both themes" — it wasn't; the new dark-scoped body-padding rule's specificity beat whatever lower-specificity rule provided that offset, resetting padding-left to 48px for any viewport 901-1920px wide (the range NOT covered by the fix's own 1920px+ override). First verification attempt appeared to pass at 1440px, but that check used `toggleTheme()` JS calls rather than a real page reload — a stale-cache artifact masked the bug. Re-verified with `location.reload(true)` (cache-bypassed) at 4 widths spanning every breakpoint (800/1226/1440/2000px): confirmed broken at 1226 and 1440, fixed by adding the missing `@media(min-width:901px)` sidebar-active mirror (matching `theme-overlay.css` lines 46-49 exactly). Re-verified clean at all 4 widths post-fix, zero overlap, zero `window.MD._errors`. 55/56 smoke, 449/449 visual_qa. Commit `2732fd0`. New standing CLAUDE.md gotcha: a `toggleTheme()` JS call and a real page reload can disagree if the browser cache serves stale CSS — always hard-reload when verifying a CSS fix, and always test multiple breakpoints spanning the full range a mirrored rule covers, not just the one width a bug screenshot happened to show. |
| 2026-07-01 | Design mockup round (3 widgets, no code) + text sharpness/brightness pass | User asked whether "Claude Design" (claude.ai/design) could redesign the dashboard — confirmed it can't apply here (no component library/Storybook to sync, per the earlier `/design-sync` investigation this session) and proposed mockups instead. Built 3 visualize-tool mockups showing before/after craft polish (no new colors or fonts): KPI tile + chart panel + data table, then macro-state banner + delta cards + so-what callout, then a full composed Pulse-tab mockup with sidebar. User approved direction, then asked for text to look "sharper, brighter, 8K quality." Implemented 3 real changes: (1) `text-rendering:geometricPrecision` was dark-mode-only, extended globally to also improve light-mode serif-numeral rendering; (2) DM Serif Display (the `.kpi-val` font, unified across themes earlier this session) ships only weight 400 with no bold variant — added a hairline `-webkit-text-stroke:0.3px currentColor` to every KPI value in both themes (required the usual `body.themed-sm` mirror since theme-overlay.css doesn't set this) rather than risk browser font-synthesis distorting the serif letterforms; (3) the existing dark-mode Chart.js tick-brightening plugin (`md_dark_theme`, sets tick color but never touched weight) got a `font.weight:500` bump via `Object.assign` to avoid overwriting each chart's own inline font-size. Verified via `getComputedStyle` in both themes; local Chart.js introspection (`Chart.getChart`) hit an unrelated API-access issue in this dev environment, so relied on `visual_qa.py`'s live-Playwright Chart.js-instance check instead (449/449 pass, confirms charts still render with live instances, not just DOM presence). 55/56 smoke. Commit `73176bc`. |
| 2026-07-01 | Redesign KPI value color: monochrome, color reserved for delta badge | User asked whether black/white KPI values would be clearer than the existing colored ones. Dispatched 2 independent expert reviews (terminal-grade financial UX veteran + accessibility lead) rather than answer solo, since this touches the semantic color system fixed earlier today. While gathering ground truth for the dossier, found the actual root problem: the main KPI value is colored by *absolute threshold status* (`_KPI_THRESHOLDS`: is this metric currently green/amber/red-zone) while the adjacent delta badge is colored *independently* by direction of change — two different semantic dimensions sharing one red/green/amber vocabulary on adjacent elements, which can visually disagree (concrete case found: UMich Sentiment sits in the red zone but had just improved, showing a red value next to a green up-arrow on one tile). Both experts converged on the same fix without seeing each other's answer: reserve color for the delta badge only (it already has a redundant arrow glyph, so no accessibility loss), make the main value neutral, and reserve a rare non-color cue (border + dot) for genuine red-zone alerts only — not amber/green, so the cue stays meaningful rather than becoming new permanent wallpaper. Showed a mockup of the exact UMich-style collision case resolved before implementing. `_kpiColor()` now returns purple (policy rates, unchanged) or null (neutral); new `_kpiIsAlert()` reuses the existing threshold `red()` check. Alert border/dot placed after the existing hero-border CSS so a tile that's ever both hero and alert shows red (active alert reads as more urgent than "this is the headline metric"). Verified against live data both themes: policy rates stay purple, the 4 genuinely red-zone KPIs (UMich Sentiment, Headline CPI, Core PCE, Headline PCE) show the new alert cue with neutral text, the other 6 (previously green/amber) go fully neutral with no cue, delta badges unaffected. Zero `window.MD._errors`. 55/56 smoke, 449/449 visual_qa. Commit `f6ee114`. |
