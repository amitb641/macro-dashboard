# Methodology — Macro Dashboard

This document specifies how each indicator on the dashboard is computed,
sourced, and interpreted. It is the reference against which the code, the
validator, and the AI commentary should be checked.

Scope for v1: the Oil Impact Chain (SHOCK_TRACKER) — the dashboard's most
consequential analytical surface. Broader KPI methodology is covered in
passing; individual KPIs will get expanded sections in future revisions.

---

## 1. Oil Impact Chain — common framework

An oil shock is defined as a step change in WTI of >30% against the trailing
annual average. The current scenario is dated **2026-03-01** (hardcoded in
`scripts/renderer.py:update_shock_tracker` — the `shock_date` field in
`SHOCK_TRACKER`). Eight phases track how the shock propagates from pump
prices through to credit stress.

### 1.1 Pre-shock baselines

Each phase compares a post-shock reading to a pre-shock baseline. Baselines
are computed from the most recent observation **before** the shock date, not
from a fixed year. This is intentional: the tracker should ask "has the
series *changed from its pre-shock trajectory?*", not "has it changed from
2020?"

For series indexed by month-level dates, pre-shock = the most recent observation
with `date < 2026-03-01` (so Feb 2026 data points for the current scenario).

### 1.2 Rate-of-change methodology (MMA)

Three phases use **MMA** (Moving Monthly-rate Annualized) for confirmation,
not YoY. Rationale: YoY is contaminated by the year-ago base, so a single
anomalous month 12 periods prior can flip "Not Yet" to "Confirmed" for
reasons unrelated to the shock. MMA compares recent monthly pace to the
pre-shock monthly trajectory, which is what actually moves when transmission
happens.

Two formulas:

```
post-shock pace      = (V_latest / V_prior)^12 − 1          (annualized)
pre-shock 6-MMA      = (V_pre / V_pre_minus_6)^(12/6) − 1   (annualized)
delta (signed)       = post_pace − pre_6MMA
```

`V_pre` is the most recent observation before the shock date. `V_pre_minus_6`
is 6 months earlier than that.

### 1.3 Confirmation tiers (MMA phases)

