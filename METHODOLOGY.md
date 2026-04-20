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
| **Source** | FRED `CUSR0000SETG` (BLS CPI, seasonally adjusted) |
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
- **Agent 7 Visual QA** performs DOM-based rendering checks to confirm the
  page actually renders what the JSON says it should.
- **Agent 8 Visual Review** (when `ANTHROPIC_API_KEY` set) does vision-based
  review of rendered charts for visual defects.

---

## 4. Limitations of v1

- **No vintage pinning.** FRED / BLS both silently revise historical data.
  Charts labeled "historical" may change month-to-month. Future: snapshot
  ALFRED vintages at collect time and serve pinned vintages for historical
  panels.
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

## 5. Revision log

| Version | Date | Notes |
|---|---|---|
| v1.0 | 2026-04-20 | Initial methodology documentation. Oil Impact Chain phases fully specified. Backtest harness and ALFRED vintage pinning scheduled for v1.1. |
| v1.0.1 | 2026-04-20 | Calibration fixes from first backtest run (see `BACKTEST_REPORT.md`). Phase 3 (CPI Energy) expected window widened 6–10 → 6–14 to match observed 2022 Ukraine confirmation at +13w (CPI release lag). Non-MMA phases (§1.4) switched from `abs(chg)` to signed `chg` so opposite-direction moves no longer spuriously confirm — e.g. 2008 Core CPI deflation no longer marks "Confirmed" for an inflation shock. Smoothing of extreme MMA delta values deferred to v1.1. |
