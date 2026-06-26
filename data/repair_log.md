## Repair Agent — 2026-06-26T13:13:40.518230Z

- **Status**: PASS
- **Total checks**: 649
- **Passed**: 649
- **Failed**: 0
- **Critical divergences**: 0

No findings to surface — pipeline is clean. ✅

---

## Repair Agent — 2026-06-20T13:23:15.814733Z

- **Status**: PASS
- **Total checks**: 649
- **Passed**: 649
- **Failed**: 0
- **Critical divergences**: 0

No findings to surface — pipeline is clean. ✅

---

## Repair Agent — 2026-06-13T13:21:13.791988Z

- **Status**: PASS
- **Total checks**: 649
- **Passed**: 649
- **Failed**: 0
- **Critical divergences**: 0

No findings to surface — pipeline is clean. ✅

---

## Repair Agent — 2026-06-08T03:35:28.722048Z

- **Status**: WARN
- **Total checks**: 649
- **Passed**: 648
- **Failed**: 1
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 38d old (limit 35d)


---

## Repair Agent — 2026-06-08T03:30:34.447432Z

- **Status**: WARN
- **Total checks**: 649
- **Passed**: 648
- **Failed**: 1
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 38d old (limit 35d)


---

## Repair Agent — 2026-06-04T06:08:39.272645Z

- **Status**: PASS
- **Total checks**: 649
- **Passed**: 649
- **Failed**: 0
- **Critical divergences**: 0

No findings to surface — pipeline is clean. ✅

---

## Repair Agent — 2026-06-04T05:59:16.291196Z

- **Status**: WARN
- **Total checks**: 649
- **Passed**: 647
- **Failed**: 2
- **Critical divergences**: 0

### Collector errors
_0 critical · 1 warning · 0 stale_

- ⚠️ **Collector error** — UMich direct: 403 Client Error: Forbidden for url: https://www.sca.isr.umich.edu/files/tbcics.csv

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 64d old (limit 35d)


---

## Repair Agent — 2026-06-04T05:44:14.346070Z

- **Status**: PASS
- **Total checks**: 649
- **Passed**: 649
- **Failed**: 0
- **Critical divergences**: 0

No findings to surface — pipeline is clean. ✅

---

## Repair Agent — 2026-06-04T05:30:18.880918Z

- **Status**: WARN
- **Total checks**: 651
- **Passed**: 646
- **Failed**: 5
- **Critical divergences**: 1

### Collector errors
_0 critical · 3 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **Collector error** — UMich direct: 403 Client Error: Forbidden for url: https://www.sca.isr.umich.edu/files/tbcics.csv

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 64d old (limit 35d)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-06-04T05:02:23.074788Z

- **Status**: WARN
- **Total checks**: 651
- **Passed**: 646
- **Failed**: 5
- **Critical divergences**: 1

### Collector errors
_0 critical · 3 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **Collector error** — UMich direct: 403 Client Error: Forbidden for url: https://www.sca.isr.umich.edu/files/tbcics.csv

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 64d old (limit 35d)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-06-04T04:49:30.125600Z

- **Status**: WARN
- **Total checks**: 651
- **Passed**: 646
- **Failed**: 5
- **Critical divergences**: 1

### Collector errors
_0 critical · 3 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **Collector error** — UMich direct: 403 Client Error: Forbidden for url: https://www.sca.isr.umich.edu/files/tbcics.csv

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 64d old (limit 35d)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-06-04T04:35:19.095014Z

- **Status**: WARN
- **Total checks**: 650
- **Passed**: 647
- **Failed**: 3
- **Critical divergences**: 1

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — 504 Server Error: Gateway Timeout for url: https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=[REDACTED]&frequency=daily&data%5B0%5D=value&facets%5Bseries%5D%5B%5D=RWTC&sort%5B0%5D%5Bcolumn%5D=period&sort%5B0%5D%5Bdirection%5D=desc&length=60
- ⚠️ **EIA fetch: RBRTE** — 504 Server Error: Gateway Timeout for url: https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=[REDACTED]&frequency=daily&data%5B0%5D=value&facets%5Bseries%5D%5B%5D=RBRTE&sort%5B0%5D%5Bcolumn%5D=period&sort%5B0%5D%5Bdirection%5D=desc&length=60

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-06-04T03:48:46.265473Z

- **Status**: WARN
- **Total checks**: 647
- **Passed**: 644
- **Failed**: 3
- **Critical divergences**: 1

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-06-04T03:30:27.043994Z

