# Macro Dashboard — Style Guide

Audience: CEO-level. Every visual element is scrutinised. This document
codifies the standards against which `Agent 7 (visual_qa.py)` and
`Agent 8 (visual_review.py)` evaluate the rendered page. Where the
playbook of macro reasoning lives in `data/playbook.md`, the playbook
of **visual presentation** lives here.

When this document and an LLM's instinct disagree, **this document
wins**. When a rule here and existing markup disagree, **the markup is
wrong** and a fix-up PR is required.

This file is the authoritative reference for any "professionalisation"
or "uplift" pass on the dashboard. Read it before designing; cite a
§-section when reviewing a PR; never improvise outside the rules.

---

## 0. The bar

The dashboard is published to a CEO-level audience. The bar is:

- **Visual perfection.** No broken charts. No overflowed labels. No
  alignment drift. No orphan or duplicate elements. No inconsistent
  typography or spacing across surfaces.
- **Editorial precision.** Every numeric assertion in commentary
  matches the corresponding raw datum within the same render cycle.
  Every quoted span in earnings panels matches a transcript verbatim.
- **Information density without noise.** Charts maximise data-ink and
  minimise chart-junk. Pages do not need decoration to feel premium —
  type discipline and whitespace do that work.
- **Restraint.** One accent colour for primary signal; semantic
  colours only for status. No ad-hoc hues, no skeuomorphism, no
  drop shadows beyond a 1px ambient lift, no glow effects, no animated
  GIFs, no decorative emoji.

Anything that would embarrass a senior reviewer if shown in a board
deck is by definition out of spec. When in doubt, default to less
colour, less weight, more whitespace.

The visual references are: Anthropic engineering blog, Stripe Press /
Stripe Docs, Linear, Vercel Analytics, Bloomberg Terminal type
discipline (without the dark theme), Goldman Sachs research report
layout, and Tufte/Few "data-ink" conventions.

---

## 1. Layout conventions

### 1.1 Page-level structure

Reading order top-to-bottom on every page:

1. **Page chrome** — eyebrow (top metadata), `<h1>`, subtitle.
2. **Global KPI strip** — `<div class="kpi-strip">` with `.m-tile` items.
3. **Tab navigation** — `<button class="nav-btn" data-tab="…">` row.
4. **Active tab panel** — one of `<div class="tab-panel" id="tab-X">`.

### 1.2 Tab-level structure

Every chart-bearing tab (`fc`, `gdp`, `jobs`, `unemp`, `wages`, `cpi`,
`pce`, `yield`, `credit`, `banks`, `housing`, `oil`) follows this
top-to-bottom order:

1. **Per-tab metric row** (optional) — `<div class="metric-row" id="<tab>-metrics">`.
   Holds 4-8 tile units sized via `grid-template-columns:repeat(auto-fill,minmax(175px,1fr))`.
2. **Tab-level commentary** — `<div class="fc-note" id="commentary-<tab>">`.
   **Must appear before the first chart canvas.** This is the "TL;DR /
   headline narrative" for the tab — a 2-4 sentence editorial framing
   of what the charts say. Either bare (`fc`, `banks`, `credit`,
   `yield`, `oil`) or wrapped in a styled `<div class="panel">` with
   a panel-title beginning with "📋 X Commentary —" (`unemp`, `cpi`,
   `wages`, `jobs`, `pce`, `housing`).
3. **Primary panels** — `<div class="two-up">` for paired charts or
   single `<div class="panel">` for one-up content.
4. **Section divider** (when a tab is multi-section) —
   `<div class="stk-section-title">…</div>`. Only `oil` currently uses
   sectioning at the tab level; keep it the exception.
5. **Additional panels** — same patterns.
6. **Source attribution** — `<p class="src">` at the bottom of each
   panel containing data (charts or tables).

Pages without per-tab commentary (`gdp`, `stack`, `validator`, `dict`)
are exempt from rule 2.

### 1.3 Tab archetypes

The 15 tabs fall into 4 archetypes, each with its own conventions:

