# Stack-Tab Restructure — Session Handoff

**Session date**: 2026-05-13
**Branch**: `claude/dashboard-visual-feedback-2uG0y` (pushed to origin)
**Latest commit**: `9d6090d Add stack-tab restructure mockups (.preview-stack/)`
**Production state**: `index.html` **unchanged**. All work lives under `.preview-stack/`.

---

## TL;DR

Spent the session iterating on the `#tab=stack` ("How the Dashboard Works") page. Produced 10 design mockups (A–J). The user converged on **Option J** as the right direction: a multi-agent / defense-in-depth narrative for an "any-level audience" (bank/lending exec → data scientist → finance analyst), with documentation-grade voice (no marketing). After two parallel expert agents (Platform Designer + Product Engineer) critiqued the I draft, J was built incorporating their changes (SVG verification edges, hero stat strip, proof artifact, ladder treatment, 3-color semantic system).

**Nothing has been ported into `buildStackTab()` yet.** All design exploration is in `.preview-stack/`.

---

## Where everything lives

| Artifact | Path |
|---|---|
| Mockup chooser page | `.preview-stack/index.html` |
| Latest / chosen direction | `.preview-stack/j.html` |
| Shared CSS | `.preview-stack/_shell.css` |
| All 10 variants | `.preview-stack/{a..j}.html` |
| This handoff | `.preview-stack/HANDOFF.md` |
| Production tab function | `index.html` line **5425**, `buildStackTab()` |
| Visual contract | `data/style_guide.md` (998 lines, governs all visual work) |
| Project rules | `CLAUDE.md` |

To review locally:
```
git fetch origin claude/dashboard-visual-feedback-2uG0y
git checkout claude/dashboard-visual-feedback-2uG0y
python3 -m http.server 8765
# Then browse to http://localhost:8765/.preview-stack/
```

---

## The design conversation — rejection patterns to NOT repeat

Each rejected direction taught a constraint. Future sessions must respect all of these:

| # | Rejected because… | Concrete constraints carried forward |
|---|---|---|
| A/B/C | "It's keep saying CEO" | No "weekly CEO briefing", no "produced for you", no italicized accent word in hero h1 |
| D | Too engineering-spec | No pseudocode (`bounded_llm_call()`), no "DAG", no "halt-on-4xx", no dark terminal code blocks |
| E | Too dry / methodology-disclosure | No "abstract" paragraph, no "Methodology Version X.Y" stamps |
| F | "Not a sales pitch" | No LIVE pulse-dot pill, no "Saves a week of work" / "Every number is traceable" benefit cards, no "Why you can trust it" defensive section, no inspirational closer |
| G | Too dense / table-heavy for "summary, any audience" | Avoid 11-row pipeline tables, 10-row C-01…C-10 control tables on this surface |
| H | Compressed too far; lost the multi-agent story | All 11 agents must be visible on the page; "multi-agent" is the headline |
| **I** | **First "this looks better"** | This is the breakthrough — multi-agent + defense-in-depth frame is correct |

**The voice that landed (J):** declarative, factual, documentation-grade. No "for you", no "trust", no benefit framing. The reader is treated as a peer.

---

## Option J — what's in the converged design

