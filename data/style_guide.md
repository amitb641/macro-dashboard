# Macro Dashboard — Style Guide

Audience: CEO-level. Every visual element is scrutinised. This document
codifies the standards against which `Agent 7 (visual_qa.py)` and
`Agent 8 (visual_review.py)` evaluate the rendered page. When the
playbook of macro reasoning lives in `data/playbook.md`, the playbook
of **visual presentation** lives here.

When this document and an LLM's instinct disagree, **this document wins.**
When a rule here and existing markup disagree, **the markup is wrong**
and a fix-up PR is required.

## 0. Bar

This dashboard is published to a CEO-level audience. The bar is:
- **Visual perfection**: no broken charts, no overflowed labels, no
  alignment drift, no orphan or duplicate elements, no inconsistent
  typography or spacing across surfaces.
- **Layout consistency**: same kind of content sits in the same
  relative position across tabs.
- **Editorial precision**: every numeric assertion in commentary
  matches the corresponding raw datum within the same render cycle.

Anything that would embarrass a senior reviewer if shown in a board
deck is by definition out of spec.

---

## 1. Layout conventions (per tab)

Every chart-bearing tab (`fc`, `gdp`, `jobs`, `unemp`, `wages`, `cpi`,
`pce`, `yield`, `credit`, `banks`, `housing`, `oil`) follows this
top-to-bottom order:

1. **Metric row** — `<div class="metric-row" id="<tab>-metrics">`
   (optional; not every tab has it). When present, it sits first.
2. **Tab-level commentary** — `<div class="fc-note" id="commentary-<tab>">`.
   **Must appear before the first chart canvas.** This is the
   "TL;DR / headline narrative" for the tab — a 2-4 sentence
   editorial framing of what the charts say. Either bare (`fc`, `banks`,
   `credit`, `yield`, `oil`) or wrapped in a styled `<div class="panel">`
   with a panel-title containing the word "Commentary" (`unemp`, `cpi`,
   `wages`, `jobs`, `pce`, `housing`).
3. **Primary charts/cards** — `<div class="two-up">` or
   `<div class="panel">` containing one or more `<canvas>` elements.
4. **Section dividers** — `<div class="stk-section-title">…</div>` to
   group multi-section tabs (oil has Section 1 / Section 2 / etc.).
5. **Additional charts/cards** — same patterns as above.
6. **Source attribution** — `<p class="src">` at the bottom of each
   panel that contains a chart, citing the data source.

Pages without per-tab commentary (gdp, stack/Dashboard, validator,
dict/Sources) are exempt from rule 2.

**Enforced by**: `visual_qa.py::Commentary positioned above first chart`
(per tab) and `visual_qa.py::Tab-level fc-note exists and is bounded`
(per tab, except exempt list).

## 2. Commentary copy rules

- Length: 2 to 4 sentences. Single-sentence summaries read thin; >4
  becomes a wall of text on the dashboard.
