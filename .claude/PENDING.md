# Pending Work — Bank Cards Redesign

## Task: Redesign CEO Commentary Cards (banks tab)

### What was done (committed & pushed to main)
- Added `BANK_THEMES` panel above cards (5 cross-bank themes, source-attributed)
- Added `_srcBadge()` helper (PREPARED=blue, Q&A=amber, SUMMARY=purple)
- Added `economy`, `lending`, `cards_loans`, `macro`, `tech_ai`, `src` fields to all 10 `BANK_COMMENTARY` entries
- All industry themes verified against earnings releases — no fabricated/implied claims

### What still needs to be done

**Redesign `BANK_COMMENTARY` data + card template** with 7 tighter sections:

```
a) CEO Commentary      — 1 key verbatim quote, 1-sentence framing
b) Q1 Financials       — EPS · Revenue · ROTCE · NII (numbers only, from press release)
c) vs. Consensus       — beat/miss + key highlights, 1 sentence
d) Cards · Loans · Deposits — 1-2 tight facts + key quote/number
e) Credit Performance  — NCO rate, provision, reserve action, 1-2 sentences
f) Macro · Policy · Regulation — 1 key CEO quote + 1 policy/reg watch item
g) AI & Tech           — 1 key quote or initiative, 1 sentence
   [Analyst & Peer Watch] — 3 bullet questions, pointed, forward-looking
```

Rules: **short, punchy, real** — every claim grounded in earnings release or call transcript. No synthesis, no editorial conclusions.

### New data field names (replacing old ones)
Old fields: `economy`, `lending`, `cards_loans`, `macro`, `credit`, `outlook`
New fields: `ceo_comment`, `financials`, `trends`, `card_loan_deposit`, `credit_perf`, `macro_policy`
Keep: `tech_ai`, `src`, `quote`, `bank`, `ceo`, `ticker`, `color`, `date`
Add: `analyst_watch` (array of 3 strings)

### New `src` keys
Old: `economy`, `lending`, `cards_loans`, `macro`, `tech_ai`
New: `ceo_comment`, `card_loan_deposit`, `macro_policy`, `tech_ai`

### Card template approach
Replace the `document.getElementById("bank-cards").innerHTML` block in `buildBanksTab()` with:
1. A `_row(icon, label, text, src)` helper const
2. Section headers: 8px uppercase muted label + icon
3. Q1 Financials section in a bg2-tinted box
4. Analyst & Peer Watch at the bottom in a bank-color-tinted box

### Compact financials per bank (verified from press releases)
- JPM:  `EPS $5.07 · Revenue $50.5B (+10%) · ROTCE 21% · NII $23.4B (ex-mkts)`
- BAC:  `NII $15.9B (+9%) · ROTCE 16% (+200bps) · Equities record $2.83B (+30%)`
- WFC:  `Revenue $21.45B (missed $21.77B est.) · CET1 10.3% · $4B returned`
- C:    `Revenue +14% · EPS $3.06 (beat $2.64) · ROTCE 13.1% · Net income +42% YoY`
- GS:   `Revenue $17.2B (2nd-highest ever) · EPS $17.55 · ROTCE 21.3% · $6.4B returned`
- COF:  `EPS $4.42 adj (missed $4.61) · Revenue $15.23B · Net income +57% YoY · NIM 7.87% (−39bps)`
- AXP:  `Revenue +11% (+10% FX-adj) · EPS $4.28 (+18%) · Spending +10% YoY (3-yr high)`
- SYF:  `EPS $2.27 adj (+20%) · NII +4% to $4.6B · NIM 15.5% (+76bps) · $43B Q1 volume (record)`
- USB:  `EPS $1.18 (+15%) · Revenue $7.3B (+4.7%) · NII +4.1% · Fee income +6.9% YoY`
- BCS:  `Q4'25: NIM 11.6% · Receivables +10% YoY · NCO ~5.2% · Q1 2026 pending Apr 30`

### Key CEO quotes per section (verified, with source type)
See full list in session summary. Short versions:

**JPM/Dimon**
- ceo_comment: `"We have to be prepared for a recession and stagflation."` (Q&A)
- macro_policy: `"The number of concerning issues remains — geopolitical tensions, inflationary pressures, high deficits, tariffs."` (Prepared)
- tech_ai: `"Deploying AI to improve efficiency ratio is a bad idea — benefits pass to the marketplace."` (Q&A)

**BAC/Moynihan**
- ceo_comment: `"We saw healthy client activity, including solid consumer spending and stable asset quality."` (Prepared)
- credit_perf: `"Charge-offs, delinquencies, and NPLs all declining vs. Q1 2025."` (Prepared)
- macro_policy: `"Watchful of evolving risks — geopolitical tensions and the sudden rise in energy prices."` (Prepared)

**WFC/Scharf**
- ceo_comment: Consumer `"resilient in the aggregate but increasingly bifurcated beneath the surface."` (Q&A)
- lending: `"Higher-income households supported; lower-income consumers face more exposure."` (Q&A)
- tech_ai: `"The long-term impact of AI on headcount is extremely significant."` (Q&A)

**C/Fraser**
- ceo_comment: `"One good first quarter does not a full year make."` (Q&A)
- macro_policy: `"We shall not allow the uncertainty to distract us from executing our strategy."` (Prepared)
- tech_ai: `"Methodically deploying AI at scale to drive revenues, process improvements, and client experiences."` (Prepared)

**GS/Solomon**
- ceo_comment: `"The geopolitical landscape remains very complex, and the ultimate impact of higher energy prices is yet to be determined."` (Prepared)
- macro_policy: `"If the resolution of the conflict drags, that will be a headwind — particularly inflation trends in Q2 and Q3."` (Q&A)

**COF/Fairbank**
- ceo_comment: `"We continue to really feel very good about our portfolio performance and the credit outlook."` (Q&A)
- macro_policy: `"If energy prices stay high for a longer period of time, that would be a real headwind for consumers."` (Q&A)
- tech_ai: `"The leverage of AI is vastly greater when AI is embedded in the company's ecosystem."` (Q&A)

**AXP/Squeri**
- ceo_comment: `"Card Member spending grew 10% — the highest quarterly growth in three years."` (Prepared); `"We really haven't seen any pull forward at all."` (Q&A)
- tech_ai: Acquired Hyper (Hypercard Network), backed by OpenAI CEO Sam Altman. Q2 close.

**SYF/Doubles**
- ceo_comment: `"The macro environment is still pretty constructive. Consumers seem to be looking past the uncertainty."` (Q&A)
- credit_perf: `"Net charge-offs peaking in Q2."` (Prepared). NCO ~5.8%; FY guide <5.5%.
- tech_ai: `"Drive AI into all aspects of our business to drive a flat headcount environment."` (Q&A) Agentic Commerce at POS.

**USB/Kedia**
- ceo_comment: `"Macroeconomic backdrop remains constructive despite some softening of sentiment."` (Prepared)
- macro_policy: `"It is turning to more core demand, which we find to be very healthy."` (Q&A)
- tech_ai: `"Our goal is to become an AI native organization."` (Prepared) $2.6B tech investment FY26.

**BCS/Venkat**
- tech_ai: `"The promise of AI is not just efficiency — it frees people up to do much more."` (Venkat, FY25 call)

### How to implement (next session)
1. Open `/home/user/macro-dashboard/index.html`
2. Replace `const BANK_COMMENTARY = [` … `];` (lines ~3544–3645) with new 10-entry array using new field names
3. Replace the card rendering block in `buildBanksTab()` (lines ~3969–3995) with new template using `_row()` helper
4. Use a Python script (not Edit tool) to avoid size limits:
   ```python
   # Read file, find markers, replace, write back
   with open('index.html', 'r') as f: html = f.read()
   # Replace BANK_COMMENTARY block
   # Replace card template block
   with open('index.html', 'w') as f: f.write(html)
   ```
5. Run `python3 tests/test_smoke.py` (must be 29/29)
6. Commit: `"Redesign bank cards: 7-section analyst tearsheet format"`
7. Push to origin main

### Grid layout note
Cards currently use `grid-template-columns:repeat(auto-fill,minmax(300px,1fr))` — keep as-is.
With 7 sections + analyst watch box, cards will be taller. That's fine — it's a dense info card now.
