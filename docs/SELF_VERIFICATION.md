# Self-Verification & Self-Correction — Design + Status

This document captures the audit-driven hardening of the dashboard pipeline
and the architectural plan for moving toward complete agentic AI automation.
Born out of the 2026-05-01 audit session that found and fixed six bugs in
the same failure class.

## The bug class we keep seeing

Every bug found in the May 1 audit shared the same fingerprint:

> **A pipeline component fails silently → falls back to a static seed →
> the seed drifts over time → users see stale numbers that look fresh.**

Concrete instances (all fixed):

| # | Bug | Failure mode |
|---|---|---|
| 1 | PCE_CAT_MOM rebuild skipped | 6 of 10 FRED IDs returned 400; threshold gate skipped rebuild; chart frozen at "Jan'26 vs Dec'25" while Mar'26 data was already published |
| 2 | CPI_CAT_MOM partial-fill | 2 of 10 FRED IDs returned 400; threshold (≥8) still met; Apparel + Energy bars silently dropped from chart |
| 3 | FC_MACRO act25 GDP/FFR | renderer read `gdp_real_annual` / `ffr_monthly`; collector wrote `gdpc1_annual` / `fedfunds_annual`; fallback chain returned `[]`; static seed preserved forever |
| 4 | FC_MACRO act24 historical | only `act{prev_yr}` got patched; `act24` FFR drifted to 4.6 vs actual 5.1 |
| 5 | SPREADS_DATA + OIL_VS_HY | (a) FRED `freq='a'` returned only n=2 for BAML OAS series; (b) annual values in raw % (1, 1) but latest in bps (81); chart showed `[1, 1, 81]` instead of `[~120, ~95, 81]` |
| 6 | Shock-tracker margins | `cpi_food_away` / `cpi_transport` collector limit=24, FRED returned n=23, borderline below YoY+pre-shock requirement |

All six fall into the same pattern, which means a single class of validator
checks would catch all six simultaneously.

## Architecture: where new layers fit

The current pipeline is a 9-agent linear chain plus one off-cycle agent
(Agent 9 — earnings). Self-verification adds passes inside the existing
validator and one new off-cycle agent following the Agent 9 pattern.

```
                ┌─ Agent 0 (Pre-flight)  ✅ live ── Validates FRED IDs upstream
                │
Briefing chain ─┼─ Agent 1 (collector)
                ├─ Agent 2 (analyzer)
                ├─ Agent 3 (briefing AI)
                ├─ Agent 4 (renderer)
                ├─ Agent 6 (validator)  ✅ Pass 3f (schema contract) — implemented
                ├─ Agent 5 (publisher)  ✅ Pass 3h (collector errors)  — implemented
                ├─ Agent 7 (visual QA)     Pass 3g (seed drift)        — proposed
                └─ Agent 8 (visual review) Pass 3i (unit consistency)  — proposed

Off-cycle ──────┬─ Agent 9 (earnings)              [existing, validator-gated]
                └─ Agent 10 (repair) [proposed] ── Tier 2/3: validator-gated, writes PRs
```

Key principle from Agent 9: autonomous agents run **off-cycle**, are
**validator-gated**, and **write structured artifacts (PRs, JSON)** — they
never extend or block the weekly briefing pipeline.

## Three tiers, ordered by cost and risk

### Tier 1 — deterministic checks (no LLM, no external calls)

| Pass | Status | What it does | Bug class caught |
|---|---|---|---|
| 3f — schema contract | ✅ live | Static-analyzes `collector.py` writes vs `renderer.py` reads; flags every key the renderer reads with no collector writer | #3 (renamed key drift) |
| 3g — seed drift | ✅ live | Recomputes FC_MACRO.actNN from raw data each run, compares to seed; flags > per-metric tolerance | #4 (act24 historical drift) |
| 3h — collector errors | ✅ live | Surfaces `raw_data['errors']` (FRED/BLS 4xx) as critical findings | #1, #2 (bad FRED IDs) |
| 3i — unit consistency | proposed | Decorate each series with `unit` tag (`pct`, `bps`, `index`); renderer asserts at point-of-use | #5 (% vs bps mismatch) |

**Currently implemented (3f + 3g + 3h):**
- `check_schema_contract()` — regex-extracts key writes from collector and reads from renderer; cross-checks. ~50 LOC.
- `check_seed_drift(html, data)` — recomputes FC_MACRO.actNN from `gdpc1_annual` / `unrate` / `cpi_all` / `ahetpi` / `fedfunds_annual`, compares against the seed parsed out of index.html; per-metric tolerance dict (`_FC_DRIFT_TOLERANCE`). 1 metric drifted = warning, ≥2 = critical. ~80 LOC.
- `check_collector_errors(raw)` — parses `raw_data['errors']` for FRED/BLS API failures by series ID. ~30 LOC.
- All feed into `build_report` and surface in `data/validation_report.json` under `schema_contract` / `seed_drift` / `collector_errors` keys. Critical-severity findings push status to FAIL via the existing `CRITICAL_THRESHOLD` gate.
- Whitelists: `_NON_COLLECTOR_KEYS = {'banks'}` (sourced from `bank_earnings.json`).
- Tolerances: GDP ±0.15pp, Unemployment ±0.10pp, CPI ±0.15pp, Wage ±0.20pp, FFR ±0.10pp.

