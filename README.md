# U.S. Macro Dashboard

A single-page macro-economic dashboard covering 12 topics across the U.S. economy, updated daily via GitHub Actions and served on GitHub Pages.

**Live:** [amitb641.github.io/macro-dashboard](https://amitb641.github.io/macro-dashboard/)

---

## Dashboard Tabs

| Tab | What it covers |
|-----|---------------|
| **Outlook** | 2026 GDP scenarios, recession probabilities, institutional forecasts, key risks |
| **GDP** | Real GDP by quarter, 30+ sector cards with mini-charts, forecast table |
| **Jobs** | Nonfarm payrolls total and by sector, 2025 benchmark revision context |
| **Unemployment** | U-3 / U-6 rates, sector unemployment, trend pills |
| **Wages** | Average hourly earnings, real vs nominal growth, sector differentials |
| **CPI** | Headline & core CPI, 10 component categories, category comparison chart |
| **PCE & Consumer** | Core PCE (Fed's gauge), saving rate, household debt & delinquencies |
| **Fed Rates** | Fed funds rate history, FOMC dot plot, yield curve, card issuer funding & yield |
| **Credit** | Delinquency rates, net charge-offs, SLOOS lending standards, credit growth |
| **Banks** | Big 6 Q4 2025 earnings, NII guidance, charge-off outlook, commentary cards |
| **Housing** | Home prices, mortgage rates, starts, affordability, metro performance |
| **Oil** | WTI/Brent history, daily price tracker, inflation transmission chain, sector impact |

Plus two reference tabs: **Sources** (glossary & data dictionary) and **Dashboard** (data series catalog & freshness tracker).

---

## Methodology & Calibration

The Oil Impact Chain — the dashboard's shock-transmission tracker — is the most analytically consequential surface. Its confirmation rules (MMA thresholds, expected windows, pre-shock baselines) are specified explicitly and backtested.

- **[METHODOLOGY.md](METHODOLOGY.md)** — Per-phase specification for all 8 tracker phases: metric, FRED/BLS series ID, formula, confirmation thresholds, expected window, rationale, known limitations. Source of truth when any threshold changes.
- **[BACKTEST_REPORT.md](BACKTEST_REPORT.md)** — Phase rules replayed against 2022 Ukraine and 2008 Lehman-era oil shocks. Surfaces false positives and drives threshold calibration. Regenerated via the `Backtest — MMA Threshold Calibration` workflow.
- **v1.0.1 calibration fixes** (April 2026): Phase 3 window widened `[6,10]→[6,14]` based on 2022 Ukraine confirmation landing at +13w (CPI release lag); non-MMA phases switched to signed-chg so opposite-direction moves can't spuriously confirm.

---

## How It Works

A **9-agent pipeline** runs on two independent schedules:

**Main pipeline** (`briefing.yml` — weekly Fri 8am ET + monthly 2nd Sat):

```
Agent 1 — Collector       Pull latest data from FRED, BLS, EIA APIs (no LLM)
Agent 2 — Analyzer        Score risk signals, flag anomalies (no LLM)
Agent 3 — Analyst         AI commentary via Claude Sonnet
Agent 4 — Renderer        Patch live values into index.html charts/KPIs (no LLM)
Agent 5 — Publisher       Commit + email briefing via Resend (no LLM)
Agent 6 — Validator       6-pass build gate: data consistency, source verification,
                          staleness, shock-tracker structure, earnings factuality,
                          + Agent 7/8 reports (no LLM)
Agent 7 — Visual QA       Headless Chromium, 224 DOM checks (no LLM)
Agent 8 — Visual Review   Claude vision: per-tab screenshot defect detection
```

**Earnings pipeline** (`earnings_agent.yml` — quarterly, earnings-season daily at 10pm UTC, days 10-28 of Jan/Apr/Jul/Oct):

```
Agent 9 — Earnings Agent  Reads data/earnings_calendar.json → fetches each bank's
                          Q-transcript (IR site / Motley Fool / Seeking Alpha) →
                          Claude Sonnet extracts 8 verbatim fields with a strict
                          no-paraphrase schema → validator Pass 3c enforces that
                          every "…" quote appears verbatim in the archived
                          transcript → auto-commits to main when the gate passes,
                          halts silently when it doesn't.
                          Fully autonomous; never touches the weekly cadence.
```

The main workflow auto-commits updated `index.html` and `data/` files each run.
Agent 9 commits per bank with messages like `Agent 9: Q2 2026 — JPM, BAC reported
(auto-extracted)` so individual extractions are easy to revert.

---

## Repository Structure

```
index.html                  Single-page dashboard (HTML + CSS + JS + Chart.js)
CLAUDE.md                   Codebase guidelines (branch strategy, gotchas,
                            earnings factuality rule)
METHODOLOGY.md              Indicator definitions, formulas, thresholds,
                            validator-pass documentation
data/
  raw_data.json             Latest API responses from Agent 1
  signals.json              Risk signals and anomaly flags from Agent 2
  analysis.json             AI commentary from Agent 3
  bank_earnings.json        Source of truth for bank commentary cards; Agent 9
                            writes, renderer patches into index.html
  earnings_calendar.json    Agent 9 input: per-quarter bank dates + transcript URLs
  transcripts/<Q>/*.txt     Archived earnings transcripts — enables validator
                            verbatim gate
  validation_report.json    6-pass validator output (Agent 6)
  visual_qa_report.json     224-check DOM report (Agent 7)
  visual_review_report.json AI vision defect report (Agent 8)
  snapshots/                Rolling data backups (last 3 runs)
scripts/
  collector.py              Agent 1 — FRED / BLS / EIA data collection
  analyzer.py               Agent 2 — signal scoring and anomaly detection
  briefing_agent.py         Agent 3 — Claude AI commentary
  renderer.py               Agent 4 — patches live data into index.html
  publisher.py              Agent 5 — email briefing via Resend
  validator.py              Agent 6 — 6-pass quality gate
  visual_qa.py              Agent 7 — Playwright DOM checks
  visual_review.py          Agent 8 — Claude vision review
  earnings_agent.py         Agent 9 — autonomous quarterly earnings extraction
  snapshot.py               Rolling snapshots (keep last 3)
  healthcheck.py            Post-deploy verification
  version_tracker.py        Pipeline run audit trail
  seed_history.py           One-time backfill of historical chart arrays
.github/workflows/
  briefing.yml              Main pipeline (Agents 1-8, weekly + monthly)
  earnings_agent.yml        Agent 9 quarterly cron (earnings-season only)
  smoke-tests.yml           PR smoke tests
```

---

## Setup

### Prerequisites

- Python 3.11+
- API keys for FRED, BLS, EIA, Anthropic (Claude), and Resend

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `FRED_API_KEY` | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) key |
| `BLS_API_KEY` | [BLS API](https://www.bls.gov/developers/) registration key |
| `EIA_API_KEY` | [EIA API](https://www.eia.gov/opendata/) key |
| `ANTHROPIC_API_KEY` | Anthropic API key for Agent 3 (Claude commentary) |
| `RESEND_API_KEY` | [Resend](https://resend.com) API key for email delivery |
| `EMAIL_FROM` | Sender email address (verified in Resend) |
| `EMAIL_TO` | Recipient email address |

### Enable GitHub Pages

1. Go to **Settings > Pages**
2. Set source to **Deploy from a branch**
3. Select **main** branch, root (`/`)
4. The `.nojekyll` file is already present to skip Jekyll processing

### Run Manually

Trigger the workflow from **Actions > Daily Macro Update > Run workflow**. Check "Force Agent 3" to run AI commentary outside the 1st-of-month schedule.

---

## Data Sources

All data comes from U.S. federal agencies, regulatory filings, and publicly reported bank earnings:

- **BEA** — GDP, PCE, personal income
- **BLS** — CPI, employment, wages (CES & CPS)
- **EIA** — Oil prices, U.S. production
- **Federal Reserve** — Fed funds rate, Treasury yields, consumer credit (G.19), SLOOS
- **NY Fed** — Household debt & credit, recession probability model
- **FDIC** — Bank call reports, deposit data
- **Bank earnings transcripts** — 10 banks (JPM, BAC, WFC, C, GS, USB, COF, SYF, AXP, BCS) auto-fetched quarterly by **Agent 9** from IR sites / Motley Fool / Seeking Alpha. CEO quotes verified verbatim via validator Pass 3c (`scripts/validator.py:check_earnings_verbatim`). See the Earnings Commentary Factuality Rule in `CLAUDE.md` for provenance requirements.
- **Freddie Mac** — Primary Mortgage Market Survey
- **S&P / Case-Shiller** — Home price indices
- **Census Bureau** — Housing starts

Forecasts are from Goldman Sachs, JP Morgan, Morgan Stanley, Deloitte, EY-Parthenon, RSM, and Stanford SIEPR (Jan-Feb 2026).

---

## License

Data sourced from public U.S. government agencies and publicly reported corporate filings.
