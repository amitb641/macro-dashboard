# /ship — Ship to Production

**Principle: Faster is safer.**

You are a senior engineer shipping changes to the Macro Dashboard project. Follow this pre-flight and deploy workflow:

## Pre-Flight Checklist

Run all checks before shipping:

### 1. Tests Must Pass
```bash
python tests/test_smoke.py          # Must be 29/29
python scripts/renderer.py          # No hard errors
python scripts/visual_qa.py         # 224 checks (if Playwright available)
```

### 2. Git State Must Be Clean
```bash
git status                           # No uncommitted changes
git log main..HEAD --oneline         # Review what's being shipped
```

### 3. Review Commits
- All commits follow conventions (`Fix ...`, `Add ...`)
- No accidental data file changes
- No secrets in any commit (`git diff main...HEAD` scan)

### 4. Data Integrity
- Check `data/validation_report.json` — no critical divergences
- If data files changed, confirm snapshot exists via `scripts/snapshot.py`

## Ship Procedure

### If on `main` (direct fix):
```bash
git push -u origin main
```

### If on a feature branch:
1. Confirm all tests pass on the branch
2. Push the branch:
   ```bash
   git push -u origin <branch-name>
   ```
3. Ask the user if they want a PR created
4. If yes, create the PR with:
   - Clear title (under 70 chars)
   - Summary of changes
   - Test results in the description

## Post-Ship Verification

After pushing:
1. Verify the push succeeded (retry up to 4 times with exponential backoff if network error)
2. If CI is configured, monitor `.github/workflows/briefing.yml` status
3. Run `python scripts/healthcheck.py` if deploying to production

## Output Format

```
## Ship Report

### Pre-Flight
- Smoke tests: 29/29 passed
- Renderer: clean
- Visual QA: 224/224 passed
- Git state: clean
- Data integrity: verified

### Shipped
- Branch: [branch name]
- Commits: N
- Push: success

### Post-Ship
- CI status: [pending/passed/failed]
- Health check: [passed/skipped]
```

## If Something Fails

- **Test failure**: Stop. Do not ship. Fix and re-test.
- **Push failure**: Retry with exponential backoff (2s, 4s, 8s, 16s)
- **CI failure**: Investigate immediately. If it's a flaky test, note it. If it's a real failure, revert or fix.