**Page shape** (top to bottom, ~2,574px total vs current production's 5,674):

1. **Hero head — 2-column grid**
   - Left: serif h1 (44px Instrument Serif, tracking −0.015em) + lede paragraph naming "multi-agent system" and "defense-in-depth"
   - Right: 300×200 inline SVG mini-glyph showing **5 sources → 11 agents → 1 dashboard**

2. **Hero stat strip — 4 editorial tiles, no card backgrounds**
   - `11 Agents`, `234 Checks per run`, `5 Public sources`, `1 Publication gate`
   - 36px Instrument Serif values, DM Mono caps labels, hairline dividers between tiles
   - "234 checks per run" is the wow line a reader can repeat

3. **§1 What it tracks** — single horizontal row, 6 compressed domain cards (Growth · Labour · Prices · Credit & rates · Banking · Energy & housing). Each card ≤80px tall.

4. **§2 Architecture** — the centerpiece
   - 5 source cards (ID in Instrument Serif 20px, publisher above in mono caps)
   - 4 agent layers: **L0 Pre-flight & Retrieval** (2 agents) → **L1 Computation & commentary** (3) → **L2 Validation & quality** [FOCUS BAND — purple-tinted, taller, right-edge purple rail] (4) → **L3 Publication** (2)
   - Agent number is metadata (top-right corner, dim mono); agent name leads in serif
   - L2 includes tick-mark visualization of check counts (10 ticks for Validator, 24 for Visual QA)
   - **SVG verification edges**: green dashed curves drawn between agent cards via JS at end of body, computing endpoints from `getBoundingClientRect`. 7 edges total: Briefing→Validator, Renderer→Validator, Renderer→Visual QA, Visual QA↔Vision Review, Validator→Repair, Earnings→Validator (C-04), Validator→Publisher (gate). `stroke:#1A9E5A; stroke-dasharray:3 4; opacity:.62; stroke-width:1.25` + small target dot.
   - Output closing card: ink-black background, 3px top border in `--verified` green, "Single-page dashboard" headline + 3 real KPI tiles ("this week's output").

5. **§3 How accuracy & reliability are maintained** — 2-column grid
   - Left: italic Instrument Serif pull-quote ("No single agent decides what ships…") + **proof artifact** chip showing a real validator finding: `C-04 · earnings_verbatim · PASS 46/46 quotes`
   - Right: **defense-in-depth ladder** — 6 rungs (L1–L6) on a vertical purple rail with numbered circles. Each rung steps +6px right as depth increases (outer → gate). Final L6 ("Publication gate") rendered in green to signal "verified out".

**No bottom "At a glance" section** — stats are at the top in the hero strip.

**Semantic colour system** (the breakthrough from Platform Designer review):
- **Ink** (`#0D1B2A`, `--text`) — deterministic agents
- **Purple** (`#8878B8`, `--purple`) — **AI surface only** (Claude-using agents)
- **Green** (`#1A9E5A`, `--verified`) — **the act of verification** (cross-check edges, the gate, the PASS pill, the L6 rung)

Three semantic colours, each load-bearing.

---

## What was NOT done (outstanding work)

### 1. Style-guide persistence (proposed, awaiting approval)
The conventions we converged on are not yet in any governing document. Proposed plan (user has not approved yet):

- **`data/style_guide.md` §2** — add explicit list of forbidden marketing constructs (CEO framing, LIVE pills, benefit-framed copy, inspirational closers)
- **`data/style_guide.md` §4.2** — add the **green = "verification / gated"** semantic, distinct from purple's AI-only usage
- **`data/style_guide.md` §X (new)** — codify the stack-tab voice (documentation-grade, four-section frame Architecture / What it tracks / Accuracy / At a glance, any-level reader test, multi-agent as the headline)
- **`.preview-stack/J-design-spec.md`** — focused component spec for the J-specific patterns (hero glyph SVG, stat strip, SVG verification-edge convention, ladder treatment, output closing card, proof artifact chip)
- **`CLAUDE.md`** — one new line pointing to the stack-tab voice section

### 2. Port into production `index.html`
The actual `buildStackTab()` function at line 5425 of `index.html` is unchanged. Production still renders the 5,674px stack tab. Porting J in requires:

- Replacing the entire `panel.innerHTML = ...` block in `buildStackTab()`
- Inlining `.preview-stack/_shell.css` tokens that aren't already in the dashboard's global CSS (most are: `--purple-ink`, `--purple-tint`, `--hiw-*` are already there)
- Adding the new `--verified` token to the dashboard's `:root` palette (currently has `--green` at `#1A9E5A` — reuse, don't introduce a new var)
- Wiring the SVG verification-edge JS into the tab build (currently the script runs at document-end in the mockup; in production it needs to run after `buildStackTab()` mutates the panel)
- Removing the existing redundant System Map SVG, Operations Matrix, Pipeline Agent Grid (three views of the same data — the brief from session start)

### 3. Validation / regression
Before any port to `index.html`:

- `python tests/test_smoke.py` — must be 29/29
- `python scripts/visual_qa.py` — must pass; will need to verify `Commentary positioned above first chart` and all cross-tab consistency checks still hold
- `python scripts/renderer.py` — verify no hard errors
- After port: re-run `visual_qa.py` and inspect for any new violations the stack tab introduces (the 224 checks)

