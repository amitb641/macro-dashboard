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

## How It Works

A five-stage pipeline runs Mon-Fri at 7 AM ET via GitHub Actions:

```
Agent 1 — Collector    Pull latest data from FRED, BLS, and EIA APIs
Agent 2 — Analyzer     Score risk signals, flag anomalies
Agent 3 — Analyst      Monthly AI commentary via Claude (1st of month only)
Agent 4 — Renderer     Patch live values into index.html charts & KPIs
Agent 5 — Publisher    Send email briefing via Resend
```

The workflow auto-commits updated `index.html` and `data/` files on each run.

---

## Repository Structure

```
index.html                  Single-page dashboard (HTML + CSS + JS + Chart.js)
data/
  raw_data.json             Latest API responses from Agent 1
  signals.json              Risk signals and anomaly flags from Agent 2
  last_update.json          Run metadata, key values, timestamps
scripts/
  collector.py              Agent 1 — FRED / BLS / EIA data collection
  analyzer.py               Agent 2 — signal scoring and anomaly detection
  briefing_agent.py         Agent 3 — Claude AI monthly commentary
  renderer.py               Agent 4 — patches live data into index.html
  publisher.py              Agent 5 — email briefing via Resend
  seed_history.py           One-time script to backfill historical chart arrays
.github/workflows/
  briefing.yml              Daily cron workflow definition
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
- **Bank earnings** — JPM, BAC, WFC, C, GS, USB, COF, DFS, SYF, BFH, AXP, BCS Q4 2025
- **Freddie Mac** — Primary Mortgage Market Survey
- **S&P / Case-Shiller** — Home price indices
- **Census Bureau** — Housing starts

Forecasts are from Goldman Sachs, JP Morgan, Morgan Stanley, Deloitte, EY-Parthenon, RSM, and Stanford SIEPR (Jan-Feb 2026).

---

## License

Data sourced from public U.S. government agencies and publicly reported corporate filings.
