# CEO-Grade Agentic AI Dashboard — Framework, Benchmarks, Maturity

**Date**: 2026-05-12
**Scope**: U.S. Macro Dashboard (this repo) — multi-stage data pipeline with
LLM-in-the-loop, publishing to a CEO-level audience.
**Authoring lens**: Senior staff engineer / SRE / AI safety practitioner.

---

## 0. Executive Summary

The dashboard is positioned to set a credible bar for **fully agentic
AI auto-pilot operation** on a public reporting surface. The system
now combines:

1. **A deterministic core** (collector → analyzer → renderer → validator
   → visual_qa → publisher). LLM reasoning is layered *on top* and
   is forbidden from modifying the rendering or layout pipeline.
2. **A bounded-action agentic layer** for diagnosis (Agent 10), signal
   explanation (Phase 2), editorial review (Phase 2.5), with every
   LLM call routed through a runtime safety module
   (`scripts/_agent_guardrails.py`) that enforces kill switch, cost
   cap, path allowlist, audit log, and now an output-validator hook
   for near-zero-fail-rate output handling.
3. **A consolidated publish gate** (`scripts/ceo_grade_gate.py`) that
   aggregates the verdicts from every quality layer into a single
   PASS / WARN / FAIL / SKIP decision suitable for an unattended
   publishing step.

This document maps each design decision to the industry-standard
framework it draws from, and gives an honest maturity assessment.

---

## 1. Framework Map

| Concern | Industry framework | What we do |
|---|---|---|
| Reliability of autonomous components | Google SRE — Error Budgets, Defense in Depth, Limit Blast Radius | Kill switch (`AGENT_DISABLE_ALL`), per-run cost cap (`AGENT_MAX_LLM_CALLS`), path allowlist that forbids writes to `renderer.py` and `index.html` structure |
| Output reliability of LLM components | Anthropic Constitutional AI, OpenAI structured outputs, IBM "AI Engineering Practices" | `bounded_llm_call(validator=…)` returns `None` on schema-rejected output; caller treats `None` as "skip" so malformed outputs never propagate downstream |
| Safety vs autonomy tradeoff | Anthropic Responsible Scaling Policy levels, NIST AI RMF | Three-stage promotion: 10a Diagnostician (read-only) → 10b Proposer (writes draft PRs, human reviews) → 10c Auto-fixer (whitelisted categories with two-LLM critique). Each promotion gated on ≥ 3 weeks of shadow data |
| Audit & replayability | SRE — observability; SOX & similar compliance lineages | Every LLM call logged to `data/agent_memory.jsonl` with prompt SHA, response, token usage, elapsed time; rolling 2000-entry retention; CLI inspector for replay (`scripts/inspect_agent_memory.py`) |
| Prompt injection / supply chain | OWASP Top 10 for LLM Applications (LLM01 Prompt Injection, LLM06 Output Handling) | LLM responses never executed directly; treated as data and validated against schema; renderer.py + index.html structurally protected from any LLM-driven write |
| Output-quality control | Constitutional AI critique pattern, Anthropic "principal/critic" research | Two-LLM critique on every "critical" editorial verdict (Sonnet audits, Opus critiques) before promotion — divergent models reduce correlated errors |
| Data correctness | Bloomberg / Refinitiv-grade source verification, FRED publishing notes | Validator Pass 3i: cross-source agreement (FRED vs BLS for shared anchor metrics) — catches one-side staleness or revision lag |
| Visual quality at CEO level | Edward Tufte; Bloomberg Terminal style guide; Google Material; finance-research IB visual conventions | Hand-curated `data/style_guide.md` codifies layout, typography, color, spacing, cross-tab consistency. Agent 7 (DOM) + Agent 8 (vision) enforce against it |
| Editorial precision in narrative | AP Stylebook; ASA Statement on p-values (clarity on uncertainty) | Style guide §2: declarative tone, 2-4 sentence band, forbidden hedging vocabulary; deterministic linter enforces |
| Process governance | GitFlow + branch protection; PR-required workflows | `main` is branch-protected. Every change reaches it via PR with smoke-test CI green. LLM-driven changes (future Stage 10b) go through the same PR flow |
| Operational kill switch | Industry standard SRE — fast rollback, feature flags | `AGENT_DISABLE_ALL=1` reverts the system to deterministic-only mode in 1 env-var flip, zero code change |

