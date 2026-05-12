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
| Hero numbers, large stat values, page title | **`'Instrument Serif', serif`** | Editorial weight for headline figures, contrast against geometric sans |
| `<h1>` page title only | **`system-ui, -apple-system, 'Segoe UI', sans-serif`** with `font-weight:800` | Standout heading; the only place a 4th family appears |

No 5th family. Do not import additional Google Fonts. Do not switch a
body element to monospace as a visual treatment — monospace is reserved
for *data labels*, code, and technical identifiers.

### 3.2 Type ramp

| Class / role | Family | Size | Weight | Line-height | Tracking | Colour |
|---|---|---|---|---|---|---|
| Page `<h1>` | system sans | clamp(22, 5vw, 34)px | 800 | 1.1 | -.02em | --text |
| Hero stat number (`.card-growth`, KPI value) | Instrument Serif | 18-22px | 400 | 1.0 | -.01em | --text |
| Section title (architecture page) | DM Mono | 11px | 700 | 1.2 | .12em UPPER | --muted |
| Panel title (`.panel-title`) | DM Sans | 13px | 500 | 1.3 | 0 | --text |
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
│ VALUE (Instrument Serif 22px, --text)      │
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
│ .panel-title    (DM Sans 13px, --text)       │
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
