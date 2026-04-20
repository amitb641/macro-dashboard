# U.S. Macro Dashboard — CEO Brief on Automation & AI

## One-line summary

8 autonomous agents run this dashboard. 2 are AI-powered; 6 are deterministic. They coordinate via a GitHub Actions pipeline, check each other's work at three independent layers, and block publication if anything is wrong.

**No human writes a number. No human formats a chart.** Human attention is reserved for improving the methodology, not running the system.

## Why this split matters

A deliberate design choice: not everything is AI.

AI is used where judgment helps — writing commentary that reflects nuance, or spotting visual defects a rulebook wouldn't catch. Deterministic code is used where precision matters — pulling data, computing signals, validating outputs against sources.

This is the opposite of the common failure mode where teams force AI into every step and then struggle with hallucinations where the answer needed to be exact.

| Type | Agents | What they do |
|---|---|---|
| Deterministic | Collector, Analyzer, Renderer, Publisher, Validator, Visual QA | Pull data, compute signals, render HTML, run quality checks — output is reproducible |
| AI (Claude) | Briefing, Visual Review | Write analyst commentary, visually audit each chart — output is judgment |

## The team of 8

1. **Collector** (deterministic) — pulls 60+ macro series from FRED, BLS, EIA, and UMich every pipeline run. Retries on flake, carries forward on API outage.
2. **Analyzer** (deterministic) — diffs new vs. prior data, scores risk signals, flags anomalies beyond historical norms.
3. **Briefing** (Claude Sonnet) — writes the monthly AI commentary on each tab. Reads the latest data, cross-references historical context, produces 2–3 sentence interpretive notes.
4. **Renderer** (deterministic) — patches HTML with fresh data, rebuilds charts, injects vintage-pinned historical series.
5. **Publisher** (deterministic) — emails briefing via Resend.
6. **Validator** (deterministic) — runs 5 independent passes of data quality checks. Re-fetches headline values from FRED/BLS to verify no silent drift from source.
7. **Visual QA** (deterministic) — opens the rendered page in a headless browser. Runs 224 structural checks: labels match data arrays, values in range, no null cells.
8. **Visual Review** (Claude multimodal) — actually looks at each chart. Flags "legend overlaps title," "two lines indistinguishable," "y-axis scale hides the trend."

## Three layers of cross-checking

This is the most important architectural detail. When the pipeline runs, three independent agents verify from three different angles:

- **Validator** — does the dashboard match source APIs? (catches silent drift)
- **Visual QA** — does the HTML have the right structure? (catches missing/broken elements)
- **Visual Review** — does each chart look right to human eyes? (catches visual defects the rulebook wouldn't)

If any flags a critical issue, publication is blocked and the previous version auto-rolls back. **The pipeline fails closed, not open.**

## The credibility layer (shipped in v1.1.0)

- **METHODOLOGY.md** — every threshold, rule, and formula is documented. When the Oil tab says "Phase 3 confirmed," the exact rule that fired is click-through-able.
- **Backtest harness** — rules were replayed against the 2022 Ukraine shock and 2008 Lehman-era collapse. First run caught a latent bug: the rule marked 2008's deflationary Core CPI drop as "confirmed inflation transmission" — wrong direction. Fixed and documented.
- **Vintage pinning** — BEA/BLS quietly revise historical data. The 2025 payroll benchmark alone rewrote 862,000 jobs. The dashboard now pins 7 Tier 1 series (GDP real + nominal, CPI, payrolls, wages, PCE headline + core) to ALFRED quarterly vintages.

## Operational rhythm

- **Every Friday 8 AM ET:** full pipeline runs automatically. ~2–3 minutes end to end.
- **Every 2nd Saturday of the month:** deep refresh catches Jobs + CPI releases in one pass.
- **Manual triggers:** any workflow runs on-demand through the GitHub Actions UI. No developer required.
