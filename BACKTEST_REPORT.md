# Backtest Calibration Report

Generated: 2026-04-20T15:52:32.083305Z

This report replays the current Oil Impact Chain confirmation rules
(see `METHODOLOGY.md`) against historical oil shocks to calibrate the
MMA thresholds (+1.5pp Confirmed, +0.5pp Emerging) and phase-timing windows.

⚠ Uses current revised FRED data, not as-of-snapshot vintages. See
`METHODOLOGY.md` §4 for the ALFRED vintage-pinning follow-up.

## 2022 Ukraine invasion

- Shock date: `2022-02-24`
- WTI pre-shock: $92.10
- WTI peak: $123.70 (+34%)
- Notes: Closest analog to 2026 scenario: post-pandemic demand + supply disruption.

Phase status by weeks-elapsed snapshot:

| Phase | Kind | +2w | +4w | +8w | +13w | +26w |
|---|---|---|---|---|---|---|
| Pump Prices Spike | level | ✅ confirmed | ✅ confirmed | ✅ confirmed | ✅ confirmed | 🟡 emerging |
| Transport & Freight | mma | 🔴 ahead | ✅ confirmed | ✅ confirmed | ✅ confirmed | ⏳ not_yet |
| CPI Energy Prints | mma | 🔴 ahead | 🔴 ahead | 🟦 on_schedule | ✅ confirmed | ⏳ not_yet |
| Food & Services | mma | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ✅ confirmed | ✅ confirmed |
| Core Goods Inflation | yoy | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | 🟦 on_schedule |
| Consumer Sentiment Falls | level | ✅ confirmed | ✅ confirmed | ⏳ not_yet | ✅ confirmed | ✅ confirmed |
| Savings Drawdown | level | 🔴 ahead | 🔴 ahead | ✅ confirmed | ✅ confirmed | ✅ confirmed |
| Delinquencies Climb | level | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ✅ confirmed |

<details><summary>Per-phase detail</summary>

### Pump Prices Spike (GASREGW)

- +2w (2022-03-10): **confirmed** · latest obs 2022-03-07 · pre_value=3.53 · now_value=4.102 · chg=0.57
- +4w (2022-03-24): **confirmed** · latest obs 2022-03-21 · pre_value=3.53 · now_value=4.239 · chg=0.71
- +8w (2022-04-21): **confirmed** · latest obs 2022-04-18 · pre_value=3.53 · now_value=4.066 · chg=0.54
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-23 · pre_value=3.53 · now_value=4.593 · chg=1.06
- +26w (2022-08-25): **emerging** · latest obs 2022-08-22 · pre_value=3.53 · now_value=3.88 · chg=0.35

### Transport & Freight (CUSR0000SETG)

- +2w (2022-03-10): **ahead** · latest obs 2022-03-01 · post_mma=82.7 · pre_6mma=3.0 · delta_pp=79.7
- +4w (2022-03-24): **confirmed** · latest obs 2022-03-01 · post_mma=82.7 · pre_6mma=3.0 · delta_pp=79.7
- +8w (2022-04-21): **confirmed** · latest obs 2022-04-01 · post_mma=287.9 · pre_6mma=3.0 · delta_pp=284.9
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-01 · post_mma=126.9 · pre_6mma=3.0 · delta_pp=123.9
- +26w (2022-08-25): **not_yet** · latest obs 2022-08-01 · post_mma=-35.4 · pre_6mma=3.0 · delta_pp=-38.4

### CPI Energy Prints (CPIENGSL)

- +2w (2022-03-10): **ahead** · latest obs 2022-03-01 · post_mma=216.9 · pre_6mma=30.8 · delta_pp=186.1
- +4w (2022-03-24): **ahead** · latest obs 2022-03-01 · post_mma=216.9 · pre_6mma=30.8 · delta_pp=186.1
- +8w (2022-04-21): **on_schedule** · latest obs 2022-04-01 · post_mma=-26.4 · pre_6mma=30.8 · delta_pp=-57.2
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-01 · post_mma=71.6 · pre_6mma=30.8 · delta_pp=40.8
- +26w (2022-08-25): **not_yet** · latest obs 2022-08-01 · post_mma=-46.6 · pre_6mma=30.8 · delta_pp=-77.4