- Voice: declarative analyst tone. No hedging filler ("may potentially
  indicate"). Either we believe it or we don't print it.
- Every numeric mentioned in the commentary (e.g. "WTI at $109.8")
  **must match the corresponding KPI tile and raw data** within the
  same render. Validator Pass 3e enforces this.
- Never reference dates that have not happened yet without an explicit
  "pending" / "forecast" / "expected" qualifier.
- Forbidden vocabulary in commentary: "in my opinion", "perhaps",
  "various", "a number of", "things". Use specifics.

**Enforced by**: Agent 8 vision review (`copy.tone`) + validator
Pass 3e (numeric cross-surface consistency).

## 3. Typography

- **Headline / hero**: `Instrument Serif`, weight 400, size 26-30px.
- **Section title** (`.stk-section-title`): `DM Mono`, 11px, weight
  700, uppercase, letter-spacing .12em.
- **Panel title** (`.panel-title`): default system sans, ~13-14px,
  weight 600.
- **Body / commentary** (`.fc-note`): default system sans, 12.5-13px,
  line-height 1.65, color `--text2` (#64748B / #475569).
- **Code / data labels**: `DM Mono`, 8.5-11px.
- **No font drift**: do not introduce a 4th font family. Do not raise
  body text above 14px in commentary contexts.

## 4. Color contract

```
--accent   #336BCC   primary brand blue
--accent2  #8878B8   secondary lavender (AI / LLM-driven surfaces)
--text     #1E293B   primary text
--text2    #64748B   body / commentary text
--muted    #94A3B8   labels, sources, metadata
--border   #E2E8F0   default borders
--bg       #F7F9FC   page background
--card     #FFFFFF   panel background
```

Semantic colors (severity / direction):
- 🔴 **Critical / shock / risk**: `#D64045` (red 600)
- ⚠ **Warning / watch**: `#CC8A00` (amber 600)
- ✅ **Confirmed / good**: `#1A9E5A` (green 600)
- 🛡 **Validation / shield**: `#059669` (green 700)

Do not introduce ad-hoc colors. New semantic categories require a
named variable here first.

## 5. Spacing & rhythm

- Panel inner padding: 28px top, 24px sides (`.diag-wrap` standard).
- Vertical rhythm between panels: 16-20px margin-bottom.
- Two-up grid gap: 12-16px.
- Hero hero hero: 32px top, 36px sides.
- Section title margin: 24-28px top, 10-12px bottom.

Spacing inconsistencies (e.g. one panel uses 32px margin-bottom while
its peers use 16px) are CEO-grade defects. Flag on review.

## 6. Charts (Chart.js conventions)

- Lines must be **continuous** — no broken segments unless data is
  genuinely sparse (and that case must be commented in the renderer).
- Y-axis must start at a sensible baseline (0 for counts, source-aware
  for rates).
- Legends present for any chart with 2+ series.
- Labels never overflow the canvas; if they would, the renderer must
  rotate or truncate them — never overflow.
- Tooltips enabled.
- Use `--accent` for the primary series; secondary series use the
  semantic palette above.

**Enforced by**: Agent 7 (canvas dimensions, console errors) + Agent 8
(`BROKEN_LINE`, `LABEL_OVERLAP`, `LABEL_TRUNCATED`, `EMPTY_CHART`,
`MISSING_LEGEND`).

## 7. KPI / metric tiles

- Numeric value typeset in `Instrument Serif`, ~18-22px.
- Label below value in 10-11px DM Mono.
- Direction arrows (↑ ↓) coloured per §4 semantic palette.
- Never display `NaN`, `undefined`, `null`, or `[object Object]`.

**Enforced by**: `visual_qa.py` `No undefined/NaN/null values`,
`KPIS no NaN/undefined`.

## 8. Cross-tab consistency rules

For elements that recur across tabs:
- Same kind of content sits in the **same relative position**
  (see §1 layout conventions).
- Same metric (e.g. "Core CPI 2.74%") is rendered with the same
  units, precision, and label across every tab in which it appears.
  Validator Pass 3e is the data side; Agent 8 vision review is the
  visual side.
- Panel borders, radii, and inner padding must match across tabs.

**Enforced by**: Agent 7 (`Commentary positioned…` and other relative
position checks added over time) + Agent 8 vision review with the
cross-tab consistency directive in its system prompt.

## 9. What "perfection" excludes (known acceptable variations)

- The Outlook tab (`fc`) intentionally uses `commentary-gdp` as the
  ID for its lead-in narrative — historical: the Outlook tab was
  originally the GDP tab. Don't "fix" this without an editorial pass.
- The architecture page (`stack`) has its own design system
  (`.stk-*` classes) — does not need to match chart-tab conventions.
- The Sources (`dict`) and Validator tabs are utility surfaces with
  their own table-heavy layouts.

These exceptions are codified here so an agent can cite this section
when downgrading a finding to "informational".

## 10. Update policy

- This document is **human-curated**, like the playbook. Agents read
  it; agents do not write it.
- Changes require a PR with a screenshot diff showing before/after
  of the affected surface(s).
- When a new check lands in Agent 7 or Agent 8, the §it enforces is
  noted under its "Enforced by:" tag.