### Tier 2 — LLM-assisted fix proposals

When Tier 1 catches an issue, dispatch to Claude API for a *proposed* fix:

- **Bad FRED ID → suggest replacement.** Validator passes the 400 + series description; Claude returns closest matching valid ID with confidence score, verified by re-fetching.
- **Schema mismatch → suggest rename.** Claude reads both files, proposes the rename diff.
- **Seed drift → propose recompute path.** If a seed is drifting and there's no rebuild, Claude writes the rebuild function.

Output: a draft PR with `auto-fix-proposal` label. **Never auto-merged.** Human reviews. Existing Agent 9 (earnings) is the precedent for this class of autonomous agent in the repo.

### Tier 3 — autonomous watchdog (Agent 10)

Same Agent 10, elevated autonomy: when Tier 2 proposes a fix, the agent
runs the full pipeline + smoke tests in a worktree. If green, opens a PR
automatically. SLO: "no critical-severity divergence persists > 1 weekly cycle."

**Don't ship Tier 3 until Tier 2 has been observed for ≥ 3 months without
auto-merging.** Every autonomous-fix system that hasn't first passively
observed its trigger signal ends up auto-merging garbage during the first
weird outage.

## Recommended sequencing

1. ✅ **Tier 1 Passes 3f + 3h** — schema contract + collector errors. Covers the bad-FRED-ID and renamed-key bug classes.
2. ✅ **Tier 1 Pass 3g** — seed drift, narrow scope (FC_MACRO.actNN). Catches historical revisions of GDP/U/CPI/Wage/FFR seeds.
3. **Tier 1 Pass 3g extension — broaden coverage** (next). Currently only FC_MACRO is checked; extend to other "data-shaped" seeds like commentary numerics, panel KPI fallback values. Each addition is a small per-target function; aim for one new target per PR so each ships independently.
4. **Tier 1 Pass 3i — unit consistency.** Add a `units` map alongside the collector key list (`{'cpi_apparel': 'index', 'ig_oas': 'pct', ...}`). Renderer reads from it; rebuild functions assert expected unit. Estimated ~200 LOC plus per-series annotations.
5. ✅ **Agent 0 (pre-flight).** `scripts/preflight.py` runs as the first step in `briefing.yml`. Extracts every FRED series_id literal from `collector.py` and pings each one with limit=1. Any 4xx halts the pipeline before Agent 1 wastes a fetch. Defense-in-depth alongside Pass 3h: Agent 0 fails upstream, 3h surfaces anything that slipped through. Bypass for local dev: `PREFLIGHT_SKIP=1`.
6. **Agent 10 skeleton — passive observation only.** Cron that reads `validation_report.json` and posts a Slack/issue comment summarizing failures. **No fix-writing for at least 3 weeks** to confirm the trigger signal is clean.
7. **Agent 10 fix-proposal mode.** Add Claude API calls; produces draft PRs with `auto-fix-proposal` label. Human reviews each.
8. **Agent 10 auto-merge for narrow classes only.** Only ID swaps that re-fetch successfully. Always reversible. Always logged.

## Writing rules for the next contributor

When you add a new data series anywhere in the pipeline, make all three of
these true or the validator will fail your build:

1. **Collector writes the exact key the renderer reads.** Pass 3f enforces.
2. **Series has ≥13 obs for any YoY chart, ≥24 for any shock-tracker chart.** CLAUDE.md "Shock Tracker Data Contracts" section + the existing rebuild thresholds enforce.
3. **No FRED ID is added without verifying it returns ≥1 obs first.** Pass 3h surfaces 400s; future Agent 0 pre-flights it.

When you add a new chart const to `index.html`, prefer:
- A dynamic rebuild path in `renderer.py` over a static seed.
- If a static seed is unavoidable, add the const name to a `STATIC_SEEDS` allowlist so Pass 3g (when shipped) doesn't flag it.

## Audit history

Snapshot of bugs found and fixed on **2026-05-01**:

| Commit | Fix |
|---|---|
| `ae2576b` | PCE_CAT_MOM: 6 broken FRED IDs → 4 monthly aggregates |
| `b776c77` | CPI_CAT_MOM: 2 broken FRED IDs (Apparel/Energy) |
| `d8705cb` | FC_MACRO act25: GDP + FFR using non-existent keys |
| `8ad953a` | FC_MACRO multi-year + SPREADS_DATA monthly + shock-tracker margins |
| (this commit) | Validator Passes 3f + 3h + visual_qa import-time crash fix |

The cumulative effect: every documented seed value on the dashboard either
auto-rebuilds from data each run, or is flagged for review the moment it
diverges. Static seeds with no recompute path are now an active anti-pattern.
