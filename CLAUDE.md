# Macro Dashboard — Claude Code Guidelines

## Branch Strategy
- **Production branch**: `main`
- **Development branch**: `dev` — ALL changes go here first, regardless of session
- Never create new feature branches unless explicitly asked
- Always check out `dev` at the start of a session: `git checkout dev && git pull origin dev`
- Push to `dev` when work is complete
- PRs are created from `dev` → `main` only when a batch of changes is ready for release

## Project Architecture
6-stage Python data pipeline:
1. `scripts/collector.py` — Pulls data from FRED, BLS, EIA APIs
2. `scripts/analyzer.py` — Diffs raw data, scores signals
3. `scripts/briefing_agent.py` — AI commentary (Claude Sonnet)
4. `scripts/renderer.py` — Patches index.html with chart data (regex-based)
5. `scripts/validator.py` — Independent data quality checks (3-pass)
6. `scripts/publisher.py` — Email delivery via Resend

Supporting scripts:
- `scripts/snapshot.py` — Rolling data backups (keep last 3)
- `scripts/healthcheck.py` — Post-deploy page verification
- `scripts/version_tracker.py` — Pipeline run audit trail
- `scripts/visual_qa.py` — Agent 7: DOM-based visual quality checks (Playwright)

## Key Files
- `index.html` — Single-page dashboard (~460KB), JS constants embedded inline
- `data/raw_data.json` — All collected API data
- `data/signals.json` — Analyzer output
- `data/validation_report.json` — Validator output
- `data/pipeline_version.json` — Version tracking audit log
- `.github/workflows/briefing.yml` — Main CI pipeline
- `.github/workflows/smoke-tests.yml` — PR smoke tests

## Known Gotchas
- BLS values are strings (e.g., `'23756.5'`), always use `round(float(val))` not `int(val)`
- `json.dumps` produces `\u` escapes — always use `lambda m: replacement` in `re.subn`, never raw strings
- FRED single-value endpoints return `{"date": "...", "value": 4.25}` dicts, not scalars
- Running renderer twice on same HTML causes benign `patch_kpi` warnings (labels already updated)
- PCE staleness warnings are genuine data lag (~95 day publication delay), not bugs

## Testing
- Run `python tests/test_smoke.py` before pushing — must be 29/29 pass
- Run `python scripts/visual_qa.py` for DOM-based visual checks (224 checks)
- Run `python scripts/renderer.py` to verify no hard errors
- Validator is a build gate — critical divergences block publishing

## Commit Conventions
- Bug fixes: `Fix <what>: <detail>`
- Features: `Add <what>: <detail>`
- Data updates: auto-committed by CI as `Weekly update: YYYY-MM-DD`
- Always commit and push before ending a session

## Do NOT
- Create new branches without asking
- Modify `main` directly
- Delete data files without snapshots
- Add dependencies without updating the CI pip install step
- Skip smoke tests before pushing