## 2. Defense-in-depth diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       PUBLISH SURFACE (CEO)                       │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │ CEO-GRADE GATE  (scripts/ceo_grade_gate.py)              │   │
│   │ Aggregates verdict. Strict mode = WARN→FAIL on pub days. │   │
│   └──────────────┬───────────────────────────────────────────┘   │
│                  │                                                │
│   ┌──────────────┴─────────────────────────────────────────────┐ │
│   │ LAYER 5 — EDITORIAL  (style_guide §2)                       │ │
│   │ Deterministic linters first; LLM tone audit optional;      │ │
│   │ Two-LLM critique on any "critical" verdict.                │ │
│   └────────────────────────────────────────────────────────────┘ │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ LAYER 4 — VISION REVIEW (Agent 8, Claude multimodal)        │ │
│   │ 16 defect categories, style_guide-cited.                   │ │
│   └────────────────────────────────────────────────────────────┘ │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ LAYER 3 — VISUAL QA  (Agent 7, Playwright DOM)              │ │
│   │ 220+ DOM checks · commentary placement · color, typography │ │
│   └────────────────────────────────────────────────────────────┘ │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ LAYER 2 — VALIDATOR  (10 passes; 200+ deterministic checks)│ │
│   │ Internal · Source · Staleness · Shock · Panel · Metric ·   │ │
│   │ Schema · Seed · Collector errors · Cross-source            │ │
│   └────────────────────────────────────────────────────────────┘ │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ LAYER 1 — SMOKE TESTS (29/29 — must pass before any merge) │ │
│   └────────────────────────────────────────────────────────────┘ │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ LAYER 0 — PREFLIGHT (Agent 0)                               │ │
│   │ FRED series IDs + Anthropic model IDs verified live before │ │
│   │ the pipeline runs.                                          │ │
│   └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

           ⬆ All "agentic" writes pass through:

   ┌────────────────────────────────────────────────────────────┐
   │  _agent_guardrails.bounded_llm_call(validator=…)            │
   │   • Kill switch  • Cost cap  • Path allowlist  • Audit log │
   │   • Output-validator hook → None on schema reject          │
   └────────────────────────────────────────────────────────────┘
