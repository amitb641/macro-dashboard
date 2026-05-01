# Macro Dashboard — Claude Code Guidelines

## Branch Strategy
- **Production branch**: `main` — small targeted fixes (1-2 file changes) go directly here
- For small fixes, commit and push straight to `main`. Don't create feature branches for minor fixes — it creates unnecessary merge/rebase overhead.
- Only use feature branches for multi-file features or changes that need review
- Never create new branches without asking
- Clean up stale remote branches after merging

## Local Dev Workflow
- Dev worktree: `/home/user/macro-dashboard-dev` on branch `dev` (shares `.git` with main checkout via `git worktree`)
- Preview server: `scripts/dev-preview.sh [port] [tab]` — defaults to `:8765`, optional tab hash (e.g. `banks`, `gdp`)
- Iterate on `dev`, smoke-test, then cherry-pick or merge to `main` in the primary checkout
- Teardown: `git worktree remove /home/user/macro-dashboard-dev`

## Project Architecture
10-agent Python data pipeline:
0. `scripts/preflight.py` — Agent 0: Pre-flight validates every FRED series_id used by collector returns ≥1 obs. Halts pipeline immediately on any 4xx so downstream agents never run on poisoned data. (Self-verification — `docs/SELF_VERIFICATION.md`.)
1. `scripts/collector.py` — Agent 1: Pulls data from FRED, BLS, EIA APIs
2. `scripts/analyzer.py` — Agent 2: Diffs raw data, scores signals
3. `scripts/briefing_agent.py` — Agent 3: AI commentary (Claude Sonnet)
4. `scripts/renderer.py` — Agent 4: Patches index.html with chart data (regex-based)
5. `scripts/validator.py` — Agent 6: Independent data quality checks (8-pass)
6. `scripts/publisher.py` — Agent 5: Email delivery via Resend
7. `scripts/visual_qa.py` — Agent 7: DOM-based visual quality checks (Playwright)
8. `scripts/visual_review.py` — Agent 8: Vision-based chart review (Claude multimodal)
9. `scripts/earnings_agent.py` — Agent 9: Autonomous quarterly earnings — fetches transcripts, extracts verbatim fields via Claude Sonnet, gated by validator Pass 3c. Runs on its own cron (`earnings_agent.yml`, 10pm UTC during Jan/Apr/Jul/Oct weeks). **Never touches the weekly briefing cadence.**

Supporting scripts:
- `scripts/snapshot.py` — Rolling data backups (keep last 3)
- `scripts/healthcheck.py` — Post-deploy page verification
- `scripts/version_tracker.py` — Pipeline run audit trail

## Key Files
- `METHODOLOGY.md` — Source of truth for indicator definitions, formulas, thresholds, and confirmation logic. Update whenever a threshold or rule changes.
- `index.html` — Single-page dashboard (~460KB), JS constants embedded inline
- `data/raw_data.json` — All collected API data
- `data/signals.json` — Analyzer output
- `data/bank_earnings.json` — Quarterly earnings commentary (source of truth for `BANK_COMMENTARY` in `index.html`; renderer patches it in via `update_bank_cards`; Agent 9 writes it autonomously)
- `data/earnings_calendar.json` — Per-quarter bank reporting dates + transcript URL candidates; Agent 9's input (maintained quarterly by a human)
- `data/transcripts/<Quarter>/<TICKER>.txt` — Archived earnings-call transcripts (auto-saved by Agent 9); presence enables validator Pass 3c verbatim gate
- `data/validation_report.json` — Validator output (6-pass)
- `data/visual_review_report.json` — Agent 8 vision review output
- `data/pipeline_version.json` — Version tracking audit log
- `.github/workflows/briefing.yml` — Main CI pipeline (Agents 1-8, weekly Fri + monthly 2nd Sat)
- `.github/workflows/earnings_agent.yml` — Agent 9 cron (quarterly, earnings-season only — Jan/Apr/Jul/Oct days 10-28, 10pm UTC)
- `.github/workflows/smoke-tests.yml` — PR smoke tests

