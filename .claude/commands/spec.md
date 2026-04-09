# /spec — Define What to Build

**Principle: Spec before code.**

You are a senior engineer defining a feature or change for the Macro Dashboard project. Follow this workflow:

## Steps

1. **Clarify the request**: Ask the user what they want to build or change. If they've already described it, summarize your understanding back to them for confirmation.

2. **Research the codebase**: Before writing any spec, read the relevant files to understand current behavior. This project is a 6-stage Python data pipeline:
   - `scripts/collector.py` — FRED, BLS, EIA API data collection
   - `scripts/analyzer.py` — Signal scoring
   - `scripts/briefing_agent.py` — AI commentary
   - `scripts/renderer.py` — HTML patching (regex-based)
   - `scripts/validator.py` — Data quality checks (3-pass)
   - `scripts/publisher.py` — Email delivery
   - `index.html` — Single-page dashboard with inline JS constants

3. **Write the spec** with these sections:
   - **Goal**: One sentence describing what this change accomplishes
   - **Current behavior**: What happens today (with file paths and line numbers)
   - **Proposed behavior**: What should happen after the change
   - **Files affected**: List every file that will be modified or created
   - **Data flow impact**: How this change affects the pipeline (collector → analyzer → briefing → renderer → validator → publisher)
   - **Known gotchas**: Reference any relevant gotchas from CLAUDE.md (BLS string values, json.dumps escapes, FRED dict format, etc.)
   - **Acceptance criteria**: Concrete, testable conditions (including smoke test expectations)

4. **Check constraints**:
   - Will this add dependencies? If so, note CI pip install update needed
   - Will this affect `data/` files? If so, note snapshot requirement
   - Does this need a feature branch or can it go direct to `main`?

5. **Present the spec** to the user for review before any implementation begins.

## Output Format

```
## Spec: [Feature Name]

### Goal
[One sentence]

### Current Behavior
[Description with file:line references]

### Proposed Behavior
[Description]

### Files Affected
- `path/to/file.py` — [what changes]

### Data Flow Impact
[Which pipeline stages are affected]

### Gotchas
- [Relevant items from CLAUDE.md]

### Acceptance Criteria
- [ ] [Testable condition]
- [ ] Smoke tests pass (29/29)
- [ ] Visual QA passes (224 checks)
```