### Food & Services (CUSR0000SEFV)

- +2w (2022-03-10): **not_yet** · latest obs 2022-03-01 · post_mma=3.1 · pre_6mma=7.6 · delta_pp=-4.5
- +4w (2022-03-24): **not_yet** · latest obs 2022-03-01 · post_mma=3.1 · pre_6mma=7.6 · delta_pp=-4.5
- +8w (2022-04-21): **not_yet** · latest obs 2022-04-01 · post_mma=7.2 · pre_6mma=7.6 · delta_pp=-0.4
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-01 · post_mma=9.2 · pre_6mma=7.6 · delta_pp=1.6
- +26w (2022-08-25): **confirmed** · latest obs 2022-08-01 · post_mma=10.9 · pre_6mma=7.6 · delta_pp=3.3

### Core Goods Inflation (CPILFESL)

- +2w (2022-03-10): **not_yet** · latest obs 2022-03-01 · yoy=6.5 · pre_yoy=6.5
- +4w (2022-03-24): **not_yet** · latest obs 2022-03-01 · yoy=6.5 · pre_yoy=6.5
- +8w (2022-04-21): **not_yet** · latest obs 2022-04-01 · yoy=6.2 · pre_yoy=6.5
- +13w (2022-05-26): **not_yet** · latest obs 2022-05-01 · yoy=6.0 · pre_yoy=6.5
- +26w (2022-08-25): **on_schedule** · latest obs 2022-08-01 · yoy=6.3 · pre_yoy=6.5

### Consumer Sentiment Falls (UMCSENT)

- +2w (2022-03-10): **confirmed** · latest obs 2022-03-01 · pre_value=62.8 · now_value=59.4 · chg=3.4
- +4w (2022-03-24): **confirmed** · latest obs 2022-03-01 · pre_value=62.8 · now_value=59.4 · chg=3.4
- +8w (2022-04-21): **not_yet** · latest obs 2022-04-01 · pre_value=62.8 · now_value=65.2 · chg=-2.4
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-01 · pre_value=62.8 · now_value=58.4 · chg=4.4
- +26w (2022-08-25): **confirmed** · latest obs 2022-08-01 · pre_value=62.8 · now_value=58.2 · chg=4.6

### Savings Drawdown (PSAVERT)

- +2w (2022-03-10): **ahead** · latest obs 2022-03-01 · pre_value=4.1 · now_value=3.2 · chg=0.9
- +4w (2022-03-24): **ahead** · latest obs 2022-03-01 · pre_value=4.1 · now_value=3.2 · chg=0.9
- +8w (2022-04-21): **confirmed** · latest obs 2022-04-01 · pre_value=4.1 · now_value=2.6 · chg=1.5
- +13w (2022-05-26): **confirmed** · latest obs 2022-05-01 · pre_value=4.1 · now_value=2.6 · chg=1.5
- +26w (2022-08-25): **confirmed** · latest obs 2022-08-01 · pre_value=4.1 · now_value=3.2 · chg=0.9

### Delinquencies Climb (DRCCLACBS)

- +2w (2022-03-10): **not_yet** · latest obs 2022-01-01 · pre_value=1.69 · now_value=1.69 · chg=0.0
- +4w (2022-03-24): **not_yet** · latest obs 2022-01-01 · pre_value=1.69 · now_value=1.69 · chg=0.0
- +8w (2022-04-21): **not_yet** · latest obs 2022-04-01 · pre_value=1.69 · now_value=1.83 · chg=0.14
- +13w (2022-05-26): **not_yet** · latest obs 2022-04-01 · pre_value=1.69 · now_value=1.83 · chg=0.14
- +26w (2022-08-25): **confirmed** · latest obs 2022-07-01 · pre_value=1.69 · now_value=2.05 · chg=0.36

</details>

## 2008 Oil crash (peak-to-trough)