- **Status**: WARN
- **Total checks**: 648
- **Passed**: 641
- **Failed**: 7
- **Critical divergences**: 1

### Collector errors
_0 critical · 3 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **Collector error** — UMich direct: 403 Client Error: Forbidden for url: https://www.sca.isr.umich.edu/files/tbcics.csv

### Internal consistency
_0 critical · 1 warning · 0 stale_

- ⚠️ **NFP_VS_ADP.adp completeness** — 

### Staleness
_0 critical · 0 warning · 1 stale_

- ⏰ **Staleness: umcsent** — 64d old (limit 35d)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 

### Visual QA
_0 critical · 1 warning · 0 stale_

- ⚠️ **Visual: data — NFP_VS_ADP.adp completeness** — 


---

## Repair Agent — 2026-05-30T19:34:50.869536Z

- **Status**: WARN
- **Total checks**: 641
- **Passed**: 638
- **Failed**: 3
- **Critical divergences**: 1

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 

### Visual QA
_0 critical · 2 warning · 0 stale_

- ⚠️ **Visual: global — Hydration: all Tier-1 keys present** — 
- ⚠️ **Visual: data — NFP_VS_ADP defined** — 


---

## Repair Agent — 2026-05-30T17:51:43.370784Z

- **Status**: WARN
- **Total checks**: 643
- **Passed**: 642
- **Failed**: 1
- **Critical divergences**: 1

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-30T17:22:34.288402Z

- **Status**: WARN
- **Total checks**: 643
- **Passed**: 642
- **Failed**: 1
- **Critical divergences**: 1

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-29T05:01:44.126282Z

- **Status**: WARN
- **Total checks**: 643
- **Passed**: 642
- **Failed**: 1
- **Critical divergences**: 1

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-29T01:47:20.762887Z

- **Status**: WARN
- **Total checks**: 720
- **Passed**: 641
- **Failed**: 79
- **Critical divergences**: 1

### Collector errors
_0 critical · 78 warning · 0 stale_

- ⚠️ **FRED fetch: DFF** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: DGS2** — 504 Server Error: Gateway Time-out for url: https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key=[REDACTED]&file_type=json&sort_order=desc&limit=14
- ⚠️ **FRED fetch: DGS5** — 504 Server Error: Gateway Time-out for url: https://api.stlouisfed.org/fred/series/observations?series_id=DGS5&api_key=[REDACTED]&file_type=json&sort_order=desc&limit=14
- ⚠️ **FRED fetch: DGS10** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: DGS30** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: DGS10** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: DGS2** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: BAMLC0A0CM** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: BAMLH0A0HYM2** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- ⚠️ **FRED fetch: BAMLC0A0CM** — HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Read timed out. (read timeout=15)
- _… and 68 more_

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-28T17:56:28.426908Z

- **Status**: WARN
- **Total checks**: 643
- **Passed**: 642
- **Failed**: 1
- **Critical divergences**: 1

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-28T13:05:16.113911Z

- **Status**: WARN
- **Total checks**: 643
- **Passed**: 640
- **Failed**: 3
- **Critical divergences**: 1

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_1 critical · 0 warning · 0 stale_

- 🔴 **Energy and housing components are pulling the PCE basket higher: title months match PCE_CAT_MOM keys** — 


---

## Repair Agent — 2026-05-28T05:45:53.352154Z

- **Status**: WARN
- **Total checks**: 644
- **Passed**: 640
- **Failed**: 4
- **Critical divergences**: 0

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)


---

## Repair Agent — 2026-05-28T05:32:58.663940Z

- **Status**: WARN
- **Total checks**: 644
- **Passed**: 640
- **Failed**: 4
- **Critical divergences**: 0

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)


---

## Repair Agent — 2026-05-28T05:01:57.380373Z

- **Status**: WARN
- **Total checks**: 635
- **Passed**: 628
- **Failed**: 7
- **Critical divergences**: 0

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-28T04:47:25.560724Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 627
- **Failed**: 7
- **Critical divergences**: 0

### Collector errors
_0 critical · 1 warning · 0 stale_

- ⚠️ **Collector error** — ALFRED PCEPILFE@2026-03-31: 429 Client Error: Too Many Requests for url: https://api.stlouisfed.org/fred/series/observations?series_id=PCEPILFE&api_key=[REDACTED]&file_type=json&sort_order=desc&limit=480&realtime_start=2026-03-31&realtime_e

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML

