# /review — Review Before Merge

**Principle: Improve code health.**

You are a senior engineer reviewing changes to the Macro Dashboard project. Follow this workflow:

## What to Review

Examine all uncommitted and recently committed changes on the current branch.

```bash
git diff main...HEAD
git log main..HEAD --oneline
```

## Review Checklist

### 1. Correctness
- [ ] BLS values handled as strings with `round(float(val))`, never `int(val)`
- [ ] FRED values handled as dicts `{"date": ..., "value": ...}`, not scalars
- [ ] `json.dumps` results used via lambda in `re.subn`, not raw strings
- [ ] Data fetch counts sufficient for renderer needs (e.g., 60 weekly obs for 12-month charts)
- [ ] No null-fill rates above 20% in aligned series

### 2. Safety
- [ ] No hardcoded API keys or secrets
- [ ] No deletion of data files without snapshots
- [ ] No new dependencies without CI pip install update
- [ ] No command injection or XSS vulnerabilities in renderer output
- [ ] PCE staleness warnings preserved (genuine data lag, not bugs)

### 3. Scope
- [ ] Changes match the stated goal — nothing extra added
- [ ] No unnecessary refactoring of untouched code
- [ ] No added comments, docstrings, or type annotations to unchanged code
- [ ] No speculative abstractions or premature generalizations

### 4. Pipeline Integrity
- [ ] Data flows correctly: collector → analyzer → briefing → renderer → validator → publisher
- [ ] Regex patterns in renderer still match index.html structure
- [ ] Validator checks still aligned with data format
- [ ] Version tracker updated if pipeline behavior changed

### 5. Test Coverage
- [ ] Smoke tests still pass (29/29)
- [ ] Changes are covered by existing tests or new tests added
- [ ] Edge cases considered (empty data, API failures, stale data)

## Output Format

```
## Code Review: [branch or change description]

### Summary
[1-2 sentences on what changed]

### Findings
- **[PASS/WARN/FAIL]** Correctness: [detail]
- **[PASS/WARN/FAIL]** Safety: [detail]
- **[PASS/WARN/FAIL]** Scope: [detail]
- **[PASS/WARN/FAIL]** Pipeline integrity: [detail]
- **[PASS/WARN/FAIL]** Test coverage: [detail]

### Issues Found
1. [severity] [file:line] — [description]

### Verdict
[APPROVE / REQUEST CHANGES / NEEDS DISCUSSION]
```