- Shock date: `2008-07-01`
- WTI pre-shock: $90.00
- WTI peak: $145.29 (+61%)
- Notes: Inverse test case — prices collapsed into 2009. Tracker should NOT confirm ongoing shock transmission.

Phase status by weeks-elapsed snapshot:

| Phase | Kind | +2w | +4w | +8w | +13w | +26w |
|---|---|---|---|---|---|---|
| Pump Prices Spike | level | 🟦 on_schedule | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet |
| Transport & Freight | mma | 🔴 ahead | ✅ confirmed | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet |
| CPI Energy Prints | mma | 🔴 ahead | 🔴 ahead | 🟦 on_schedule | 🟦 on_schedule | ⏳ not_yet |
| Food & Services | mma | 🔴 ahead | 🔴 ahead | ⏳ not_yet | ✅ confirmed | ⏳ not_yet |
| Core Goods Inflation | yoy | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | 🟦 on_schedule |
| Consumer Sentiment Falls | level | 🟦 on_schedule | 🟦 on_schedule | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet |
| Savings Drawdown | level | 🔴 ahead | 🔴 ahead | ✅ confirmed | ✅ confirmed | ⏳ not_yet |
| Delinquencies Climb | level | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ⏳ not_yet | ✅ confirmed |

<details><summary>Per-phase detail</summary>

### Pump Prices Spike (GASREGW)

- +2w (2008-07-15): **on_schedule** · latest obs 2008-07-14 · pre_value=4.095 · now_value=4.113 · chg=0.02
- +4w (2008-07-29): **not_yet** · latest obs 2008-07-28 · pre_value=4.095 · now_value=3.955 · chg=-0.14
- +8w (2008-08-26): **not_yet** · latest obs 2008-08-25 · pre_value=4.095 · now_value=3.685 · chg=-0.41
- +13w (2008-09-30): **not_yet** · latest obs 2008-09-29 · pre_value=4.095 · now_value=3.632 · chg=-0.46
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-29 · pre_value=4.095 · now_value=1.613 · chg=-2.48

### Transport & Freight (CUSR0000SETG)

- +2w (2008-07-15): **ahead** · latest obs 2008-07-01 · post_mma=20.3 · pre_6mma=18.1 · delta_pp=2.2
- +4w (2008-07-29): **confirmed** · latest obs 2008-07-01 · post_mma=20.3 · pre_6mma=18.1 · delta_pp=2.2
- +8w (2008-08-26): **not_yet** · latest obs 2008-08-01 · post_mma=5.1 · pre_6mma=18.1 · delta_pp=-13.0
- +13w (2008-09-30): **not_yet** · latest obs 2008-09-01 · post_mma=-15.2 · pre_6mma=18.1 · delta_pp=-33.3
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-01 · post_mma=-18.2 · pre_6mma=18.1 · delta_pp=-36.3

### CPI Energy Prints (CPIENGSL)

- +2w (2008-07-15): **ahead** · latest obs 2008-07-01 · post_mma=50.4 · pre_6mma=34.9 · delta_pp=15.5
- +4w (2008-07-29): **ahead** · latest obs 2008-07-01 · post_mma=50.4 · pre_6mma=34.9 · delta_pp=15.5
- +8w (2008-08-26): **on_schedule** · latest obs 2008-08-01 · post_mma=-32.0 · pre_6mma=34.9 · delta_pp=-66.9
- +13w (2008-09-30): **on_schedule** · latest obs 2008-09-01 · post_mma=-10.6 · pre_6mma=34.9 · delta_pp=-45.5
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-01 · post_mma=-69.9 · pre_6mma=34.9 · delta_pp=-104.8

### Food & Services (CUSR0000SEFV)

- +2w (2008-07-15): **ahead** · latest obs 2008-07-01 · post_mma=7.9 · pre_6mma=4.6 · delta_pp=3.3
- +4w (2008-07-29): **ahead** · latest obs 2008-07-01 · post_mma=7.9 · pre_6mma=4.6 · delta_pp=3.3
- +8w (2008-08-26): **not_yet** · latest obs 2008-08-01 · post_mma=3.9 · pre_6mma=4.6 · delta_pp=-0.7
- +13w (2008-09-30): **confirmed** · latest obs 2008-09-01 · post_mma=6.6 · pre_6mma=4.6 · delta_pp=2.0
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-01 · post_mma=3.6 · pre_6mma=4.6 · delta_pp=-1.0