### 4. Real data wiring
The mockup has illustrative numbers (CPI 3.8% / U-3 4.3% / 10Y–2Y 47bp / WTI $109.8 / "46/46 quotes"). The production tab should pull:
- KPI mini-preview tiles in the output closing card → real values from `signals.json` via `renderer.py` (similar to how other tabs render their KPI tiles)
- Proof artifact value (`46/46 quotes`) → real last-run value from `data/validation_report.json` Pass 3c result. If validation_report.json isn't easily readable at render time, hardcode initially with a comment noting the source.

### 5. Audience-test loop
Run two short reads on the ported page before merging:
- **30-second scan test**: does an exec leave knowing "11 agents, 234 checks, 5 sources, 1 gate"?
- **5-minute substance test**: can an analyst find the C-04 verbatim rule, the L2 focus band, the verification-edge story?

---

## Decisions outstanding (need user)

1. **Lock J as the direction**, or apply tweaks first? User implicitly converged on J but never said "ship it". Get explicit yes/no.
2. **Approve style-guide persistence plan** above. Without this, the conventions are at risk of drifting in future edits.
3. **Real data wiring approach** for the proof artifact — pull from `validation_report.json` or hardcode-with-comment?
4. **What to do with `.preview-stack/`** after the port — delete (clean), keep as historical reference, or archive to a tag like `design/stack-tab-history`?

---

## Next-session actions, in order

1. **Read this handoff** + glance at `.preview-stack/j.html` + screenshot at `.preview-stack/HANDOFF.md`'s level.
2. **Get user's go/no-go on Option J** as-is, or capture tweaks.
3. **Persist the design language** to `data/style_guide.md` + `CLAUDE.md` + write `.preview-stack/J-design-spec.md` (if user approves persistence plan).
4. **Port J into `buildStackTab()`** in `index.html` line 5425. Single file edit.
5. **Run smoke tests** (`python tests/test_smoke.py` → 29/29).
6. **Run visual_qa** (`python scripts/visual_qa.py` → no new violations).
7. **Screenshot the real `#tab=stack`** via the documented Playwright pattern and compare against `j.html`. Iterate any visual deltas.
8. **Commit + push** to `claude/dashboard-visual-feedback-2uG0y`. **Do not open PR without user request** (per CLAUDE.md branch policy — small fixes go direct to main; this is multi-file feature work so it needs a PR + review).
9. **Decide `.preview-stack/` fate** before merge.

---

## Constraints carried forward (do not violate)

- **Body text ≤14px** per `style_guide.md` §3.3
- **No marketing voice** — see rejection table above for the exact forbidden constructs
- **Multi-agent + defense-in-depth** is the headline message; do not compress agents into generic "stages"
- **3 semantic colours, each load-bearing**: ink (deterministic), purple (AI), green (verification)
- **No emojis** per CLAUDE.md
- **Smoke tests 29/29** before any push
- **Renderer + layout are off-limits to autonomous agents** per CLAUDE.md — this work is human-curated through the AI assistant
- Branch is `claude/dashboard-visual-feedback-2uG0y`; **do not push to main directly** since this is multi-file feature work

---

## Sandbox state notes (volatile — do not rely on)

- Dev server on `:8765` will die when the sandbox ends
- All `/tmp/chrome_*.png` screenshots are sandbox-only
- The branch on origin is what survives — everything we need is in the commit `9d6090d`

---

## Useful reference paths

| | |
|---|---|
| Production tab function | `index.html:5425` `buildStackTab()` |
| Production current height | 5,674px |
| J height | 2,574px (target reduction: ~55%) |
| `_shell.css` (mockup tokens) | `.preview-stack/_shell.css` |
| Verification-edge JS | bottom `<script>` block in `.preview-stack/j.html` |
| Pipeline DAG (factual) | `CLAUDE.md` "Project Architecture" — agents 0–10 |
| Validator passes (factual) | `CLAUDE.md` "Testing" — 10 passes |
| Style contract | `data/style_guide.md` §0–§5 |
| Editorial copy rules | `data/style_guide.md` §2 + `data/playbook.md` §2 |

---

## One sentence to start the next session with

> "I'm picking up the stack-tab restructure. Option J on branch `claude/dashboard-visual-feedback-2uG0y` under `.preview-stack/j.html` is the converged direction. Confirm go/no-go, then I'll persist the style-guide additions and port into `buildStackTab()` per the next-session action list in `.preview-stack/HANDOFF.md`."