## Known Gotchas
- BLS values are strings (e.g., `'23756.5'`), always use `round(float(val))` not `int(val)`
- `json.dumps` produces `\u` escapes — always use `lambda m: replacement` in `re.subn`, never raw strings
- FRED single-value endpoints return `{"date": "...", "value": 4.25}` dicts, not scalars
- Running renderer twice on same HTML causes benign `patch_kpi` warnings (labels already updated)
- PCE staleness warnings are genuine data lag (~95 day publication delay), not bugs
- Regex-replace patterns in `renderer.py` must match the JSON shape the renderer *itself writes back* — `json.dumps(..., separators=(', ', ':'))` produces single-line output, so patterns requiring `\n};` will silently fail after the first run (see `update_shock_tracker`)
- UMich Consumer Sentiment: collector pulls direct from `sca.isr.umich.edu/files/tbcics.csv` first (gives prelim ~2 weeks before FRED's embargoed final). `umcsent` entries carry a `status` field (`'preliminary'` or `'final'`) — renderer/KPI/validator all treat missing status as `'final'` for back-compat

## Shock Tracker Data Contracts
The Oil Impact Chain (`update_shock_tracker` in `renderer.py`) rebuilds `SHOCK_TRACKER` every run. Each phase reads from specific raw-data keys — if you change a key name or fetch count, the phase silently falls back to a hardcoded baseline. Audit the whole chain when touching any of these:

| Phase | Metric | Raw-data key | YoY needs |
|---|---|---|---|
| Pump Prices Spike | Gasoline $/gal | `gasoline` (GASREGW weekly) | 2 obs — pre-shock + latest |
| Transport & Freight | CPI Transport Svcs YoY | `cpi_transport` (CUSR0000SETG) | **24 obs** (13 for YoY + pre-shock) |
| CPI Energy Prints | CPI Energy YoY | `cpiengsl` (CPIENGSL) | 13+ obs |
| Food & Services | CPI Food Away YoY | `cpi_food_away` (CUSR0000SEFV) | **24 obs** (13 for YoY + pre-shock) |
| Core Goods | Core CPI YoY | `vals['core_cpi_yoy']` scalar | — |
| Consumer Sentiment | UMich | `vals['umcsent']` scalar | — |
| Savings Drawdown | Saving Rate | `vals['saving_rate']` scalar + `data['psavert']` dates | — |
| Delinquencies | CC 90+ DPD | `vals['cc_delinq']` scalar + `data['cc_delinq']` dates | — |

Rules:
- Any series feeding a YoY phase in the tracker must be collected with `limit>=24` (covers latest + year-ago + pre-shock baseline + buffer)
- Post-shock gate: a phase only moves beyond `not_yet` when the series' latest date is `>= 2026-03-01`. The shock date is hardcoded in `update_shock_tracker`; update it if the scenario changes
- After editing the tracker, spot-check the rendered HTML — `SHOCK_TRACKER` should contain real `pre`/`now` numbers, not equal hardcoded defaults (a silent fall-through symptom)

## Testing
- Run `python tests/test_smoke.py` before pushing — must be 29/29 pass
- Run `python scripts/visual_qa.py` for DOM-based visual checks (224 checks)
- Run `python scripts/visual_review.py` for AI vision-based chart review (requires ANTHROPIC_API_KEY)
- Run `python scripts/renderer.py` to verify no hard errors
- Validator is a build gate — critical divergences block publishing
- Validator runs 9 passes: internal consistency, source verification, staleness, shock tracker, panel-data consistency, metric consistency, **schema contract** (3f), **seed drift** (3g), **collector errors** (3h), earnings commentary (verbatim), visual QA, vision review

## Commit Conventions
- Bug fixes: `Fix <what>: <detail>`
- Features: `Add <what>: <detail>`
- Data updates: auto-committed by CI as `Weekly update: YYYY-MM-DD`
- Always commit and push before ending a session

## Data Quality Checks
- When fetching time series data, ensure fetch count covers the full range needed by the renderer (e.g., 12 months of monthly charts need ~60 weekly observations, not 6)
- When aligning two series by label, check for null/None fill rates — >20% nulls indicates a fetch-count or alignment bug
- Trace data path from collector → renderer to verify sufficiency before shipping

## Earnings Commentary — Factuality Rule (project skill)
Applies to `BANK_COMMENTARY`, `BANK_THEMES`, `BANK_RESULTS`, earnings-call panels in `index.html`, and any narrative block sourced from a company disclosure.

- **Only real, attributable content.** Every CEO/CFO quote must be a verbatim excerpt from an actual earnings call transcript, press release, or 10-Q/10-K filed by that company. No paraphrases in quotation marks. No composed sentences written in an executive's voice.
- **No implication, no fabrication.** Do not write forward-looking guidance, NCO rates, EPS, NIM, or headcount numbers unless the figure is published by the company. If a company hasn't reported yet (e.g. Barclays BCUS on Apr 30 before it happens), mark it `Pending` — do not pre-fill with estimates.
- **Cite the source channel** via the `src` field tag (`Prepared` / `Q&A` / `Summary` / `Pending` / `FY25 Call`). If you can't point to a transcript line or filing page, the content doesn't ship.
- **Verify before editing.** Before modifying a quote or figure in an earnings card, read the underlying source (transcript URL, press-release PDF, or 10-Q) and paste the matching snippet in the commit message. "Touched up wording" is not allowed — either the quote is verbatim or it becomes a non-quoted summary.
- **When in doubt, remove — don't smooth.** If a sentence reads well but you can't source it, delete it rather than rephrasing it into plausibility.
- **Structural redesigns need sources first.** Expanding the card schema (e.g. adding Performance Trends / Credit Performance / Regulation / Tech-AI sub-sections) requires sourced content for every new field per bank before any template change lands. Do not ship a new template populated with AI-generated filler.
- **Auditing checklist** before any commit that touches this data:
  1. Every `quote` field traces to a transcript line.
  2. Every numeric (NCO, NII, EPS, NIM, volumes) matches the company's released figure.
  3. Future-dated items (reports after today's date) are marked `Pending`.
  4. Source attribution in the panel footer lists each call date used.

### Update Workflow (Q2 2026 onward)
The earnings commentary is **data-driven** — do not hand-edit `index.html`. Flow:

1. **Edit `data/bank_earnings.json`** — add/update each bank's `actual_report_date`, `transcript_url`, `quote`, and the 7 field entries (`economy`, `lending`, `cards_loans`, `macro`, `tech_ai`, `credit`, `outlook`). Set `status` to `reported` once actual data is in. Leave `pending` for banks whose call hasn't happened yet.
2. **Archive the transcript** to `data/transcripts/<Quarter>/<TICKER>.txt` (e.g. `data/transcripts/Q2_2026/JPM.txt`) — plain text of the call is fine. This enables the validator's verbatim gate for this bank.
3. **Run `python scripts/renderer.py`** — patches `BANK_COMMENTARY` in `index.html` from the JSON. Date with `(pending)` suffix is rendered automatically for banks whose `actual_report_date` is missing or in the future.
4. **Run `python scripts/validator.py`** — Pass 3c (`check_earnings_verbatim`) verifies every quoted span in your JSON exists verbatim in the archived transcript. A mismatch is build-blocking (critical severity).
5. **Update the panel footer `src=...` line** in `index.html` by hand for now (sources attribution — not yet automated).

When the reporting date list changes quarter-to-quarter, update `expected_report_date` per bank in the JSON (single field, one place).

## Agent Skills (Slash Commands)
Custom development lifecycle commands are available in `.claude/commands/`:
- `/spec` — Define what to build (spec before code)
- `/plan` — Plan implementation as small, atomic tasks
- `/build` — Implement one slice at a time with verification
- `/test` — Run all test layers: smoke (29/29), renderer, visual QA (224)
- `/review` — Code review checklist (correctness, safety, scope, pipeline integrity)
- `/code-simplify` — Simplify code without changing behavior
- `/ship` — Pre-flight checks, push, and post-ship verification

Use these commands to follow a structured development lifecycle for all changes. For multi-step features, follow the flow: `/spec` → `/plan` → `/build` → `/test` → `/review` → `/ship`.

## Do NOT
- Create new branches without asking (for small fixes, push directly to main)
- Delete data files without snapshots
- Add dependencies without updating the CI pip install step
- Skip smoke tests before pushing

## Rollback Anchors
Known-good baselines are tracked in `.claude/BACKUPS.md` (dedicated registry,
not this generic file). Before multi-commit refactors, create a fresh
`backup/<tag>` branch and log it there with what state it captures.
