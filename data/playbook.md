# Macro Dashboard — Agent Reasoning Playbook

Curated by humans. Read by every agentic component as the single source
of truth for "what counts as normal" and "what to recommend when X breaks."

When this document and an LLM's prior training disagree, **this document
wins.** Agents are instructed in their system prompt to cite a line from
this playbook when justifying a diagnosis; if they can't, they downgrade
their confidence and surface the gap to humans.

---

## 1. Pipeline overview

The dashboard is a deterministic multi-stage CI pipeline with LLM
components at three points (briefing commentary, vision review, earnings
extraction). The Repair Diagnostician (Agent 10, Stage 10a) reasons
about pipeline failures and emits incident reports. It does not modify
code, data, or layout.

See `CLAUDE.md` for the authoritative agent list.

## 2. What is normal

### 2.1 Cadence
- Pipeline runs **weekly** (Saturday 12:00 UTC, GitHub Actions cron).
- A second monthly run lands on the 2nd Saturday for monthly-only data.
- Earnings agent (Agent 9) runs only on its own cron during earnings
  weeks (Jan/Apr/Jul/Oct days 10–28).

### 2.2 Publish lag per source
| Source         | Typical lag                       | Notes |
|----------------|-----------------------------------|-------|
| FRED weekly    | 0–3 days                          | gasoline (GASREGW), claims |
| FRED monthly   | 5–10 days after month end         | Fed Funds, mortgage rate |
| BLS monthly    | ~5–10 days after month end        | NFP, CPI, wages |
| BEA quarterly  | ~30 days after quarter end        | GDP advance/2nd/3rd estimates |
| BEA monthly    | ~30 days for PCE; ~95 days observed | Personal saving rate, PCE prices |
| EIA weekly     | 0–3 days                          | weekly oil/gas |
| UMich          | mid-month prelim, end-of-month final | Sentiment |
| NY Fed         | ~45 days after quarter end        | HHDC report (CC delinquency) |

A staleness flag that **matches the source's normal lag is not a bug.**
The clearest example: PCE shows ~95 day lag because of BEA's monthly
release schedule — this is genuine and should be reported as
**informational**, not actionable.

### 2.3 Typical noise floors (per-series natural wiggle)
| Series                       | Noise floor      | Used by |
|------------------------------|------------------|---------|
| Core CPI YoY                 | ±0.3pp month/month | Shock tracker Core Goods phase |
| Saving rate                  | ±0.3pp month/month | Shock tracker Savings phase |
| UMich Sentiment              | ±0.5pt month/month | Shock tracker Sentiment phase |
| CC 90+ DPD                   | ±0.15pp quarter/quarter | Shock tracker Delinq phase |
| Gasoline $/gal               | ±$0.10/gal week/week | Shock tracker Pump phase |

When a series moves within its noise floor, the shock tracker should
return `not_yet` — even if the direction is shock-consistent. See
`scripts/renderer.py::update_shock_tracker._status()`.

## 3. Validator semantics

### 3.1 Pass-by-pass intent
| Pass | What it checks | When it should flag |
|------|----------------|---------------------|
| 1 — Internal consistency | KPI vs raw_data parity | Renderer wrote a value that disagrees with the underlying series |
| 2 — Source verification | sample of values matches API ground truth | Collector got stale or wrong-row data |
| 3 — Staleness | per-series age vs `max_lag_days` | Genuine delay; **NOT** a code bug |
| 3d — Shock tracker | every phase's `pre`/`now` matches the right raw key | Renderer fell through to a hardcoded baseline (silent bug) |
| 3e — Cross-surface metric consistency | same metric shown identically in multiple tabs | Renderer drift between tabs |
| 3f — Schema contract | collector keys ↔ renderer expectations | A new series was added in one place but not the other |
| 3g — Seed drift | hardcoded seeds in renderer match latest raw value | Seeds went stale silently |
| 3h — Collector errors | API fetch failures during the run | Network / quota issues |
| 3c — Earnings verbatim | quoted spans exist in archived transcripts | Hand-edited content drifted from the source |
| 4 — Visual QA | 224 Playwright DOM checks | Chart canvas missing, label overflow, etc. |
| 5 — Vision review | Claude multimodal compares chart screenshot vs caption | Vision-level anomalies (wrong axis range, missing legend) |