```

Six independent layers. Any single layer's failure does not produce a
silent CEO-visible defect. This is the "swiss cheese" reliability
model from human-factors engineering (Reason 1990), adapted to AI/ML
systems.

## 3. Near-zero-fail-rate guarantees

| Source of "fail" | Mechanism that prevents propagation |
|---|---|
| LLM hallucinates malformed JSON | `bounded_llm_call(validator=…)` rejects, retries, returns `None`. Callers treat `None` as "skip" — bad output never lands |
| LLM gives an opinion on a layout change | Path allowlist refuses any write outside `data/*` allowlist set. `renderer.py` and `index.html` are read-only to agents |
| LLM cost runs away on a pathological run | `AGENT_MAX_LLM_CALLS` cap raises `BudgetExhausted` exception, agent emits a "budget exhausted" report and stops |
| Editorial review confidently endorses a fabricated number | Deterministic linter checks every numeric in commentary against `raw_data.json` first. The LLM never sees the value before the deterministic check has filtered |
| Visual review misses a layout drift | DOM-level Agent 7 check (`Commentary positioned above first chart`) is deterministic and catches the exact failure mode that the model might miss |
| Repair Diagnostician escalates a benign warning | Memory-aware recurrence detection downgrades first-time findings; playbook §9 codifies known acceptable variations |
| One source publishes a wrong number | Pass 3i cross-source agreement (FRED vs BLS) flags divergence within the same render cycle |
| Single point of failure in the agentic layer | Kill switch (`AGENT_DISABLE_ALL=1`) reverts to deterministic-only, in 1 env-var flip |
| A new LLM model misbehaves | `scripts/_models.py` centralised model IDs + preflight check (Agent 0) — model swap is a single-file change, validated before run |

We are not claiming "zero fail." We are claiming that **every known
class of fail has at least one independent layer that prevents
propagation to the CEO-visible surface.** The remaining failure modes
(novel jailbreaks, novel chart bugs, novel data publishing schedules)
are caught by the human-curated playbook/style-guide pair, which is
the system's "court of last resort."

## 4. Maturity assessment vs industry benchmarks

| Dimension | Current state | Industry benchmark | Gap |
|---|---|---|---|
| LLM output validation | Schema validator hook on every call; two-LLM critique on critical verdicts | Anthropic / OpenAI structured-output APIs + critique loops | Caught up; can adopt the formal `response_format: json_schema` once it stabilises across our model |
| Audit trail | Append-only JSONL, 2000-entry rolling, prompt SHA + truncated text | SOX-style audit, full-fidelity replay | Adequate for review; full prompt retention would need durable storage (S3 / GCS) — not yet implemented |
| Cost control | Per-run cap, in-process counter | Cloud anomaly detection (e.g. AWS Cost Anomaly Detection) | Local enforcement only; no $-denominated budget pulled from billing yet |
| Kill switch | Single env-var, instantly reverts | LaunchDarkly / Statsig feature flags | Equivalent in effect; lacks per-region rollout (not needed at single-deploy scale) |
| Branch protection | `main` protected, smoke-test gate, squash merge | Industry standard GitHub workflows | Caught up |
| Visual QA | DOM-level Playwright + Claude vision review + style guide as contract | Bloomberg-style "perceptual diff" + manual editorial | Vision review still per-tab (not cross-tab in one call); editorial reviewer is automated (not the human board reviewer) |
| Data sourcing | FRED + BLS + BEA + EIA + UMich; cross-source agreement check | Bloomberg / Refinitiv multi-source averaging | Single-source authoritative for each metric; cross-source is a check, not an averaging |
| Agentic action scope | Stage 10a Diagnostician (read-only). 10b/10c gated on 3 weeks observation | Anthropic Computer Use; Cognition Devin | Conservative by design; we are early in the maturity ladder for "agent that writes code." This is appropriate for a CEO publishing surface |
| Editorial control | Style-guide-driven deterministic linter + optional LLM tone audit | AP / Reuters house-style enforcement (human) | Automated; reasonable for the audience; final human review is still recommended for board-deck embeds |

## 5. Where we are conservative on purpose

The bar "auto-pilot with near-zero fail rate" pulls in two directions:
*more autonomy* (do more without human-in-loop) and *more reliability*
(catch more before publish). For a CEO surface, reliability wins
every time. Specifically:

- **No LLM ever writes to `renderer.py` or `index.html` structure.**
  This is encoded in `LLM_WRITABLE_PATHS` and enforced before every
  write. The dashboard layout is humans-only.
- **The Repair Agent (Agent 10) is observer+diagnostician only.**
  Stage 10b (Proposer with draft PR) and 10c (whitelisted auto-fix)
  exist in the roadmap but are explicitly gated on weeks of shadow
  data showing the diagnostician's reasoning is sound.
- **Critical findings require two-LLM critique.** Different model
  families (Sonnet for primary, Opus for critique) reduce the chance
  of correlated failure on adversarial inputs.
- **Every commentary numeric is checked against raw data deterministically
  before any LLM weighs in.** The deterministic pass catches the highest-
  confidence failures without spending an LLM call.

## 6. Roadmap — completing the picture

Already delivered:
- Layer 0 Preflight (Agent 0)
- Layer 1 Smoke tests (29/29)
- Layer 2 Validator with 10 passes (including new Pass 3i cross-source)
- Layer 3 Visual QA with layout + typography + color drift checks
- Layer 4 Vision Review with style-guide-aware prompts and 6 new defect categories
- Layer 5 Editorial Review (deterministic linters live; LLM tone audit opt-in)
- CEO-grade gate aggregating all of the above
- Guardrails with kill switch, cost cap, path allowlist, audit log, validator hook
- Memory-aware Diagnostician for recurrence detection

Recommended next steps (in priority order, each its own PR):

1. **Cross-tab vision review mode** — batch all 12 chart tabs into a
   single multi-image call to Claude, ask for cross-tab consistency
   verdicts (currently Agent 8 reviews per-tab in isolation).
2. **Editorial review enabled in CI** — once shadow data shows the
   deterministic linter's findings hold up, set `AGENT_EDITORIAL_REVIEW_ENABLED=1`
   in the workflow.
3. **Diagnostician → Proposer (Stage 10b)** — after ≥3 weeks of clean
   10a output, promote to writing draft PRs with code diffs. Human
   reviews before merge.
4. **Cost telemetry** — export `agent_memory.jsonl` token aggregates
   to a dashboard panel (sources tab) so cost trends are visible.
5. **Durable audit storage** — push `agent_memory.jsonl` to S3/GCS
   nightly so the rolling 2000-entry cap doesn't lose history.
6. **Editorial human review surfacing** — when the editorial agent
   flags a critical issue, post a comment on the next briefing PR so
   the human reviewer sees it inline.
7. **Vision-driven layout repair (Stage 11)** — a separate, very
   bounded agent that proposes index.html layout fixes when Agent 8
   flags inconsistencies. Highest-risk; requires the layout contract
   to be far more formal first.

## 7. References

- Anthropic, *Responsible Scaling Policy* (v2). Multi-stage promotion
  ladder for autonomous capabilities.
- Anthropic, *Constitutional AI: Harmlessness from AI Feedback*.
  Foundation for critique-loop pattern used in 10b/10c.
- OWASP, *Top 10 for Large Language Model Applications* (2025).
  LLM01 Prompt Injection, LLM06 Output Handling, LLM09 Overreliance
  — all mapped to controls in `_agent_guardrails.py`.
- NIST AI RMF (NIST.AI.100-1). Govern, Map, Measure, Manage.
- Google SRE Workbook, Beyer et al. — Error Budgets, Toil, Defense
  in Depth.
- Reason, James (1990). *Human Error*. Cambridge University Press.
  "Swiss cheese" model of accident causation.
- Tufte, Edward (2001). *The Visual Display of Quantitative
  Information*. 2nd ed. Reference for chart/typography conventions in
  `data/style_guide.md`.
- AWS Well-Architected Framework — Operational Excellence pillar.
- Microsoft, *Responsible AI Standard* (v2). Reliability, transparency,
  accountability, fairness, inclusiveness, privacy, security.

---

## 8. How to use this report

- **For the CEO / sponsor**: §0 + §2 (diagram) + §4 (maturity table)
  are the talking points. We have built a defense-in-depth pipeline,
  conservative by design, on industry-standard foundations.
- **For engineering reviewers**: §3 (zero-fail mechanisms) and §5
  (where we are conservative on purpose) are the implementation
  rationale.
- **For maintainers planning future work**: §6 (roadmap) is the
  prioritised follow-up list; each item is its own PR.
