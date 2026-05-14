# Parallel Run: prod (main) vs dev/multi-expert-improvements

> **Start date:** 2026-05-14
> **Planned merge-decision date:** 2026-06-14 (T+1 month — extended from
> original T+2 weeks for tighter observation of the new gates)
> **Status:** Active — observation mode

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
