# Parallel Run: prod (main) vs dev/multi-expert-improvements

> **Start date:** 2026-05-14
> **Planned merge-decision date:** 2026-05-28 (T+2 weeks)
> **Status:** Active

This document tracks the parallel-run trial of the
`dev/multi-expert-improvements` branch against production (`main`).
Both branches now operate independent, parallel CI pipelines against
the same upstream data sources (FRED / BLS / EIA / Anthropic /
Resend). Neither inherits state from the other.

---

## Why parallel

The dev branch carries ~38 commits of expert-driven improvements (B1–B7
series, Tier 1/2/3 audit follow-ups, CI hardening, tier-A annotation
+ gate fixes). Rather than land it all in one large PR, we exercise
both pipelines side-by-side for 2 weeks to surface any regression
that would only show up against fresh live data — then decide whether
to fast-forward `main` to dev or extend the trial.

## The mechanics

**Three new files own the parallel arrangement:**

| File | Role |
|---|---|
| `.github/workflows/briefing-dev.yml` | Mirrors `briefing.yml` exactly — same agents, same gates, same `--strict` — but checks out `dev/multi-expert-improvements`, commits weekly updates back to dev, skips GitHub Pages deploy, and emails only if `EMAIL_TO_DEV` is set. |
| `.github/workflows/parallel-compare.yml` | Fires on `workflow_run` completion of *either* briefing. When the other branch also has a fresh (<24h) successful run, runs `scripts/parallel_compare.py` and commits the report to dev. |
| `scripts/parallel_compare.py` | Reads `ceo_grade_verdict.json` / `validation_report.json` / `editorial_report.json` / `signals.json` / `raw_data.json` from both refs and renders a markdown comparison. |

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
| Vercel (parallel dev) | `dev/multi-expert-improvements` | (set after Vercel project creation) |

## How to review

Every Saturday after both crons fire, look for:

1. **The most recent `data/parallel_compare_latest.md`** (committed to
   dev) — gives the headline diff: verdict-vs-verdict, pass-count
   delta, signals delta, anchor-metric drift.
2. **GitHub Actions tab** — runs of both `Weekly Macro Update` (prod)
   and `Weekly Macro Update (DEV — parallel)` should both be green.
   Red on dev surfaces in a `[dev]` prefixed pipeline-failure issue.
3. **The dev branch's `index.html` artifact** — download from the dev
   workflow run to inspect the rendered page locally.

## Decision criteria after 2 weeks

| Path | Trigger |
|---|---|
| **Promote dev → main** | 2 consecutive weeks of `PASS` or `WARN` verdicts on dev with no diverging signals on same-day data; dev's new gates (`transcript_archive_coverage`, annotation lexicon, `--strict`-on-cron) fired correctly. |
| **Extend trial** | Any week shows `FAIL` on dev, or comparison surfaces unexpected behavioural difference that warrants more observation. |
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

## Log

| Date | Event | Note |
|---|---|---|
| 2026-05-14 | Trial started | Tier-A bundle landed on dev (`75226dd`); parallel scaffolding (this commit) added. |
