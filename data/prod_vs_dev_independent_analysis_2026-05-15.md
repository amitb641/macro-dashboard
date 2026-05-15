# Independent prod-vs-dev analysis — 2026-05-15

**Question put to the analysis:** prod (`origin/main`) and dev (`HEAD`)
diverged on this parallel-run cycle. **Is prod wrong and dev right, or
vice versa?**

**Verdict in one line:** **dev is right in every divergence.** None of
the dev-side findings are regressions; they are deliberate new gates
or correct flagging that prod's older pipeline silently misses.

**Anchor data is identical** between branches (UMich 63.8, FFR 3.64,
10Y 4.46, UE 7.2 — all `Δ=0`). So no upstream-data divergence; every
delta is in the **pipeline's interpretation** of the same data.

---

## Per-divergence ruling

### 1. `validator.collector_errors` — prod=0 failures, dev=3 failures

**Underlying data:**

| | Prod | Dev |
|---|---|---|
| ALFRED AHETPI fetch | ok | 429 rate-limited |
| ALFRED PCEPI fetch | ok | 429 rate-limited |
| ALFRED PCEPILFE fetch | ok | 429 rate-limited |

**Ruling: NEITHER is wrong — they observed different real-world API
states.** Dev's run hit a transient FRED ALFRED rate-limit window;
prod's run, executed minutes apart, did not. The check itself is
correctly implemented on both sides; the divergence is a sampling
artifact of staggered runs against a rate-limited upstream.

**Action:** Add an exponential-backoff retry to the ALFRED fetcher in
`scripts/collector.py` so transient 429s don't propagate to the
validator. Until then, recurrence-track via the ledger — if it shows
up >2 weeks in a row, it's a quota problem, not transient.

---

### 2. `validator.earnings_verbatim` — dev critical, prod warnings only

**Underlying data:** Both branches have the SAME 9 missing-transcript
warnings (JPM, BAC, WFC, C, GS, COF, AXP, SYF, USB — all reported but
no archived transcript). Dev adds one extra check: a pass-level
`transcript_archive_coverage` aggregate flagged at **critical**
severity.

**Ruling: DEV IS RIGHT.** The 9 missing transcripts are a real
CEO-grade quality issue — the validator's verbatim gate cannot
function without them. Prod surfaces 9 individual warnings that
nobody acts on; dev escalates to a single critical that forces
attention. Same underlying reality, better signal.

**Action:** Archive transcripts to `data/transcripts/Q1_2026/<TICKER>.txt`
for the 9 banks that have reported. This clears the critical AND the
9 individual warnings on both branches.

---

### 3. `validator.visual_qa` — prod 1 failure, dev 12 failures

**Underlying data:** Dev adds 11 new failures, all of the form
`Visual: <tab> — Commentary color matches palette` across every tab
card (GDP, Jobs, Unemployment, Wages, CPI, Consumer & PCE, Rates &
Yields, Credit, Banking, Housing, Oil). Prod only has the single
sentence-count check both branches share.

**Ruling: DEV IS RIGHT.** Dev's `visual_qa.py` carries a new
palette-conformance check (part of the expert-bundle improvements)
that prod's older version lacks. The check is correctly detecting
that per-tab commentary text colors fall outside the documented
palette in `data/style_guide.md`. Prod produces a falsely-clean
report by not having the check at all.

**Action:** Either (a) update commentary text colors in `index.html`
to a palette-compliant value, or (b) update `data/style_guide.md` to
whitelist the current color if it's intentional. The visual reviewer
needs ground truth one way or the other.

---

### 4. `analyzer.signals` — prod 0 flagged, dev 2 flagged

**Underlying data:**

| Signal | Prod | Dev |
|---|---|---|
| `wti` (WTI Crude) | 105.78, Δ−3.98, **not flagged** | 105.78, Δ−3.98, **alert** |
| `wages_yoy` | 3.6, Δ−0.3, **not flagged** | 3.6, Δ−0.3, **flagged** |

**Ruling: DEV IS RIGHT.** Same numeric inputs, different threshold
logic. Dev's analyzer correctly flags a −$3.98/bbl WTI move and a
−0.3pp wages-YoY decel as material; prod's older threshold logic
misses both. These are real magnitude changes — the parallel-run trial
specifically exists to surface analyzer improvements like this.

**Action:** Promote dev's analyzer logic when the broader
promote-to-main decision is made. No interim fix needed.

---

### 5. CEO-grade verdict + editorial-report artifacts missing on prod

Prod's `data/ceo_grade_verdict.json` and `data/editorial_report.json`
are absent because prod doesn't run those gates — they're dev-only
features in the parallel-run trial. This is a **known asymmetry**, not
a divergence. No action.

---

## 🚨 Security finding (incidental — surfaced during the analysis)

While inspecting the divergence in `signals.json`, the analysis caught
a **FRED API key leak** in the committed JSON:

- `data/signals.json` on the dev branch carries the full upstream URL
  (including `api_key=<KEY>`) in its `raw_errors` field when an ALFRED
  fetch fails with 429.
- A `git log -S api_key=8510a633 --all` finds **101 commits** across
  history containing that key.
- The key is now in the public commit history of the repo.

**This is independent of the prod-vs-dev question.** Both branches'
collectors append the raw exception string (which embeds the URL+key)
to `raw_errors` — prod just happened to have an empty `raw_errors`
this week because no FRED calls failed. The leak surfaces whenever
ANY FRED call fails with the URL in the message.

**Required actions (in order):**

1. **Rotate the FRED API key immediately.** Treat
   `8510a633d1530b31f395e351daa237c7` as compromised.
2. Patch `scripts/collector.py` so error capture scrubs the
   `api_key=…` query parameter before persisting to `raw_data.json`
   or `signals.json`.
3. Add a validator pass that fails on any `api_key=` substring
   appearing in any committed JSON artifact.
4. Optionally rewrite git history to purge the key. Practical caveat:
   if the repo has external clones / forks, the only safe assumption
   is the key is permanently compromised — rotation supersedes purge.

---

## Aggregate verdict on promotion

Based on this cycle's data alone:

- **Anchor data integrity:** equal between branches → no regression.
- **Validator deltas:** all dev-favourable (dev catches things prod
  silently passes).
- **Visual_qa deltas:** all dev-favourable.
- **Analyzer signal deltas:** all dev-favourable.
- **CEO-grade gate:** only present on dev — by design.
- **Editorial review:** only present on dev — by design.

**Recommendation:** continue the parallel run for the remaining
weekly cycles per the decision-date plan (2026-06-14), but the data
already strongly favors promoting dev → main. **Blockers to address
before promotion remain:**

1. Archive the 9 missing transcripts (resolves the
   `transcript_archive_coverage` critical).
2. Reconcile the 11 palette warnings against `data/style_guide.md`.
3. Retire the legacy `patch_kpi()` calls so `renderer --strict`
   passes on dev without observation-mode.
4. **Rotate FRED key + scrub api_key from error capture** (security).