| Archetype | Tabs | Typical structure |
|---|---|---|
| **Headline / Outlook** | `fc` (Outlook) | hero metric strip → narrative → scenario table → grid of indicator cards → synthesis panel |
| **Indicator chart** | `gdp`, `jobs`, `unemp`, `wages`, `cpi`, `pce`, `yield`, `credit`, `housing` | metric row → wrapped commentary → 1-3 two-ups of charts → MoM/sector panel → src |
| **Compound** | `banks`, `oil` | metric row → bare commentary → section-divided panels with both charts and tables (and earnings cards in banks' case) |
| **Utility / Reference** | `stack` (architecture), `dict` (sources), `validator` | own design system (`.stk-*` for stack; flat tables for dict; pre-rendered JSON for validator) |

Cross-tab DOM checks in `visual_qa.py` enforce that chart tabs follow
the canonical archetype.

### 1.4 Two-up grid

Use `<div class="two-up">` for *paired* charts that should be compared
side-by-side (e.g. annual vs monthly view of the same series).
`grid-template-columns: 1fr 1fr; gap: 16px;`. Never stack a `.two-up`
inside another `.two-up`. Below ~700px viewport width the grid
collapses to a single column.

### 1.5 Section dividers

`<div class="stk-section-title">` style is reserved for the
architecture page. Inside chart tabs, group charts via paired panels
with related titles rather than introducing a new divider class.

### 1.6 What "perfection" excludes

- **Outlook tab `fc`** uses `commentary-gdp` as the ID for its lead-in
  narrative — historical, the Outlook tab was originally the GDP tab.
  Don't auto-rename without an editorial review.
- **Architecture page `stack`** has its own design system (`.stk-*`
  classes) — does not need to match chart-tab conventions.
- **Sources `dict`** and **Validator** tabs are utility surfaces with
  table-heavy layouts; minor density and type-size deviations are
  acceptable when the page is reference rather than reporting.

**Enforced by**: `visual_qa.py::Commentary positioned above first
chart` (per tab), plus the cross-tab archetype audit when added.

---

## 2. Commentary copy rules

### 2.1 Length and structure
- **2 to 4 sentences.** Single-sentence summaries read thin; >4 becomes
  a wall of text on the dashboard.
- One declarative claim per sentence. No clause-stuffing.
- Lead with the headline number when one exists ("Core CPI at 2.74%
  is …"). End with the implication ("…raising the probability of a
  hawkish pivot").

### 2.2 Voice
- Declarative analyst tone. State the assessment.
- No hedging filler: "may potentially", "might possibly", "could
  potentially", "it is possible", "arguably".
- No marketing language: "best-in-class", "world-class",
  "next-generation", "revolutionary", "leverage".
- No personal voice: no "in my opinion", "I think", "we believe".
- No pseudo-precision: "various", "a number of", "things", "stuff".

### 2.3 Facts
- Every numeric mentioned in the commentary (e.g. "WTI at $109.8")
  must match the corresponding KPI tile and raw data within the same
  render cycle. **Validator Pass 3e** enforces this.
- Never reference dates that have not happened yet without an explicit
  `pending` / `forecast` / `expected` qualifier.
- Earnings-call quotations must be transcript-verbatim per
  CLAUDE.md "Earnings Commentary — Factuality Rule".
- Forward-looking statements ("we expect", "the path remains") only
  with explicit institutional attribution (Goldman, RSM, Fed dot plot,
  etc.) — never as our own forecast.

### 2.4 Tense and quantifier hygiene
- Past tense for what happened; present tense for what is currently
  true; future tense only when sourced.
- Absolute numbers preferred over percent-of-percent ("rose 0.4pp"
  not "rose by 12% of the prior 3.4% level").
- "pp" for percentage-point change; "%" for level. Don't mix in one
  clause without disambiguation.

**Enforced by**: `scripts/_editorial_review.py` deterministic linters
(length, vocab, hedging, numeric grounding) + Agent 8 vision review
(`COPY_QUALITY`) + Validator Pass 3e (numeric cross-surface).

---

## 3. Typography

### 3.1 Font stack

| Role | Family | Rationale |
|---|---|---|
| Body, panels, commentary, charts | **`'DM Sans', system-ui, sans-serif`** | Modern geometric sans, broad Latin support, good at 11-14px |
| Code, data labels, mono surfaces | **`'DM Mono', 'Courier New', monospace`** | Numerical tabular feel, matches data theme |
| KPI tile value (`.kpi-val`) | **`'DM Serif Display', Georgia, serif`** | Tabular-numeral-friendly display serif, paired with the print-grade numeric typography pass (tnum/lnum/ss01). Same family both themes — enforced by `visual_qa.py::check_serif_scope`. |
| Other hero/stat numbers (`.card-growth`, oil/Brent price displays, sources infographic) | **`'Instrument Serif', serif`** | Editorial weight for headline figures, contrast against geometric sans |
| `<h1>` page title only | **`system-ui, -apple-system, 'Segoe UI', sans-serif`** with `font-weight:800` | Standout heading; the only place a 5th family appears |

No 6th family. Do not import additional Google Fonts. Do not switch a
body element to monospace as a visual treatment — monospace is reserved
for *data labels*, code, and technical identifiers.

### 3.2 Type ramp

| Class / role | Family | Size | Weight | Line-height | Tracking | Colour |
|---|---|---|---|---|---|---|
| Page `<h1>` | system sans | clamp(22, 5vw, 34)px | 800 | 1.1 | -.02em | --text |
| Hero stat number (`.card-growth`) | Instrument Serif | 18-22px | 400 | 1.0 | -.01em | --text |
| KPI tile value (`.kpi-val`) | DM Serif Display | 22-36px (hero variant larger) | 400 | 1.0-1.05 | -.01em to -.02em | --text |
| Section title (architecture page) | DM Mono | 11px | 700 | 1.2 | .12em UPPER | --muted |
| Panel title (`.panel-title`) | DM Sans | 17px | 600 | 1.25 | -.01em | --text |
| Panel subtitle (`.panel-sub`) | DM Sans | 10px | 400 | 1.4 | 0 | --muted |
| Eyebrow (`.eyebrow`) | DM Sans | 10px | 400 | 1.0 | .20em UPPER | --muted |
| Subtitle (`.subtitle`) | DM Sans | 11px | 400 | 1.45 | 0 | --muted |
| Body / commentary (`.fc-note`) | DM Sans | 12.5-13px | 400 | 1.65 | 0 | --text2 |
| Table header (`.dtable th`) | DM Sans | 11px | 500 | 1.2 | 0 | --dim |
| Table cell (`.dtable td`) | DM Sans | 11px | 400 | 1.35 | 0 | --text2 (first col), --text (others) |
| Source line (`.src`) | DM Sans | 9-10px | 400 | 1.5 | 0 | --muted / --dim |
| Status pill | DM Mono | 8-9px | 700 | 1.0 | .10em UPPER | semantic |
| Nav button (`.nav-btn`) | DM Sans | 13px | 500 | 1.0 | 0 | --muted (off), --accent (active) |
| Sort button (`.sort-btn`) | DM Mono | 10px | 400 | 1.0 | 0 | --dim |

### 3.3 Rules
- Body text **never** exceeds 14px in commentary contexts.
- Headlines **never** drop below 16px.
- Monospace never appears in flowing prose; only in labels, code,
  technical identifiers (e.g. `claude-sonnet-4-6`).
- Numerical tables align right and use `font-variant-numeric: tabular-nums`
  where supported.
- Line-height inside chart titles is 1.2; inside body 1.55-1.65; never
  above 1.75 (looks loose).

### 3.4 Tabular figures

For any column that compares numbers (KPI tiles, dtable values, chart
axes), apply `font-variant-numeric: tabular-nums` so digit widths
align. Without this rule, `1,234` and `9,999` shift columns visually.

---

## 4. Colour contract

### 4.1 Variable palette (rendered ground truth)

Defined on `:root` in `index.html` near line 406. **Agents must read
this section, not invent colours.**

```
--bg      #F7F8FA    page background
--bg2     #EEF1F7    secondary background (table header, hover)
--card    #FFFFFF    panel / card background
--card2   #F1F4F9    nested card background

--border  #E2E8F0    default 1px border
--bord2   #CBD5E1    emphasised border (focus, separators)

--text    #0D1B2A    primary text   (rgb 13, 27, 42)
--text2   #334E68    body / commentary (rgb 51, 78, 104)
--muted   #7A8FA8    labels, sources, metadata (rgb 122, 144, 168)
--dim     #94A3B8    de-emphasised metadata, placeholders

--accent  #336BCC    primary brand blue (link, focus, primary chart series)
--acc2    #2B5AB3    accent-darker (hover, pressed)
--blue    #336BCC    alias of --accent

--green   #1A9E5A    confirmed / good / direction-positive
--red     #D64045    critical / risk / direction-negative
--amber   #CC8A00    warning / watch / pending
--purple  #8878B8    AI / LLM-driven / agentic surfaces
```

These resolve to the values `visual_qa.py::Commentary color matches
palette` checks against. Any change to the CSS variable block MUST be
mirrored here AND in the check's `allowed_colors` set.

### 4.2 Semantic colour usage

| Use case | Colour | Notes |
|---|---|---|
| Primary brand / link / focus / primary chart series | `--accent` | The "default" blue everything falls back to |
| Hover / pressed brand state | `--acc2` | One shade darker |
| Direction up (in a *good* metric) | `--green` | e.g. GDP, employment, savings |
| Direction up (in a *bad* metric) | `--red` | e.g. CPI, unemployment, delinquency |
| Direction down (in a *good* metric) | `--red` | "Worsening" |
| Direction down (in a *bad* metric) | `--green` | "Improving" |
| Critical / shock / pipeline-blocking | `--red` | Validator critical, shock-tracker confirmed |
| Watch / warning / pending | `--amber` | Validator warning, "pending" earnings tile |
| Confirmed / shield / validator | `--green` | Pass status, "✅" badge background |
| AI / LLM-driven / agentic | `--purple` | Every LLM-bearing surface; never deterministic |

The direction-coding rule above is the same as Bloomberg: *up in red*
when up is bad. Failure to follow it is the most common visual bug.

### 4.3 Chart palette

Restricted; do not deviate.

| Slot | Colour | Used for |
|---|---|---|
| Primary line / bar | `--accent` #336BCC | The principal series |
| Secondary line / bar | `--purple` #8878B8 | Comparison / AI / prior period |
| Tertiary / overlay | `--amber` #CC8A00 | Forecast band, threshold marker |
| Up bars (in MoM views) | `--red` #D64045 at 60-80% | Direction up |
| Down bars (in MoM views) | `--green` #1A9E5A at 60-80% | Direction down |
| Reference baseline | `--dim` #94A3B8 | Annual average dashed line |
| Recession band | `rgba(13,27,42,.06)` | Tufte-grade subtle grey |
| Grid lines | `--border` #E2E8F0 at 60% | Y-axis grid |

Charts with >3 series should re-design (split into two charts) before
adding a 4th colour.

### 4.4 Forbidden

- Gradients with more than 2 stops.
- Colours not in §4.1 (no purple→pink, no lime, no teal).
- Decorative tints (e.g. coloured panel backgrounds for "warmth").
- Saturation above the named values. Don't bump a colour because
  "it looks brighter" — the value is fixed.

### 4.5 Annotation contract

Chart annotations (reference lines, bands, event markers) are the
editorial voice of the chart. They are the part a CEO actually reads.
Inconsistent annotation strings across charts ("Oil shock" here,
"Mar 2026 oil shock" there, "Hormuz shock" in prose) is the most
common amateur-hour signal in financial dashboards. Lock them down.

**Lexicon — one phrasing per concept, sentence case, no parentheticals
on plot.** This table is the source of truth; if a chart wants to use
one of these events, it must use the exact string in column 2.

| Concept | Label (verbatim) | Colour | Notes |
|---|---|---|---|
| Fed inflation target | `Fed 2% target` | `--green` #1A9E5A, dash `[6,4]` | Horizontal line at y=2.0 |
| FOMC long-run neutral | `Neutral rate, 2.5–3.0%` | fill `rgba(26,158,90,.10)`, label `#0F7A45` | Horizontal band y1=2.5, y2=3.0 |
| Strait of Hormuz oil event | `Hormuz shock, Mar 2026` | `--amber` #CC8A00, dash `[4,3]` | Vertical at x=`2026-03-01` |
| NBER recession | (no plot label — see §4.3) | `rgba(13,27,42,.06)` | Vertical band, label in panel-sub only |

**Typography.**

- Annotation labels use the same font stack as axis labels:
  `'DM Mono', monospace`, 10px, semibold or bold.
- White pill background at 92% opacity behind the text so the label
  reads cleanly over any series colour.
- Label anchors at the *near* edge of the line/band, never floating in
  the middle of the chart. Horizontal lines anchor top-left, bands
  top-right, vertical events top of the line offset right (flip left
  if overflow).

**Series-weight rule.** Series must visually beat annotations. Series
lines: 2px solid; annotation lines: 1.5px dashed. If the eye reads
the annotation before the data, the dash is too heavy or the colour
too saturated — rework before shipping.

**Adding new events.** Before introducing a new label, add a row to
the table above and update `scripts/visual_qa.py` annotation-presence
check (`check_chart_annotations`). Ad-hoc labels added directly in
`index.html` will fail CI.

---

## 5. Spacing and rhythm

### 5.1 Scale (8-pt base)

```
Token   Value   Use
xs      4px     Tight gaps inside a chip / between an icon + label
s       8px     Between siblings inside a row, table cell padding
m       12px    Inside cards, between paired tiles
l       16px    Vertical rhythm between panels, two-up gap
xl      20px    Panel inner padding (top/bottom)
xxl     24px    Section-level gap, panel inner padding (sides)
xxxl    32px    Between page chrome and first content
```

The dashboard uses these tokens implicitly. New code should snap to
the scale; round 14px → 16, 22px → 24.

### 5.2 Panel padding

`padding: 20px`. Override only via the existing classes; no inline
`padding` overrides on `.panel`.

### 5.3 Vertical rhythm

- `metric-row` → next element: 16px.
- `.panel` → next `.panel`: 16-20px.
- `.fc-note` (commentary) → next `.panel`: 12-16px.
- `<h1>` → subtitle: 5px. Subtitle → KPI strip: 22px.

### 5.4 Hero / page top

```
body padding-top:                  28px
<h1> → subtitle:                   5px
subtitle → kpi-strip:              22px
kpi-strip → nav-btn row:           10px
nav-btn row → first tab panel:     16px
```

### 5.5 Density

Some tabs are denser than others by design (`oil`, `banks`). Density
is acceptable when the content is reference-grade (tables, multiple
tile rows). It is NOT acceptable when it crowds chart canvases or
clips labels.

Spacing inconsistencies (one panel uses 32px margin-bottom while its
peers use 16px) are CEO-grade defects.

---

## 6. Charts (Chart.js conventions)

### 6.1 Universal rules

- Lines are **continuous**. No broken segments unless data is
  genuinely sparse and that sparseness is annotated in the renderer.
- Y-axis baseline is 0 for counts / volumes; source-aware for rates
  (e.g. UNRATE baseline 3.0, not 0). Cite the chosen baseline in the
  panel subtitle when it deviates from 0.
- Legends present for any chart with 2+ series, positioned `top:right`.
- X-axis labels rotate if they would overflow. Never overflow.
- Tooltips enabled; show value + label + (optional) source.
- Chart background transparent so the `.panel` colour shows through.
- Chart grid `var(--border)` at 60% opacity, dashed for major
  gridlines, no minor gridlines.
- Chart font inherits from body (`'DM Sans'`); never set a chart-only
  font.

### 6.2 Series colour assignment

| Position | Colour |
|---|---|
| 1st (primary) | `--accent` |
| 2nd | `--purple` |
| 3rd | `--amber` |
| 4th+ | re-design |

### 6.3 Type-specific rules

**Line chart**
- Stroke width 2px (mobile 1.5px).
- Point markers only at the most-recent value, unless the series has
  ≤12 points (then every point gets a 2-3px dot).
- Anti-alias on; tension 0 (straight segments) unless the series is a
  natural curve (yield curve uses tension 0.2 — acceptable).

**Bar chart**
- Bars 60-70% width of their slot. Gap between bars matches gap
  between groups in grouped bars.
- Border radius 2-3px on the top corners only.
- Categorical X axis: 9-10px font.

**Stacked area**
- Use only for cumulative contribution stories (e.g. NFP by sector).
- Top series uses `--accent`; lower series shade down by 15-20% per
  layer.

**Sparkline / micro-chart (inside KPI tile)**
- 1.5px stroke, no axes, no grid, no labels.
- Width: full tile width. Height: 32-40px.
- Last point marked with a 3px filled dot in `--accent`.

**Dot plot / scenario panel**
- Each scenario one dot, sized 5-6px.
- Vertical reference line at consensus value (`--dim`, dashed).

**Two-y-axis chart**
- Avoid where possible. When unavoidable: primary axis on the left in
  `--accent`; secondary on the right in `--purple`; clearly label both
  axes with their unit; both axis lines `--border`.

### 6.4 Recession bands

When showing long histories, NBER recession bands as `rgba(13,27,42,.06)`
filled rectangles. Never use the brand or semantic colours for these.

### 6.5 Annotations

- Threshold lines: `--amber` dashed.
- Forecast / projection: `--accent` dashed at 50% opacity.
- "Now" marker: `--accent` solid vertical line, 1px.
- Annotation labels: 9-10px DM Mono, 60% opacity background pill.

### 6.6 Empty / sparse data

If a chart has <2 data points: render the panel with a `<div class="empty">`
"Awaiting first observation" message at 12px `--muted`. Do **not**
render an empty or near-empty canvas.

**Enforced by**: Agent 7 (`Chart canvas N has size`, `No JS exceptions`)
+ Agent 8 (`BROKEN_LINE`, `LABEL_OVERLAP`, `LABEL_TRUNCATED`,
`EMPTY_CHART`, `MISSING_LEGEND`, `SPARSE_DATA`, `FORMAT_ERROR`).

---

## 7. KPI / metric tiles

### 7.1 Anatomy

```
┌────────────────────────────────────────────┐
│ LABEL (DM Mono 9px UPPER, --muted)         │
│ VALUE (DM Serif Display 22px, --text)      │
│ Δ delta · direction · period (DM Sans 11px)│
└────────────────────────────────────────────┘
```

Width 175-220px (auto-fill, minmax(175px,1fr)). Height auto, typically
~70-80px. Inner padding 12px 14px. Border 1px `--border`. Radius 8px.

### 7.2 Direction indicators

- Up arrow `↑` for direction-up; down arrow `↓` for direction-down.
- Colour per §4.2 (up-in-a-bad-metric is `--red`).
- Direction arrow ALWAYS precedes the delta number.

### 7.3 Status decoration

For metrics with a status (KPIs that are "alert" / "watch" / "ok"):
- 3px top-edge accent bar in semantic colour.
- Or a small DM Mono pill in the top-right corner.
- Never both.

### 7.4 Forbidden in tiles

- `NaN`, `undefined`, `null`, `[object Object]`. Pipeline bug.
- Decimal places beyond what the source publishes (no `4.30%` if FRED
  publishes `4.3`).
- Mixed units in a tile cluster (don't put `%` next to `$/bbl` next to
  `K jobs` in one row without clear unit labels).

**Enforced by**: `visual_qa.py::No undefined/NaN/null values`,
`KPIS no NaN/undefined`.

---

## 8. Panels and cards

### 8.1 Anatomy

```
┌──────────────────────────────────────────────┐
│ .panel-title    (DM Sans 17px, --text)       │
│ .panel-sub      (DM Sans 10px, --muted)      │
│ [content — chart canvas, table, list, etc.]  │
│ <p class="src"> attribution (9-10px --muted) │
└──────────────────────────────────────────────┘
```

Panel: white background, 1px `--border`, 12px radius, 20px padding,
16px margin-bottom, subtle hover lift (`0 4px 16px rgba(0,0,0,.06)`).

### 8.2 Title hierarchy

- `.panel-title` is the only allowed heading inside a panel. Do not
  nest `<h2>`/`<h3>` inside panels.
- Sub-sections inside a panel use a 10-11px DM Mono divider label, not
  a heading.

### 8.3 Sub-headers

If a panel has multiple distinct content blocks, use:
- A 1px `--border` horizontal divider between them.
- A 10px DM Mono UPPERCASE block label above each.

Don't use coloured backgrounds to visually group blocks.

### 8.4 Inner grids

- Two-up of charts inside a single panel: 12px gap.
- Tile grid inside a panel: `auto-fill, minmax(160px, 1fr)`, 10px gap.

### 8.5 Panel variants

| Variant | When to use | How it differs |
|---|---|---|
| Default `.panel` | Standard data card | White, 1px border |
| Compact (`.panel.compact`, *future*) | Reference tables, dense lists | 12px padding, 10px font |
| Highlight (*future*) | "Hero metric of the page" | 4px left-edge accent in `--accent` |

New variants need a §-entry here before they ship.

---

## 9. Tables

### 9.1 `.dtable` conventions

- Header row: 11px, weight 500, colour `--dim`, background `--bg2`,
  bottom border 2px `--border`. Non-first columns right-aligned;
  first column left-aligned.
- Body row: 11px, padding 7px 10px, bottom border 1px `--bg`. First
  column colour `--text2`; other columns colour `--text` right-aligned.
- Last row (totals or summary): weight 600, no bottom border,
  background `--bg2`.
- Hover row: background `--bg2`.
- Sticky first column on overflow (mobile horizontal scroll).

### 9.2 Column types

| Type | Alignment | Format | Example |
|---|---|---|---|
| Name / label | left | text | "JPMorgan" |
| Currency | right | `$X,XXX` with `tabular-nums` | "$1,234" |
| Percent | right | `X.X%` with sign | "+1.4%" |
| Percentage-point | right | `X.Xpp` with sign | "−0.2pp" |
| Basis points | right | `X bps` | "47 bps" |
| Count | right | `X,XXX` with `tabular-nums` | "11,500" |
| Date | left | `MMM DD, YYYY` or `YYYY-MM` | "Apr 14, 2026" |
| Status | center | pill (see §13) | "🟢 Confirmed" |
| Source link | right | small text + `↗` | "FRED ↗" |

### 9.3 Number formatting

- Always use the source's published precision. Don't add false
  precision (BLS publishes `4.3%`, not `4.30%`).
- Trailing zeros only when the precision is meaningful (`2.50%` if
  the precision matters; `2.5%` otherwise).
- Comma-thousands separators for >999.
- Negative numbers: `−` (U+2212), NOT `-` (hyphen). The renderer should
  substitute when patching.
- Currency symbol attached: `$1,234` (no space).
- Units in header, not in cells: header "Volume ($B)", cells "1,234".

### 9.4 Sorting

When a table is sortable: clickable column header, arrow indicator
(`↑`/`↓`) at end of label, indicator colour `--accent`. Don't show the
arrow on unsorted columns — only the active sort.

### 9.5 Empty tables

Render a single row "No data available for this period" at 11px
`--muted`, instead of an empty `<tbody>`.

---

## 10. Status indicators / pills / badges

### 10.1 Taxonomy

| Class of state | Background | Border | Text | Example label |
|---|---|---|---|---|
| Confirmed / ok | `rgba(26,158,90,.10)` | `rgba(26,158,90,.30)` | `--green` | "Confirmed" |
| Watch / pending | `rgba(204,138,0,.10)` | `rgba(204,138,0,.30)` | `--amber` | "Pending" |
| Critical / risk | `rgba(214,64,69,.10)` | `rgba(214,64,69,.30)` | `--red` | "Risk" |
| AI / agentic | `rgba(136,120,184,.10)` | `rgba(136,120,184,.30)` | `--purple` | "Claude Sonnet" |
| Neutral / info | `--bg2` | `--border` | `--text2` | "Quarterly" |

### 10.2 Form

DM Mono 8-9px, weight 700, uppercase, letter-spacing .10em, padding
2px 8px, border 1px in border colour above, border radius 4px.

### 10.3 Placement

- Inside KPI tiles: top-right corner.
- Inside table rows: in the "Status" column, centered.
- Inside section titles: trailing, after a 6px gap.

### 10.4 Forbidden

- Pills wider than 90px. If you need more space, it's not a pill — it's
  a sub-header (see §8.3).
- Pills with shadows or gradients.
- More than 2 pills adjacent — too noisy; pick the most informative.

---

## 11. Iconography and emoji policy

### 11.1 Allowed inline emoji

The dashboard uses minimal emoji as section/tab markers. The current
allowed set is:

```
📋  Commentary panel marker
📊  Section title prefix in oil/banks tabs
📈  "Up trend" or "Section: Price" marker
📉  "Down trend"
🔴  Critical status (in copy, not as decoration)
🟢  Confirmed status (in copy)
⚠   Warning / watch (in copy)
🛢   Oil/energy tab marker
🏦   Bank/finance tab marker
👷   Labor/jobs tab marker
🧠   AI / agentic (architecture page only)
🔒  Lock / allowlist (architecture page only)
🛡   Validation / shield (architecture page only)
↑ ↓ ↗ ↘  Directional arrows
```

Do not introduce a new emoji without adding it to this list first.
Decorative emoji (✨, 🚀, 💯, etc.) are banned outright.

### 11.2 Heroicons / inline SVG

When an icon needs to be styleable or precise, use inline SVG with the
Heroicons or Lucide visual vocabulary (rounded, 2px stroke). Embed
SVG inline; do not load an icon CDN.

### 11.3 Size

- Inline emoji in headings: matches font-size of the heading.
- Inline emoji in body: matches body font-size.
- Inline SVG icons: 16x16px default; 12x12 in dense tables;
  20x20 in section labels.

---

## 12. Navigation (tab nav)

### 12.1 `.nav-btn` states

| State | Background | Border | Colour |
|---|---|---|---|
| Default | `#FFFFFF` | `#D1D5DB` | `#6B7280` |
| Hover | `#F9FAFB` | `--accent` at 40% | `--accent` |
| Active | `#FFFFFF` | `--accent` 1.5px | `--accent` |
| Focus | `--accent` 2px outer ring | — | inherit |

Padding 9px 18px, radius 9px, height ~38px. Gap between buttons 8px.
On overflow, the row scrolls horizontally with momentum (`overflow-x:
auto; -webkit-overflow-scrolling: touch`).

### 12.2 Meta tabs

`.nav-btn-meta` for utility tabs (Sources, Dashboard, Validator):
transparent background, no border, smaller text (12px), colour
`--dim`. Visually deferred.

### 12.3 Active indicator

The active tab uses border + text colour, NOT a coloured background
fill. A solid coloured tab button feels heavy and dates the design.

---

## 13. Source attribution

### 13.1 Where

Every panel that displays data gets a `<p class="src">` line at the
bottom. No exceptions for "obvious" sources — readers can't see what
you can't be bothered to type.

### 13.2 Format

```
Sources: <provider 1>; <provider 2>; <provider 3>. <Period if relevant>.
```

- Semi-colons between providers; period at end.
- Full provider name on first reference per panel; abbreviation
  acceptable elsewhere ("FRED", "BLS", "BEA", "EIA").
- For research-house attributions: "Goldman Sachs Macro Outlook Jan 2026".
- For company sources: "JPMorgan Q1 2026 earnings release".

### 13.3 Style

`font-size: 9-10px`, `colour: --muted` or `--dim`, `margin-top: 10px`,
`line-height: 1.5`. Light italic discouraged (looks blog-y, reads worse).

### 13.4 Links

External source links use `target="_blank" rel="noopener"` and a
trailing `↗`. Do NOT colour the link `--accent` — keep it `--muted`
with underline on hover only. The dashboard is read-mostly; visible
link colour pulls the eye away from the data.

---

## 14. Empty / loading / error states

### 14.1 Empty (no data yet)

Panel renders as normal, but content area shows a single line of
12-13px `--muted` text:
- Chart: "Awaiting first observation — next publish: <date>".
- Table: a single "No data available for this period." row.
- Tile: dash `—` (em-dash) in `--dim` instead of the value; label
  unchanged.

### 14.2 Loading

The dashboard renders static HTML — there is no per-panel "loading"
state in the user-facing sense. Validator-tab progressive loading is
the only exception: "Loading validation report…" in `.fc-note` style.

### 14.3 Error

Panel borders shift to `--red` at 30% opacity. A 4px left-edge stripe
in `--red`. Error message in `.fc-note` style with the recommended
remediation: "Pipeline error — see incident report yyyy-mm-dd.md."

### 14.4 Skipped (CI environment)

Tiles for charts not rendered in the current run: dashed `--border`,
`--dim` text "Skipped — see validation_report.json". No console errors.

---

## 15. Motion and animation

### 15.1 Allowed motion

- **Tab switch**: 300ms ease-out fade-in on the activating panel
  (`@keyframes tabFadeIn`). One pass; no looping.
- **Panel hover**: 150ms ease-out shadow lift (already in CSS).
- **KPI mount**: 350ms ease-out fade-up cascade on first paint of the
  page (already in CSS).
- **Active sparkline**: a single 800ms `dasharray` reveal on first
  paint; static thereafter.

### 15.2 Forbidden motion

- Looping animations (rotating icons, pulsing borders, bouncing dots).
- Motion to indicate severity (a red shaking pill is amateur).
- Auto-rotating carousels.
- Page-level transitions or hero animations.
- Parallax.
- Lottie or `<video>` autoplay.

### 15.3 Durations

| Element | Duration | Easing |
|---|---|---|
| Hover state change | 150ms | ease |
| Tab switch | 300ms | ease-out |
| Panel mount | 350ms | ease |
| Page-load reveal cascade | 350ms each, 70ms stagger | ease |

### 15.4 `prefers-reduced-motion`

When the OS reports reduced motion, ALL of the above are disabled and
elements render in their final state. Implement once in a single
`@media (prefers-reduced-motion: reduce)` block.

---

## 16. Accessibility

### 16.1 Contrast minimums (WCAG AA)

- Body text on `--bg`: `--text2` over `--bg` = 7.1:1 (passes AAA).
- `--muted` over `--bg`: 4.7:1 (passes AA). Do not use for body
  prose — only labels, metadata.
- `--dim` over `--bg`: 3.4:1 (fails AA for body). Restrict to
  decorative / placeholder text only.
- Buttons: hover/focus state must have ≥3:1 against background.

### 16.2 Focus rings

- Native `:focus-visible` outline kept. Override only with the same
  contrast: `outline: 2px solid var(--accent); outline-offset: 2px`.
- Never remove focus rings on interactive elements.

### 16.3 Keyboard navigation

- Tab nav row is keyboard-navigable via arrow keys + Enter (existing).
- Tables with sortable columns have `<th>` as `<button>` semantics so
  they're keyboard-operable.
- Modal/dialog patterns trap focus (none currently present).

### 16.4 Screen-reader labels

- KPI tiles: `<span class="sr-only">` describing the value's meaning
  ("Up 0.4 percentage points versus prior month").
- Chart `<canvas>`: `aria-label` summarising the chart's content.
- Status pills: `aria-label` spelling out the status word.

### 16.5 Colour-only encoding

Never encode meaning in colour alone. Status pills always carry text;
direction arrows always accompany delta colour.

---

## 17. Responsive behaviour

### 17.1 Breakpoints

| Name | Width | Behaviour |
|---|---|---|
| Phone | ≤700px | `.two-up` collapses to 1-col; metric tiles shrink to 160px min; tables scroll horizontally |
| Tablet | 701-1024px | Default grid; nav row may wrap to 2 lines |
| Desktop | ≥1025px | All grids active; max-width 1280px container; centered |

### 17.2 What does NOT collapse

- The KPI strip — flex-wraps but each tile stays full-width if needed.
- Source lines — wrap but never truncate.
- Panel titles — wrap to 2 lines max; never ellipsis.

### 17.3 What DOES collapse

- `.two-up` → single column at ≤700px.
- `.fc-grid` → single column at ≤700px.
- Multi-column tables → horizontal scroll with sticky first column.

### 17.4 Touch

Hit targets ≥44x44px on phone. Tab buttons increase to 42px height at
≤700px; nav-btn font stays the same (don't shrink readable text).

---

## 18. Editorial conventions (numbers, dates, units)

### 18.1 Numbers

- Thousands separator: comma (`1,234`).
- Decimal separator: period (`1.5`).
- Negative: minus glyph `−` (U+2212), not hyphen.
- Percent: no space (`2.5%`).
- Currency: no space, ISO symbol (`$1,234`, `€1,234`).
- Range: en-dash (`2.0–2.5%`), not hyphen, no spaces.
- Approximate: tilde with space (`~$110/bbl`).

### 18.2 Dates

| Granularity | Format | Example |
|---|---|---|
| Day | `MMM DD, YYYY` | Apr 14, 2026 |
| Month | `MMM 'YY` or `MMM YYYY` | Apr '26 or Apr 2026 |
| Quarter | `QN YYYY` | Q1 2026 |
| Year | `YYYY` | 2026 |
| Date range | `MMM–MMM YYYY` | Mar–May 2026 |
| Time | `HH:MM UTC` (24h) | 12:00 UTC |

### 18.3 Units

| Unit | Symbol | Notes |
|---|---|---|
| Percent | `%` | Of a total |
| Percentage point | `pp` | Change of a percent |
| Basis point | `bps` (or `bp` singular) | 1bp = 0.01pp |
| US dollar | `$` | `$X,XXX` |
| Billion / million / thousand | `B`, `M`, `K` | Always uppercase, attached |
| Per gallon | `/gal` | `$/gal` |
| Per barrel | `/bbl` | `$/bbl` |
| Annualised | "ann." or "annualised" in subtitle, NOT the value | "+21.2% ann." |
| Year-over-year | `YoY` | Always upper |
| Month-over-month | `MoM` | Always upper |
| Quarter-over-quarter | `QoQ` | Always upper |
| Seasonally adjusted | `SA` | In subtitle when relevant |

### 18.4 Forecasts and projections

When a number is a forecast / projection / consensus rather than an
observation:
- Label it explicitly: "Consensus 2.0% (Jan '26)".
- Cite the source-of-forecast: "GS: 1.8%", "Deloitte: 2.1%".
- Never present a forecast adjacent to an observation without labels —
  the reader can't tell the difference, and that's our failure.

---

## 19. Brand voice (page-level copy)

### 19.1 Tone

The dashboard speaks like a senior macro analyst briefing the
investment committee. Clear, specific, declarative. Calibrated
confidence — never bombast, never hedging.

### 19.2 Lead-with-the-number

When a sentence makes a quantitative claim, lead with the number:

  Good: "Core PCE at 3.2% is 120bp above target — no data-driven case for cuts."
  Bad:  "We see ongoing inflation pressures with the core PCE measure tracking above target."

### 19.3 Reader assumptions

The reader knows what "core PCE" is. The reader knows what "the
target" is. Don't define standard terms. Don't apologise for jargon
that's standard in the audience.

### 19.4 What we don't say

- We don't predict ("rates will fall in Q3").
- We don't recommend trades ("buy 10-year").
- We don't editorialise on policy ("the Fed should…").
- We don't speculate on intent ("Powell is signalling…").

We *describe* the data, *cite* the consensus, and *flag* the risks.

---

## 20. Visual QA hooks

Every rule in this guide should be checkable. The cross-reference:

| Rule | Where enforced |
|---|---|
| §1.2 Commentary above first chart | `visual_qa.py::Commentary positioned above first chart` |
| §2.1 Commentary length | `_editorial_review.py::lint_length` |
| §2.2 Forbidden vocab | `_editorial_review.py::lint_forbidden_vocab` |
| §2.3 Numeric grounding | `validator.py::check_metric_consistency` + `_editorial_review.py::lint_no_fabricated_numerics` |
| §4.1 Colour palette | `visual_qa.py::Commentary color matches palette` (extend to other surfaces as needed) |
| §6 Chart correctness | Agent 8 vision review categories `BROKEN_LINE`, `LABEL_OVERLAP`, etc. |
| §7 KPI value sanity | `visual_qa.py::KPIS no NaN/undefined` |
| §10 Pill taxonomy | Agent 8 `STATUS_DRIFT` (future) |
| §11 Emoji whitelist | Agent 8 `COPY_QUALITY` (future) |
| §16 Contrast / focus | Agent 7 future `Focus visible` check |

A rule without a check is a rule that won't survive a year of CI runs.
When a new section is added here, an enforcing check should be added
within the same PR, or a follow-up issue filed.

---

## 21. Known acceptable variations

These deviations are codified so agents can downgrade flags to
"informational":

1. **Outlook tab** uses `commentary-gdp` ID for its lead narrative
   (historical naming).
2. **Architecture page** uses its own `.stk-*` design system.
3. **Sources tab** uses denser tables (`.dtable` at 10px font).
4. **Validator tab** progressively loads its content; first paint
   shows a `.fc-note` placeholder.
5. **Oil tab** is the only chart tab with section dividers
   (`.stk-section-title`); other tabs group via paired panels.
6. **Banks tab** is the only chart tab with earnings cards as a
   first-class section (the `BANK_COMMENTARY` JS const).

---

## 22. Update policy

- This document is **human-curated**. Agents read it; agents do not
  write it.
- Changes require a PR with before/after screenshots of the affected
  surface(s).
- When a new check lands in Agent 7 / Agent 8 / editorial review, the
  §-section it enforces gets a row in §20.
- When a CSS variable changes, §4.1 must be updated **in the same PR**
  AND the `allowed_colors` set in `visual_qa.py` must be updated, or
  the next CI run will flag it.
- A new visual variant (new panel class, new chart type, new pill
  style) requires a §-entry **before** it ships, not after.

The intent is that this document remains the durable visual contract.
A reviewer should be able to cite a §-section in any PR comment and
the author should know exactly what to fix.

---

## 23. Uplift extensions (2026-05-15) — visualization advisory panel

The following sub-sections were added after a panel review by ten
visualization practitioners (Economist, FT, Bloomberg, NYT/Upshot,
Tufte school, Datawrapper, Pentagram, Goldman Research, McKinsey,
Vercel/Linear). Each codifies one pattern that lifts the dashboard
from "competent data tool" to "research briefing." All ten patterns
have CSS or JS landed in `index.html`; reference implementation on
the CPI tab. Sweep across remaining tabs is incremental.

### 23.1 (§6.7) Finding-first panel titles — Economist + McKinsey

Every chart panel `.panel-title` must lead with the **finding**, not
the **topic**. The technical descriptor moves to `.panel-sub`.

- ❌ "CPI: Headline vs Core" (topic)
- ✅ "Headline CPI re-accelerates above Core for the third month" (finding)

Rules:
- One finite verb in the title (auditable: contains a verb token).
- Sentence case. No abbreviations a non-specialist would miss.
- Topic + units + window go in `.panel-sub`.

**Enforced by**: future `visual_qa.py::Panel titles contain a finite
verb`. Until that lands, reviewer responsibility.

### 23.2 (§13.2) Panel-meta strip — Goldman Sachs research

Below `.panel-sub` and above the chart canvas, every data panel
carries a `.panel-meta` strip:

```html
<div class="panel-meta">
  <span class="pm-exhibit">Exhibit NN</span>
  <span class="pm-sep">|</span>
  <span class="pm-source">BLS CPI-U</span>
  <span class="pm-sep">|</span>
  <span class="pm-asof">As of Apr 2026</span>
  <span class="pm-sep">|</span>
  <span class="pm-cadence">Refreshed monthly</span>
</div>
```

- `pm-exhibit` numbers exhibits **within a tab**; reset per tab.
- `pm-source` is the primary upstream (BLS, FRED, BEA, Cleveland Fed).
- `pm-asof` is the latest data point's period, not the render date.
- `pm-cadence` is one of "Refreshed weekly", "Refreshed monthly",
  "Refreshed quarterly", "Refreshed annually", "Refreshed daily".

When `.panel-meta` is present, the bottom `.src` line drops to a
brief sentence (the *attribution* moves up; the bottom line carries
**editorial detail**, e.g. methodology footnotes).

### 23.3 (§6.7) "So what" footer — McKinsey exhibit convention

Below every chart canvas (above `.src`), a single-sentence italic
takeaway:

```html
<div class="so-what">The 90bp headline/core gap is entirely
energy-driven; if WTI stays elevated through Q2, core resumes
climbing as transport costs transmit.</div>
```

- ≤ 140 characters.
- One finite verb.
- Implication, not description. Lead with the consequence.
- Auto-prefixed with "So what — " via CSS `::before`. Do **not**
  type that prefix manually.
- Generated by the briefing agent (Agent 3) when it lands; today
  hand-curated as we sweep tabs.

**Enforced by**: future Validator Pass 3l (`check_so_what_footers`)
— length, verb, numeric-grounding consistent with panel data.

### 23.4 (§4.5) Now line + Last print pill — FT-style anchor

Every historical chart (>12 points) carries either a vertical "Now"
line at the most recent data point or a "Last print" pill anchored to
it showing `value · date`. JS helper `MD.buildNowAnnotation(lastX,
lastY, fmt)` returns a `chartjs-plugin-annotation` config block; opt-in
per chart by calling it during init.

### 23.5 (§6.1) Per-series baseline lookup — NYT/Upshot baselines

Y-axis floor and ceiling are anchored to each series' 10-year
**published** range, not the visible data window. Source of truth:
`data/chart_baselines.json` + JS mirror at `window.MD._baselines`.
Helper: `MD.applyBaseline(opts, "FEDFUNDS")` mutates a Chart.js
options dict to set `scales.y.min` / `.max`.

A 0.4pp move in Fed funds should visibly traverse ~10% of the panel
height — if it doesn't, the chart is auto-scaling and needs
`applyBaseline()`.

### 23.6 (§6.8) Sparkgrid — Tufte small multiples

When a tab shows ≥6 series of the same metric (banks per-bank NCO,
credit per-segment delinquency, carriers per-carrier ASM), use
`<div class="sparkgrid">` with `<div class="spark-cell">` children
instead of stacked Chart.js panels. Each cell:

```html
<div class="spark-cell">
  <div class="spark-label">JPM</div>
  <svg class="spark-svg" viewBox="0 0 100 32">
    <polyline class="spark-line" points="..." />
    <circle class="spark-last" cx="..." cy="..." r="2.5" />
  </svg>
  <div class="spark-foot">
    <span class="spark-val">2.4%</span>
    <span class="spark-delta up">+0.1pp</span>
  </div>
</div>
```

Reduces per-tab DOM and renders synchronously (no Chart.js per cell).

### 23.7 (§5.2) Briefing-zone rhythm — Pentagram whitespace

Three margin zones replace uniform 16px rhythm:

| Zone | Class | Top margin | Bottom margin | Use |
|---|---|---|---|---|
| Briefing | `.commentary-zone`, `.fc-note` | 32px | 24px | Tab commentary, scenario panel, verdict block |
| Data | `.commentary-zone-data` (or default) | 16px | 16px | Charts, KPI rows — current default |
| Reference | `.commentary-zone-reference`, `.src` | 8px | 8px | Sources, footnotes, validator output |

### 23.8 (§7.5) Dense KPI tile variant — Bloomberg density

`.metric.dense` / `.m-tile.dense` for secondary metric rows where 8-12
metrics-per-row is more readable than 4-6 spacious tiles. Reserve
default-size tiles for the *headline* metric row of each tab.

Container: add `.dense` to `.metric-row` for the tighter grid.

### 23.9 (§17.2) Mobile table row-cards — Datawrapper

`<table class="dtable responsive">` below 600px width collapses to
per-row cards. Each `<td>` should set `data-label="..."` for the
column header to appear in the card view:

```html
<td data-label="Apr'26">+2.4%</td>
```

The renderer must populate `data-label` on every non-first `<td>`
when building tables (or omit `.responsive` to keep horizontal-scroll
mode).

### 23.10 (§16.2) Shape redundancy on direction bars — a11y

Direction-coded bars (MoM up/down) must carry a shape cue in addition
to colour: utility classes `.dir-glyph-up` / `.dir-glyph-dn` append a
▲/▼ glyph. Required for any chart where bar colour is the *only*
encoding of direction (deuteranopia trap with red/green).

### 23.11 (§15.2) Motion affordances — Vercel/Linear

- **Value pulse**: `MD.pulseValue(el)` adds `.value-changed` for one
  200ms scale animation. Call when a KPI value changes between
  renders.
- **Skeleton loader**: `.skeleton` class on a value node shows a
  shimmering placeholder while data loads.
- **Tab cross-fade**: documented; ships in a follow-up PR after
  `.tab-panel` visibility model migrates from display:none to
  opacity-only.

All motion respects `prefers-reduced-motion`.

### Implementation status (2026-05-15)

| § | Pattern | CSS / JS | Reference tab |
|---|---|---|---|
| 23.1 | Finding-first titles | n/a | CPI (6/6 panels) |
| 23.2 | Panel-meta strip | ✅ `.panel-meta` | CPI (6/6 panels) |
| 23.3 | "So what" footer | ✅ `.so-what` | CPI (6/6 panels) |
| 23.4 | Now line + pill | ✅ `MD.buildNowAnnotation` | none yet (helper landed) |
| 23.5 | Baseline lookup | ✅ `MD.applyBaseline` + JSON | none yet (helper landed) |
| 23.6 | Sparkgrid | ✅ `.sparkgrid` | none yet (component landed) |
| 23.7 | Briefing rhythm | ✅ `.commentary-zone*` | global (applies to `.fc-note`) |
| 23.8 | Dense tile | ✅ `.metric.dense` | none yet (class landed) |
| 23.9 | Mobile row-cards | ✅ `.dtable.responsive` | CPI category table |
| 23.10 | Shape redundancy | ✅ `.dir-glyph-*` | none yet (class landed) |
| 23.11 | Motion | ✅ `MD.pulseValue` + skeleton | none yet (helper landed) |

Sweep order for follow-up tabs: GDP → Jobs → Wages → Unemployment →
PCE → Yield → Housing → Credit → Banks → Oil → Outlook. Banks and
Credit also receive sparkgrid replacement of their per-bank panels.

---

## §24 — Futuristic ambient pass (PR1 of 3, 2026-05-15)

The "futuristic" remit is a restraint exercise: signal the chart is
**alive and current** without sacrificing data-ink discipline (§4) or
CEO-grade legibility (§1). Three additions, two affordances. No third-
party libs.

### 24.1 — Breathing "now" dot

A single 8px dot, painted in the foreground series colour, sits at the
last printed value and emits a slow ring (1.8s scale-2.4 ease-out,
opacity .45→0). This is the only chart element allowed to animate
continuously, and it pulses **once per chart at most** — on the
foreground series. The animation pauses when the user enables
`prefers-reduced-motion`.

Implementation: DOM overlay via `MD.addPulseMarker(chart [, idx])`
(see `index.html` UPLIFT-2026-05-PR1 block). Pure CSS keyframes; no
extra `requestAnimationFrame` cost.

```css
.md-pulse-dot{width:8px;height:8px;border-radius:50%;background:var(--accent)}
.md-pulse-dot::after{animation:md-pulse-ring 1.8s ease-out infinite}
```

### 24.2 — Annotation-on-scroll (briefing rhythm motion)

`.panel-meta` and `.so-what` fade up (4px translate, 420ms) when the
panel first scrolls into view. Staggered: meta at 80ms, so-what at
280ms — this preserves the read-order rhythm of §23.7. Chart canvas
content is **not** animated (charts must render fully on first paint
so a screenshot taken before scroll still reads correctly). Disabled
under `prefers-reduced-motion`.

Implementation: `IntersectionObserver` (rootMargin -10% bottom,
threshold 0.05), single-fire via `unobserve()`. The `.pre-reveal`
class is the hiding state; `.revealed` is the resolved state. If JS
fails, panels never get `.pre-reveal` and stay fully visible.

### 24.3 — Dark-mode parity

Single toggle, persisted in `localStorage.md_theme`. `<html
data-theme="dark">` swaps every palette variable from §3:

| Var | Light | Dark |
|---|---|---|
| `--bg` | `#FAFAF7` | `#0F1419` |
| `--card` | `#FFFFFF` | `#161B25` |
| `--text` | `#0D1B2A` | `#E5E9F0` |
| `--text2` | `#3F4A5C` | `#A8B2C1` |
| `--muted` | `#6B7280` | `#7A8696` |
| `--border` | `#E2E8F0` | `#243042` |
| `--accent` | `#336BCC` | `#5B8CE6` |
| `--grid` | `rgba(13,27,42,.06)` | `rgba(229,233,240,.08)` |

Bloomberg up-in-red is preserved across both themes (light `#D64045`
+ dark `#FF6B6B`). No new accent colours added — dark mode is a
re-tone of the existing palette, not a new identity.

### 24.4 — Theme-toggle pill

Top-right fixed, DM Mono 10px uppercase, sun/moon glyph (☼/☾). Reads
as an instrument indicator (consistent with `.chart-now-pill` and
`.panel-meta`), not as a CTA. Hover lifts text to `--text` and
border to `--text2`. On mobile (<680px), shrinks to 9px / 5px-8px
padding so it doesn't crowd the eyebrow.

### 24.5 — Implementation status

| § | Pattern | Helper | Shipped to |
|---|---|---|---|
| 24.1 | Breathing now-dot | `MD.addPulseMarker` | helper landed; per-chart wiring pending |
| 24.2 | Scroll reveal | `MD.initScrollReveal` (auto-init) | all `.panel`s with meta/so-what |
| 24.3 | Dark palette | `:root[data-theme="dark"]` | all tabs (palette-level) |
| 24.4 | Theme toggle | `MD.toggleTheme` / `.theme-toggle` | global header |

Per-chart wiring of 24.1 (`MD.addPulseMarker`) and area-gradient
backgrounds (`MD.areaGradient`) happen in PR 2 (instrument-cluster
pass) alongside the sparkgrid ribbons, since both touch chart init
code paths.

### 24.6 — Non-goals (deliberately excluded from PR 1)

- No neon, no glow, no animated grid lines.
- No chart-type changes (charts remain Chart.js line/bar; no radial
  or 3D).
- No font swap — DM Sans + DM Mono + Instrument Serif + DM Serif Display (KPI values only) remain.
- No haptic / sound feedback.
- No "live ticker" running banner — would conflict with §4
  (data-ink). The breathing dot is the only "live" affordance.

A chart should still pass §1's screenshot test ("would not embarrass
us in a board deck") in both themes with motion disabled.

---

## §25 — Instrument cluster (PR 2 of 3, 2026-05-15)

Density. After the ambient pass adds "alive", the instrument-cluster
pass adds "informative". Tableau (Hewson) and Snowflake (Tigani) push:
your inch-per-datapoint is luxurious; load it up with signal.

### 25.1 — Sparkgrid ribbon (`.spark-ribbon`)

A 6–12 tile glance row at the top of every tab. Each tile = label
(DM Mono 9px upper) · value (DM Sans 15px 600) · delta chip
(monospace, Bloomberg up-in-red preserved). Renders the entire tab's
state in 400ms before any chart loads.

Helper: `MD.buildSparkRibbon(tabId, kpis)` (per-tab) or
`MD.populateSparkRibbons()` (sweeps `MD._sampleKPIs` map). The
sample-KPIs map is wired today; full renderer integration ships with
PR 5 (data-driven from per-tab raw signals).

### 25.2 — Regime backdrop (Chart.js plugin `mdRegime`)

Behind every time-series chart with ≥12 datapoints: NBER recession
bands (`rgba(13,27,42,.06)` light, `rgba(229,233,240,.06)` dark) and
Fed cycle phase washes (hiking red-tint .045, cutting green-tint .045,
ZIRP blue-tint .04, hold transparent). Drawn `beforeDatasetsDraw` so
the data path sits on top.

Phases are hard-coded in `MD._regimes`:
- ZIRP (2008-12 → 2015-12)  · Lift-off (2015-12 → 2019-07)
- Mid-cycle cut (2019-07 → 2020-03) · COVID ZIRP (2020-03 → 2022-03)
- Hiking (2022-03 → 2024-07) · Plateau (2024-08 → 2025-09)
- Cutting (2025-10 → ongoing)

Opt-in per chart: `chart.options.plugins.mdRegime = { recessions: true, fedPhases: true }`.
Charts without this key render exactly as before — zero regression risk.

### 25.3 — Frame-erase (Chart.js plugin `mdFrame`)

Tufte rule applied globally. `Chart.register(MD.mdFramePlugin)` mutes:
- Gridline color → `rgba(13,27,42,.06)` (zero-line → `.18` for emphasis)
- Tick marks → off
- Right border (`y1` axis) → off
- Axis labels → DM Mono 9px `rgba(13,27,42,.55)`

Opt-out per chart: `chart.options.plugins.mdFrame = false`. Today
every chart inherits this automatically.

### 25.4 — KPI YoY chip (`.kpi-yoy`)

Below each KPI value. Reads `data-yoy`, `data-yoy-dir`, `data-yoy-label`
attributes on `.kpi-val` / `.m-val` nodes. When the renderer emits
those attributes, `MD.injectYoYChips()` (auto-run on DOM ready) adds
the chip. No retrofit needed until renderer-side attribute support
lands; chip will appear automatically when it does.

### 25.5 — Exhibit numbering (`.exhibit-tag`)

Goldman-GIR convention. `MD.injectExhibitNumbering()` (auto-run)
walks each `.tab-panel` and prefixes every `.panel-title` with
`<span class="exhibit-tag">Ex 1</span>` etc. Skips panels marked
`.exhibit-skip` (footer / source citations). Idempotent — running
twice doesn't double-tag.

### 25.6 — Direction glyph polish

`.dir-glyph-up`, `.dir-glyph-dn`, `.dir-glyph-flat` get tighter
vertical alignment and an explicit width so a row of `▲▼●` glyphs
align to a 1em grid. Bloomberg up-in-red preserved both themes.

### 25.7 — Implementation status

| § | Pattern | Plugin / Helper | Auto-applied? |
|---|---|---|---|
| 25.1 | Spark ribbon | `MD.buildSparkRibbon` | yes (sample data; 4 tabs) |
| 25.2 | Regime backdrop | `MD.mdRegimePlugin` | opt-in per chart |
| 25.3 | Frame-erase | `MD.mdFramePlugin` | yes (global) |
| 25.4 | YoY chip | `MD.injectYoYChips` | yes (when renderer emits attrs) |
| 25.5 | Exhibit numbering | `MD.injectExhibitNumbering` | yes |
| 25.6 | Direction glyph | CSS only | yes |

---

## §26 — Decision lens (PR 3 of 3, 2026-05-15)

Decisions. After "alive" and "informative", PR 3 makes the dashboard
*useful*. McKinsey (Birchard) + BCG (Murray) push: every chart needs
a "therefore" clause. Charts that don't end in action are decoration.

### 26.1 — Threshold lines + consequence chips

`MD.mdThresholdPlugin` (Chart.js plugin) draws horizontal rules
labelled with a right-edge pill. Opt-in per chart:

```js
chart.options.plugins.mdThresholds = {
  lines: [
    { y: 2.0, label: "Fed 2% target",
      consequence: "Below → cut prob ≥60%" },
    { y: 4.0, label: "FOMC dot 4%" }
  ]
};
```

The pill renders at the right edge of the line in DM Mono 9px.
Consequence text is *not* drawn on the chart (would crowd) — it
sits below the chart as a `.consequence-chip` chip strip:

```html
<div class="consequence-row">
  <span class="consequence-chip"><strong>Below 2% target</strong> next-meeting cut prob ≥60%</span>
  <span class="consequence-chip"><strong>Above 4%</strong> hike reversal risk</span>
</div>
```

Consequence chips never claim certainty. They cite probabilities or
historical analogs ("1995 cycle: +0.4pp wage decel preceded 50bp cut
by 4 months"). Hedging is OK in chips — it's about decision *framing*,
not analyst commentary.

### 26.2 — Headline-chart promotion

`MD.markHeadlineCharts()` adds `.headline-chart` to the first
`.panel` in each tab. On wide screens (`min-width: 980px`), the
headline chart gets:
- Padding bumped 18→22px
- Title font 16→18px
- Chart canvas height +40px (`ch400` → 440px, `ch320` → 380px)

The visual hierarchy is now: headline → exhibits 2..N. McKinsey's
"one chart that tells the story" rendered.

### 26.3 — Legend-as-filter (`MD.styleLegendFilter(chart)`)

Click a series in the legend → strike its label + halve the line
opacity (Chart.js's default toggles visibility; we add the visual
cue). Helper is opt-in per chart — auto-applying would conflict with
charts that already have a custom `legend.onClick`.

### 26.4 — So-what link affordance

`.so-what a.so-link` styles cross-tab pointers as dashed-underline
accent links with a `→` glyph. Used when a so-what footer
cross-references another tab:

```html
<div class="so-what">Energy is leading the basket.
<a href="#oil" class="so-link">See Oil tab</a> for the WTI driver.</div>
```

### 26.5 — Non-goals (PR 3)

- No counter-factual sliders. Those need a small Phillips-curve
  module (PR 4 candidate, after a spec).
- No auto-generated consequence text. Chips are hand-written by an
  analyst; this prevents the dashboard from making confident
  forecasts in the user's name.
- No live regime auto-tagger. `MD._regimes` is hand-curated.

### 26.6 — Implementation status

| § | Pattern | Helper | Auto-applied? |
|---|---|---|---|
| 26.1 | Threshold lines | `MD.mdThresholdPlugin` | opt-in per chart |
| 26.1 | Consequence chip | CSS `.consequence-chip` | hand-authored |
| 26.2 | Headline promo | `MD.markHeadlineCharts` | yes |
| 26.3 | Legend strike | `MD.styleLegendFilter` | opt-in per chart |
| 26.4 | So-what link | CSS `.so-link` | hand-authored |

Sweep order for richer integration (data-driven sparkgrids,
per-chart regime/threshold opt-ins, hand-authored consequence chips):
CPI → Jobs → Yield → Oil → Banks → Credit → Housing → GDP → PCE →
Unemp → Wages → Outlook.