### Core Goods Inflation (CPILFESL)

- +2w (2008-07-15): **not_yet** · latest obs 2008-07-01 · yoy=2.5 · pre_yoy=2.4
- +4w (2008-07-29): **not_yet** · latest obs 2008-07-01 · yoy=2.5 · pre_yoy=2.4
- +8w (2008-08-26): **not_yet** · latest obs 2008-08-01 · yoy=2.5 · pre_yoy=2.4
- +13w (2008-09-30): **not_yet** · latest obs 2008-09-01 · yoy=2.4 · pre_yoy=2.4
- +26w (2008-12-30): **on_schedule** · latest obs 2008-12-01 · yoy=1.8 · pre_yoy=2.4

### Consumer Sentiment Falls (UMCSENT)

- +2w (2008-07-15): **on_schedule** · latest obs 2008-07-01 · pre_value=56.4 · now_value=61.2 · chg=-4.8
- +4w (2008-07-29): **on_schedule** · latest obs 2008-07-01 · pre_value=56.4 · now_value=61.2 · chg=-4.8
- +8w (2008-08-26): **not_yet** · latest obs 2008-08-01 · pre_value=56.4 · now_value=63.0 · chg=-6.6
- +13w (2008-09-30): **not_yet** · latest obs 2008-09-01 · pre_value=56.4 · now_value=70.3 · chg=-13.9
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-01 · pre_value=56.4 · now_value=60.1 · chg=-3.7

### Savings Drawdown (PSAVERT)

- +2w (2008-07-15): **ahead** · latest obs 2008-07-01 · pre_value=4.6 · now_value=3.6 · chg=1.0
- +4w (2008-07-29): **ahead** · latest obs 2008-07-01 · pre_value=4.6 · now_value=3.6 · chg=1.0
- +8w (2008-08-26): **confirmed** · latest obs 2008-08-01 · pre_value=4.6 · now_value=3.1 · chg=1.5
- +13w (2008-09-30): **confirmed** · latest obs 2008-09-01 · pre_value=4.6 · now_value=3.9 · chg=0.7
- +26w (2008-12-30): **not_yet** · latest obs 2008-12-01 · pre_value=4.6 · now_value=5.8 · chg=-1.2

### Delinquencies Climb (DRCCLACBS)

- +2w (2008-07-15): **not_yet** · latest obs 2008-07-01 · pre_value=4.9 · now_value=4.8 · chg=-0.1
- +4w (2008-07-29): **not_yet** · latest obs 2008-07-01 · pre_value=4.9 · now_value=4.8 · chg=-0.1
- +8w (2008-08-26): **not_yet** · latest obs 2008-07-01 · pre_value=4.9 · now_value=4.8 · chg=-0.1
- +13w (2008-09-30): **not_yet** · latest obs 2008-07-01 · pre_value=4.9 · now_value=4.8 · chg=-0.1
- +26w (2008-12-30): **confirmed** · latest obs 2008-10-01 · pre_value=4.9 · now_value=5.64 · chg=0.74

</details>

---

## Calibration observations

_Fill in after inspecting the tables above. Questions to answer:_

1. **Did Phase 3 (CPI Energy) confirm in the expected 6–10 week window** for
   the 2022 Ukraine shock?
2. **Did Phase 1 (Pump Prices) confirm within 2 weeks** in both shocks?
3. **Did the tracker correctly NOT confirm** phases during the 2008 post-peak
   collapse (where shock was peaking, not accelerating)?
4. **Were there phases that confirmed far outside their expected window** —
   suggesting the window needs adjustment?
5. **Were any thresholds obviously too tight or too loose** based on the
   magnitude of deltas observed?

If (1)–(4) all pass, current thresholds are defensible. If not, recalibrate
in `renderer.py:_mma_status` / `_status` and update `METHODOLOGY.md` §1.3.