### Visual QA
_0 critical · 1 warning · 0 stale_

- ⚠️ **Visual: contract — spacing_grid** — 


---

## Repair Agent — 2026-05-28T04:33:45.286272Z

- **Status**: WARN
- **Total checks**: 635
- **Passed**: 627
- **Failed**: 8
- **Critical divergences**: 0

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML

### Visual QA
_0 critical · 1 warning · 0 stale_

- ⚠️ **Visual: contract — spacing_grid** — 


---

## Repair Agent — 2026-05-28T02:32:20.729186Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 628
- **Failed**: 6
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML

### Visual QA
_0 critical · 1 warning · 0 stale_

- ⚠️ **Visual: contract — spacing_grid** — 


---

## Repair Agent — 2026-05-28T01:28:19.911358Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 628
- **Failed**: 6
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML

### Visual QA
_0 critical · 1 warning · 0 stale_

- ⚠️ **Visual: contract — spacing_grid** — 


---

## Repair Agent — 2026-05-28T01:16:29.484492Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-28T00:51:48.630030Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-28T00:32:44.163335Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-28T00:24:42.865560Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-28T00:04:31.766110Z

- **Status**: WARN
- **Total checks**: 635
- **Passed**: 628
- **Failed**: 7
- **Critical divergences**: 0

### Collector errors
_0 critical · 2 warning · 0 stale_

- ⚠️ **EIA fetch: RWTC** — 504 Server Error: Gateway Timeout for url: https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=[REDACTED]&frequency=daily&data%5B0%5D=value&facets%5Bseries%5D%5B%5D=RWTC&sort%5B0%5D%5Bcolumn%5D=period&sort%5B0%5D%5Bdirection%5D=desc&length=60
- ⚠️ **EIA fetch: RBRTE** — HTTPSConnectionPool(host='api.eia.gov', port=443): Read timed out. (read timeout=15)

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 57d old (limit 55d)
- ⏰ **Staleness: payems** — 57d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T23:41:42.236865Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T21:31:52.706092Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T21:19:21.017056Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T18:51:40.689776Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T17:48:34.454864Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T17:08:21.493854Z

- **Status**: WARN
- **Total checks**: 633
- **Passed**: 628
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-27T16:34:36.242843Z

- **Status**: WARN
- **Total checks**: 634
- **Passed**: 629
- **Failed**: 5
- **Critical divergences**: 0

### Staleness
_0 critical · 0 warning · 2 stale_

- ⏰ **Staleness: unrate** — 56d old (limit 55d)
- ⏰ **Staleness: payems** — 56d old (limit 55d)

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T23:47:08.285999Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T22:56:24.829413Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T21:41:52.381084Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T20:02:35.962662Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T19:49:59.178392Z

- **Status**: WARN
- **Total checks**: 390
- **Passed**: 375
- **Failed**: 15
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML

### Visual QA
_0 critical · 12 warning · 0 stale_

- ⚠️ **Visual: global — Nav buttons present** — 
- ⚠️ **Visual: Jobs — Nav button exists** — 
- ⚠️ **Visual: Unemployment — Nav button exists** — 
- ⚠️ **Visual: Wages — Nav button exists** — 
- ⚠️ **Visual: CPI — Nav button exists** — 
- ⚠️ **Visual: Consumer & PCE — Nav button exists** — 
- ⚠️ **Visual: Rates & Yields — Nav button exists** — 
- ⚠️ **Visual: Credit — Nav button exists** — 
- ⚠️ **Visual: Banking — Nav button exists** — 
- ⚠️ **Visual: Housing — Nav button exists** — 
- _… and 2 more_


---

## Repair Agent — 2026-05-24T17:44:45.177113Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T07:21:17.471108Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T06:41:07.945458Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T06:27:12.292147Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

## Repair Agent — 2026-05-24T05:42:28.966329Z

- **Status**: WARN
- **Total checks**: 631
- **Passed**: 628
- **Failed**: 3
- **Critical divergences**: 0

### Panel data
_0 critical · 3 warning · 0 stale_

- ⚠️ **Energy and transport categories are pulling the basket higher: data const CPI_CAT_MOM extractable** — Could not parse const CPI_CAT_MOM from HTML
- ⚠️ **Energy and housing components are pulling the PCE basket higher: data const PCE_CAT_MOM extractable** — Could not parse const PCE_CAT_MOM from HTML
- ⚠️ **Hiring is now concentrated in healthcare and leisure: data const SECTOR_MOM extractable** — Could not parse const SECTOR_MOM from HTML


---