| Status | Condition | Visual |
|---|---|---|
| **Confirmed** | delta > +1.5pp AND (in or past expected window) | green pill |
| **Emerging** | +0.5 < delta ≤ +1.5pp AND (in or past expected window) | amber pill |
| **Ahead** | delta > +0.5pp AND before expected window | red pill — unusual early signal |
| **On Track** | in expected window, delta ≤ +0.5pp | blue pill |
| **Not Yet** | before window OR delta non-positive (inflation phases don't confirm on deceleration) | gray pill |
| **Awaiting Data** | insufficient history (e.g. <7 obs for MMA) | purple pill |

**Signed delta matters**: an inflation phase decelerating vs. pre-shock
pace does *not* confirm the shock, even if the magnitude exceeds thresholds.

### 1.4 Confirmation tiers (non-MMA phases)

Phases 1 (Pump Prices), 5 (Core CPI), 6 (Sentiment), 7 (Savings), 8
(Delinquencies) use a signed-delta rule against the pre-shock baseline:

```
chg = (now − pre) * sign           # sign = −1 for drop-expected phases
moved = chg > 0.15                 # sub-threshold gate, SIGNED
confirmed = moved AND (in/past window) AND chg > 0.5
```

`chg` is **signed**, not absolute. Opposite-direction moves never confirm,
even if their magnitude exceeds the threshold. This prevents the tracker
from marking "Confirmed" when a series moves the *wrong* way relative to
shock expectations. Historical example: during the 2008 oil crash, Core CPI
*dropped* 0.6pp from demand destruction + Lehman stress. An `abs(chg)`
check would have marked Phase 5 "Confirmed" for inflation transmission —
misleading, since the mechanism is deflationary. The signed rule correctly
leaves it at `not_yet`. Drop-expected phases (Sentiment, Savings) handle
direction via `sign=-1` so a shock-consistent drop still produces positive
`chg`.

### 1.5 Base-effect auto-flag

On MMA phases, when YoY delta is large (> +1.5pp) but MMA delta is small
(< +1.0pp), the popover emits an amber callout explaining the YoY reading
is base-effect contaminated. Triggered in `_base_effect_note()` in
`renderer.py`. Real example: Transport Services YoY spiked 5.0% → 10.2%
(+5.2pp) in Mar'26 *despite* monthly pace being unchanged — because Mar'25
was a local trough.

---

## 2. Oil Impact Chain — per-phase specifications

### Phase 1: Pump Prices Spike

| | |
|---|---|
| **Metric** | Gasoline retail price, $/gal |
| **Source** | FRED `GASREGW` (EIA weekly retail gasoline, all grades, all formulations) |
| **Cadence** | Weekly, Monday reference date |
| **Collector fetch** | 30 observations (`collector.py:204`) |
| **Pre-shock baseline** | Last weekly observation before 2026-03-01 |
| **Formula** | `chg = latest_price - pre_shock_price` |
| **Confirmation threshold** | |chg| > $0.50 /gal (~15% of baseline) |
| **Expected window** | Weeks 0–2 post-shock (days 1–14) |
| **Rationale** | WTI → retail pass-through is mechanically fast. The rule-of-thumb is $0.024/gal per $1/bbl of sustained WTI move (~$0.24 per $10/bbl). Refiner margins buffer 5–10 days; full pass-through by week 2. |
| **Known limitations** | Regional variation; state taxes; refinery outages can amplify pass-through beyond the rule-of-thumb. |

### Phase 2: Transport & Freight Costs

| | |
|---|---|
| **Metric** | CPI Transportation Services YoY % |
| **Source** | FRED `CUSR0000SAS4` (BLS CPI, seasonally adjusted) — corrected 2026-07-25 from `CUSR0000SETG` ("Public Transportation", a narrower airfare/transit-heavy basket that had been mislabeled as this broader category since the phase was built; the coverage description below was already written for the correct broader concept, only the series ID was wrong) |
| **Cadence** | Monthly, 2nd week of following month |
| **Collector fetch** | 24 observations (`collector.py:336`) |
| **Coverage** | Airline fares, intracity transit, vehicle insurance, vehicle maintenance, vehicle leasing. Does **not** cover freight trucking rates (see limitations). |
| **Confirmation** | MMA (section 1.2–1.3). Post-shock pace vs. pre-shock 6-MMA, annualized. |
| **Expected window** | Weeks 4–6 |
| **Rationale** | Airfare fuel surcharges reprice on 2–4 week cycles; auto insurance renewals flow through over 4–8 weeks as replacement-part costs rise. |
| **Known limitations** | The "Freight" in the UI label is a misnomer — a true freight-rate series (Cass Freight Index) would need a separate source. Insurance pass-through is lagged by the insurance regulation calendar in some states. |

### Phase 3: CPI Energy Prints

| | |
|---|---|
| **Metric** | CPI Energy YoY % |
| **Source** | FRED `CPIENGSL` (BLS CPI Energy, seasonally adjusted) |
| **Cadence** | Monthly, mid-month |
| **Collector fetch** | 320 observations |
| **Composition** | Gasoline (~65% weight), natural gas, fuel oil, electricity |
| **Confirmation** | MMA (section 1.2–1.3) |
| **Expected window** | Weeks 6–14 |
| **Rationale** | First full BLS capture of post-shock gasoline prices lands in the CPI print covering the first fully-post-shock reference month (Mar 2026 data, published ~April 10). Headline inflation becomes "official" here. Window widened from 6–10 to 6–14 based on 2022 Ukraine backtest: CPI release lag (~4-6 weeks) means the April CPI print (at ~week 7) often misses threshold, with confirmation arriving in the May print (~week 13). |
| **Known limitations** | Natural gas and electricity components move on longer cycles (utility filings), so the initial CPI Energy move will be gasoline-dominated. A second-wave component from utilities shows up 2–4 months later. |

### Phase 4: Food & Services Inflation

| | |
|---|---|
| **Metric** | CPI Food Away from Home YoY % |
| **Source** | FRED `CUSR0000SEFV` (BLS CPI, seasonally adjusted) |
| **Cadence** | Monthly |
| **Collector fetch** | 24 observations |
| **Coverage** | Restaurant meals, cafeteria meals, beverages at food-service establishments |
| **Confirmation** | MMA (section 1.2–1.3) |
| **Expected window** | Months 3–5 (weeks 12–20) |
| **Rationale** | Restaurant menus reprice on a 60–90 day cycle. Energy-cost pass-through to food prices goes via transport (Phase 2) and ingredient inputs, both of which are lagged. |
| **Known limitations** | Labor costs are the dominant driver of food-away inflation, with energy a secondary input. A pure oil-shock transmission signal is harder to isolate here than in Phases 1–3. |

### Phase 5: Core Goods Inflation

| | |
|---|---|
| **Metric** | Core CPI YoY % (CPI ex-Food & Energy) |
| **Source** | FRED `CPILFESL` → `data['core_cpi_yoy']` (scalar, derived in analyzer) |
| **Cadence** | Monthly |
| **Pre-shock baseline** | 2.5% (hardcoded to Feb 2026 reading) |
| **Confirmation threshold** | \|chg\| > 0.5pp within/past window |
| **Expected window** | Months 5–8 (weeks 20–32) |
| **Rationale** | Energy cost pass-through to manufacturing (chemicals, plastics, packaging) takes 5–8 months as inventories unwind and new procurement cycles at post-shock prices feed into retail pricing. |
| **Known limitations** | Core CPI is noisy at the pp level; a 0.5pp threshold will catch real transmission but also any shelter/services surprise. Supplement with PPI pass-through tracking in future revisions. |

### Phase 6: Consumer Sentiment Falls

| | |
|---|---|
| **Metric** | UMich Index of Consumer Sentiment |
| **Source** | `sca.isr.umich.edu/files/tbcics.csv` direct (preliminary mid-month + final end-of-month), with FRED `UMCSENT` as fallback for history |
| **Cadence** | Monthly, with preliminary release ~mid-month and final end-of-month |
| **Status field** | Each observation carries `status: "preliminary"` or `"final"`; `(P)` marker in the UMich CSV is the trigger |
| **Pre-shock baseline** | 56.6 (Feb 2026 reading, hardcoded) |
| **Confirmation threshold** | drop > 0.5pt within/past window |
| **Expected window** | Weeks 2–6 |
| **Rationale** | Consumer psychology responds to visible-at-the-pump prices within a news cycle. UMich captures this faster than spending behavior does. |
| **Known limitations** | UMich often overshoots actual spending changes; "sentiment fall" is a leading indicator of perception more than behavior. Preliminary vs final revisions typically run 1–3 points in either direction. |

### Phase 7: Savings Drawdown

| | |
|---|---|
| **Metric** | Personal Saving Rate, % of disposable income |
| **Source** | FRED `PSAVERT` (BEA) |
| **Cadence** | Monthly, released ~1 month after reference period |
| **Pre-shock baseline** | 4.5% (hardcoded) |
| **Confirmation threshold** | drop > 0.5pp within/past window |
| **Expected window** | Months 2–4 (weeks 8–16) |
| **Rationale** | Fuel costs compress take-home pay over 1–2 months as higher gasoline spending crowds out discretionary saving. |
| **Known limitations** | Saving rate is revision-heavy (BEA revises back 3+ years on annual methodology updates). Low-saving-rate scenarios (<3%) make the 0.5pp threshold noisy. |

### Phase 8: Delinquencies Climb

| | |
|---|---|
| **Metric** | Credit Card 90+ Day Delinquency Rate, % |
| **Source** | FRED `DRCCLACBS` (Federal Reserve, quarterly call reports) |
| **Cadence** | Quarterly, ~45-day lag after quarter end |
| **Collector fetch** | 108 observations (~27 years, wired in for full historical card90 line) |
| **Pre-shock baseline** | 2.94% (latest Q3'25 reading at time of shock) |
| **Confirmation threshold** | increase > 0.15pp within/past window |
| **Expected window** | Months 5–10 (weeks 20–40) |
| **Rationale** | Credit stress surfaces in 2–3 quarters as consumers exhaust savings buffers (Phase 7) and roll higher-balance revolving debt. Subprime first, prime 1–2 quarters later. |
| **Known limitations** | Quarterly cadence means the first post-shock read is Q3'26 release (~Nov 2026). Structural delinquency levels vary with the credit cycle — a 2.94% baseline in a tight labor market is different from the same level in a softening labor market. |

---

## 3. Data quality controls

- **Pre-render collector run** validates that each FRED call returned ≥1 observation;
  failures append to `errors` list in `raw_data.json`.
- **Validator Pass 1** (`scripts/validator.py:check_internal`) verifies every
  chart constant in index.html deserializes as JSON, has matching labels/data
  lengths, and completeness ≥ threshold (default 50%, see SPARSE_OK overrides).
- **Validator Pass 2** (`check_sources`) spot-checks 10 headline values
  against fresh FRED/BLS API calls with per-type tolerances.
- **Validator Pass 3** (`check_staleness`) flags series that haven't updated
  within their expected release cadence, calibrated to actual BLS/BEA
  publication schedules.
- **Validator Pass 3b** (`check_shock_tracker`) verifies SHOCK_TRACKER structure,
  required fields per phase, and status-vs-MMA consistency (confirmed phases
  must have delta > 1.5pp, etc.).
- **Validator Pass 3c** (`check_earnings_verbatim`) enforces the earnings
  commentary factuality rule: every `"…"` substring in each field of
  `data/bank_earnings.json` must appear verbatim (modulo smart-quote /
  dash / whitespace normalization) in the archived transcript at
  `data/transcripts/<Quarter>/<TICKER>.txt`. A mismatch is CRITICAL severity
  and blocks publish. Missing transcript → WARNING (enables gradual adoption;
  content still ships but un-gated). This is the mechanical guardrail that
  makes Agent 9's autonomous extraction safe — Claude can't fabricate a quote
  and have it merge, because the validator would catch it first.
- **Agent 7 Visual QA** performs DOM-based rendering checks to confirm the
  page actually renders what the JSON says it should.
- **Agent 8 Visual Review** (when `ANTHROPIC_API_KEY` set) does vision-based
  review of rendered charts for visual defects.

---

## 4. Limitations of v1

- **Vintage pinning — proof-of-concept only.** v1.0.2 pins the real GDP
  historical series (`gdpc1_annual`) to an ALFRED as-of-vintage date so
  the 25-year metric tiles don't shift on BEA benchmark revisions.
  Remaining series (nominal GDP, CPI, payrolls, PCE, etc.) still use
  latest revised values. Full rollout across all Tier 1 headline series
  is scheduled for v1.1. See §5 for the current scope.
- **Single-scenario backtest.** Current MMA thresholds (1.5pp confirmed,
  0.5pp emerging) are intuitive but not historically calibrated. Pending:
  `scripts/backtest_shock.py` against 2022 Ukraine, 2008 Lehman-era, 1990
  Gulf, 1979 Iran, 1973 OPEC shocks.
- **Hardcoded shock date.** The 2026-03-01 date in `update_shock_tracker`
  is scenario-specific. Future: make shock date a parameter, support
  multi-shock timelines.
- **Single data source per series.** No triangulation (e.g. FRED + Haver
  cross-check). A single FRED outage degrades the dashboard.
- **No stated prior.** The shock-phase lags (weeks 4–6 for Transport, etc.)
  are drawn from academic/industry rules-of-thumb, not from a specific
  published model. Backtest will tell us whether these windows are accurate.

---

## 5. Vintage pinning (v1.0.2 proof-of-concept)

### The problem

FRED and the underlying BEA / BLS sources silently revise historical data.
BEA publishes annual and comprehensive benchmark revisions that can move
GDP levels back five or more years. BLS does annual benchmark revisions
for payrolls. A chart labeled "historical" on the dashboard today may
show different values next month — a credibility risk when a reviewer
asks "didn't GDP show 2.1% last week and now shows 1.9%?"

### The fix

ALFRED (Archival FRED) exposes FRED data as-of any historical publication
date. By fetching observations with `realtime_start = realtime_end =
<vintage_date>`, we get the values exactly as they were published on
that date — frozen against subsequent revisions.

### Current scope

Pinned series (all share the same pin date within a cycle):
- **GDPC1 annual** (real GDP) — annual aggregate chart
- **GDP annual** (nominal GDP) — annual aggregate chart; keeps real/nominal
  deflator math consistent within a pin cycle
- **CPIAUCSL monthly** (headline CPI) — drives CPI_ANNUAL Dec-to-Dec YoY
- **PAYEMS monthly** (total nonfarm payrolls) — drives JOBS_ANNUAL (protects
  against BLS annual benchmark revisions, which have rewritten ~862K jobs
  across 10 months in past cycles)
- **AHETPI monthly** (avg hourly earnings) — drives WAGE_ANNUAL (nominal +
  real-wage lines)
- **PCEPI monthly** (PCE price index, headline) — drives PCE_ANNUAL headline
- **PCEPILFE monthly** (core PCE) — drives PCE_ANNUAL core; Fed's preferred
  inflation gauge, subject to periodic BEA comprehensive revisions

Pin cadence is **quarterly** — pin date refreshes to the previous quarter
end at each new quarter (Q2 pins to Mar 31, Q3 pins to Jun 30, etc.).
This gives within-quarter stability while still capturing new data
releases at quarterly natural boundaries.

**Current-period KPIs and monthly/YoY charts continue reading live
(unpinned) data.** The pin applies only to the historical-aggregate
computations, so the dashboard still updates on the latest BLS/BEA release
for headline numbers, with historical lines held stable within a quarter.

Data flow:
- `scripts/collector.py:fred_alfred_obs()` pulls the vintage-pinned
  observations
- `data/raw_data.json` carries two parallel arrays:
  `gdpc1_annual` (live, latest revised) for KPI current-period values
  and `gdpc1_annual_pinned` (vintage-pinned) for the 25-year historical
  series used in metric-tile computations
- `data['vintages']` records the pin date and cadence
- `scripts/renderer.py` prefers pinned data for `GDP_TOTAL_DATA`, falls
  back to live data if the pinned fetch returned empty
- `GDP_VINTAGE_INFO` constant in `index.html` surfaces the pin date as a
  footnote below the GDP metric tiles

### Expansion plan (v1.1)

Pin the remaining headline series that show ≥5-year historical chart
surfaces: CPI annual, unemployment annual, wage annual, PCE annual,
Fed funds annual. Each expansion requires a parallel `<series>_pinned`
data array + renderer fallback. No methodology change — same pin cadence,
same ALFRED helper.

### Not pinned (intentionally)

- Current-period KPIs — latest revised is what institutional consumers
  quote in real time.
- Shock-tracker phases — these explicitly model "how has the world
  changed since the shock date," so they need the latest data, not a
  pre-shock snapshot of history.
- High-frequency daily series (WTI, Treasury yields) — ALFRED vintage
  coverage is coarser (weekly-ish) and the revision risk for daily
  market prices is effectively zero.

---

## 6. Revision log

| Version | Date | Notes |
|---|---|---|
| v1.0 | 2026-04-20 | Initial methodology documentation. Oil Impact Chain phases fully specified. Backtest harness and ALFRED vintage pinning scheduled for v1.1. |
| v1.0.1 | 2026-04-20 | Calibration fixes from first backtest run (see `BACKTEST_REPORT.md`). Phase 3 (CPI Energy) expected window widened 6–10 → 6–14 to match observed 2022 Ukraine confirmation at +13w (CPI release lag). Non-MMA phases (§1.4) switched from `abs(chg)` to signed `chg` so opposite-direction moves no longer spuriously confirm — e.g. 2008 Core CPI deflation no longer marks "Confirmed" for an inflation shock. Smoothing of extreme MMA delta values deferred to v1.1. |
| v1.0.2 | 2026-04-20 | Vintage pinning proof-of-concept (§5). GDP annual (`gdpc1_annual`) now pinned to ALFRED as-of previous quarter-end via new `fred_alfred_obs()` collector helper. Renderer prefers pinned data with fallback to live. `GDP_VINTAGE_INFO` footnote surfaces the pin date on the GDP tab. Establishes the pattern for rolling out to other Tier 1 headline series in v1.1. |
| v1.0.3 | 2026-04-20 | JSON-blob data-layout proof-of-concept. `VALIDATION_REPORT` removed from inline `index.html` (-45KB) and now fetched at runtime from `data/validation_report.json` via a cached `fetchValidationReport()` helper. Cache is warmed at page load so tab-click and download-all capture see an already-resolved promise. Graceful failure mode: dedicated error panel if the fetch fails. Establishes the decoupled data/UI pattern for rolling out to the remaining ~40 inline constants in v1.2. `scripts/visual_qa.py` updated to await the fetch (async evaluate + `page.route` interception for file://-protocol CORS). |
| v1.0.4 | 2026-04-20 | Vintage pin expanded to nominal GDP (`gdp_annual`). Closes a latent inconsistency in v1.0.2 where only the real line was pinned — any BEA revision to nominal GDP would have caused the real/nominal deflator to drift within a pin cycle. Both series now share the same pin date, rebuilt together each quarter. Pattern scales cleanly: each additional series needs one `fred_alfred_obs()` call + one line in the vintages dict + one renderer `or` fallback. |
| v1.0.5 | 2026-04-20 | Vintage pin expanded to three Tier 1 monthly series feeding the long-history annual-aggregate charts: `cpi_all` (→ CPI_ANNUAL), `payems` (→ JOBS_ANNUAL), `ahetpi` (→ WAGE_ANNUAL). Rationale: these all pass through BLS annual benchmark and seasonal-adjustment revisions (the 2025 payroll benchmark alone rewrote ~862K jobs); the long chart surface now stays stable within each quarterly pin cycle. Current-period KPIs and 12-month mini-charts continue reading live data so freshness is unaffected. |
| v1.0.6 | 2026-04-20 | Vintage pin expanded to PCE headline (`pce`) and core (`pce_core`). Fed's preferred inflation gauge; BEA does periodic methodology updates (most recently 2023 comprehensive revision) that restate multi-year history. PCE_ANNUAL chart now stays stable within a pin cycle. Brings the total pinned-series count to 7 (real + nominal GDP, CPI, payrolls, wages, PCE headline + core). |
| v1.0.7 | 2026-04-20 | Surface vintage-pin state to users. Added `<p class="src vintage-note">` footnotes beneath the metric rows on the GDP (already had one), CPI, Jobs, Wages, and PCE tabs. A single page-load init populates all `.vintage-note` elements from the shared `GDP_VINTAGE_INFO` constant, so users see "Annual-chart data vintage: pinned to ALFRED as-of 2026-03-31 · refresh cadence: quarterly…" on every long-history chart surface. Makes the credibility work visible — previously only the GDP tab advertised the pin. |
| v1.0.8 | 2026-04-24 | Headline wage-growth source changed from BLS AHETPI YoY → Atlanta Fed Wage Growth Tracker 3MMA (`FRBATLWGT3MMAUMHWGO`). AHETPI computes YoY from an aggregate level and is biased by composition effects (a wave of lower-paid workers entering the survey drags the number down even if individual raises are unchanged). Atlanta Fed's tracker follows the same workers over 12 months and reports their actual wage change — the right measure for "are workers' wages growing?". AHETPI retained for the historical annual chart (WAGE_ANNUAL, long BLS history) and for the sector breakdown table (Atlanta Fed has no sector decomposition). Renderer falls back to AHETPI-YoY if the Atlanta Fed series hasn't been collected yet. |