### 3.2 Severity ladder
- **critical** (or `divergence`) → blocks publish. Always actionable.
- **warning** → does not block. Often actionable but may be cosmetic.
- **stale** → informational. Compare against §2.2 publish lag table
  before recommending action.
- **skipped** → environment dependency missing (e.g. Playwright). Not a
  bug in the data — a CI-config gap.

## 4. Common-cause patterns (for the Diagnostician)

When reasoning about a finding, look for the patterns below first.
They cover the majority of historical failures.

### 4.1 Pattern: "Series X is stale by Yd, limit is Yd"
- **Likely root cause**: source has not published yet (compare against §2.2).
- **If lag is within table's typical range**: do NOT recommend a fix.
  Recommend "monitor next publish window: <date>".
- **If lag exceeds table by >7 days**: investigate (1) source outage,
  (2) collector fetch parameters (likely `limit=` too small), (3) API
  endpoint change.

### 4.2 Pattern: "SHOCK_TRACKER phase Z reads pre=X.X, now=X.X (equal)"
- **Likely root cause**: `update_shock_tracker` fell through to its
  hardcoded baseline because the underlying raw key has insufficient
  observations. See `CLAUDE.md` "Shock Tracker Data Contracts" table —
  YoY phases need limit≥24.
- **Recommend**: collector fetch count bump for the responsible series.
  Cite the exact raw-data key.

### 4.3 Pattern: "patch_kpi not found" warnings
- **Often benign** — renderer runs twice on the same HTML produce these
  because the first run already updated the labels.
- **Investigate if NEW** — the KPI structure may have changed and the
  renderer's selector is stale.

### 4.4 Pattern: "core_cpi_yoy = 2.74 vs 2.5 pre, status = ahead at week 10"
- This is the **noise-floor confusion bug** (see git log `move_threshold`).
- The fix shape is: phase-specific `move_threshold` parameter, NOT a
  single global threshold.
- **Recommend**: check that every `_status()` caller in
  `update_shock_tracker` passes its own `move_threshold` matching §2.3.

### 4.5 Pattern: Pass 3c (earnings verbatim) fails
- A quoted span in `data/bank_earnings.json` no longer matches the
  archived transcript in `data/transcripts/<Q>/<TICKER>.txt`.
- **Never recommend "edit the JSON to match"** without a transcript
  source check — that would launder fabricated content.
- **Recommend**: re-read the transcript, verify the quote, either fix
  the JSON to match transcript verbatim OR remove the quotation marks
  and convert to summary (per CLAUDE.md factuality rule).

## 5. What the Diagnostician must NEVER recommend

Stage 10a is read/explain only. Even at later stages, the following
recommendations are forbidden by default:

1. **Edit `index.html` structure or layout.** Only data values inside
   pre-defined containers may change; structure changes are humans-only.
2. **Edit `scripts/renderer.py` regex patterns.** These are the contract
   between data and presentation; an LLM rewriting them risks silent
   data drift. Regex changes go through human review with the renderer
   tests as the gate.
3. **Delete data files.** `data/raw_data.json`, `data/signals.json`, the
   snapshot tarballs — none of these are LLM-deletable. Recovery is via
   `scripts/snapshot.py` rollback.
4. **Disable a validator pass.** If a pass is flapping, the right
   recommendation is to investigate the false positives, not to silence
   the gate.
5. **Fabricate quotes or numbers in earnings content.** Per CLAUDE.md
   factuality rule, every numeric and every quoted span must be
   traceable to a source.
6. **Bypass the renderer.** If a value needs to land in the dashboard,
   it goes via `scripts/renderer.py` patching `data/signals.json` or
   `data/raw_data.json` — never via direct HTML edits.

## 6. Reporting style

Incident reports should be:
- **Structured** — one Markdown section per finding with the same headings.
- **Cite-or-downgrade** — every diagnosis cites either a playbook
  section (§X.Y) or a file:line. If neither, mark confidence "low".
- **Action-oriented** — every finding ends with a "recommended next
  step" the maintainer can execute, OR explicitly says "monitor only".
- **No hedging fluff** — drop sentences like "may potentially indicate"
  unless the uncertainty is the substance of the report.
