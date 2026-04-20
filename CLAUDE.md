# Macro Dashboard — Claude Code Guidelines

## Branch Strategy
- **Production branch**: `main` — small targeted fixes (1-2 file changes) go directly here
- For small fixes, commit and push straight to `main`. Don't create feature branches for minor fixes — it creates unnecessary merge/rebase overhead.
- Only use feature branches for multi-file features or changes that need review
- Never create new branches without asking
- Clean up stale remote branches after merging

## Project Architecture
8-agent Python data pipeline:
1. `scripts/collector.py` — Agent 1: Pulls data from FRED, BLS, EIA APIs
2. `scripts/analyzer.py` — Agent 2: Diffs raw data, scores signals
3. `scripts/briefing_agent.py` — Agent 3: AI commentary (Claude Sonnet)
4. `scripts/renderer.py` — Agent 4: Patches index.html with chart data (regex-based)
5. `scripts/validator.py` — Agent 6: Independent data quality checks (5-pass)
6. `scripts/publisher.py` — Agent 5: Email delivery via Resend
7. `scripts/visual_qa.py` — Agent 7: DOM-based visual quality checks (Playwright)
8. `scripts/visual_review.py` — Agent 8: Vision-based chart review (Claude multimodal)

Supporting scripts:
- `scripts/snapshot.py` — Rolling data backups (keep last 3)
- `scripts/healthcheck.py` — Post-deploy page verification
- `scripts/version_tracker.py` — Pipeline run audit trail

## Key Files
- `index.html` — Single-page dashboard (~460KB), JS constants embedded inline
- `data/raw_data.json` — All collected API data
- `data/signals.json` — Analyzer output
- `data/validation_report.json` — Validator output (5-pass)
- `data/visual_review_report.json` — Agent 8 vision review output
- `data/pipeline_version.json` — Version tracking audit log
- `.github/workflows/briefing.yml` — Main CI pipeline
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
- Validator runs 5 passes: internal consistency, source verification, staleness, visual QA, vision review

## Commit Conventions
- Bug fixes: `Fix <what>: <detail>`
- Features: `Add <what>: <detail>`
- Data updates: auto-committed by CI as `Weekly update: YYYY-MM-DD`
- Always commit and push before ending a session

## Data Quality Checks
- When fetching time series data, ensure fetch count covers the full range needed by the renderer (e.g., 12 months of monthly charts need ~60 weekly observations, not 6)
- When aligning two series by label, check for null/None fill rates — >20% nulls indicates a fetch-count or alignment bug
- Trace data path from collector → renderer to verify sufficiency before shipping

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
