# /test — Prove It Works

**Principle: Tests are proof.**

You are a senior engineer verifying changes to the Macro Dashboard project. Follow this workflow:

## Test Suite

Run all three test layers in order:

### 1. Smoke Tests (required — build gate)
```bash
python tests/test_smoke.py
```
- **Expected**: 29/29 pass
- **If failures**: Fix before proceeding. These are non-negotiable.
- Tests cover: data file integrity, HTML structure, pipeline script imports, signal format

### 2. Renderer Verification
```bash
python scripts/renderer.py
```
- **Expected**: No hard errors. Benign `patch_kpi` warnings are OK (labels already updated from prior runs).
- **If errors**: Check regex patterns in renderer against current index.html structure

### 3. Visual QA (DOM-based checks)
```bash
python scripts/visual_qa.py
```
- **Expected**: 224 checks pass
- **If failures**: Check the specific DOM elements flagged — usually missing data attributes or chart rendering issues
- Note: Requires Playwright — if not available, skip and note as manual verification needed

## Data Quality Checks

If the change touched data collection or processing:

1. **Verify fetch counts**: Monthly charts need ~60 weekly observations, not 6
2. **Check null-fill rates**: >20% nulls in aligned series = fetch-count or alignment bug
3. **Trace data path**: Follow data from `collector.py` → `raw_data.json` → `analyzer.py` → `signals.json` → `renderer.py` → `index.html`
4. **Validate against report**: Check `data/validation_report.json` for any critical divergences

## After Tests Pass

Report results to the user:
```
## Test Results
- Smoke tests: NN/29 passed
- Renderer: [clean / warnings only / errors]
- Visual QA: NNN/224 passed
- Data quality: [checked / not applicable]
```

If all tests pass, the change is verified and ready for review or shipping.

## If Tests Fail

1. Identify which test(s) failed and the error messages
2. Correlate with the changes made — is the failure related to our change or pre-existing?
3. Fix the root cause (not the symptom)
4. Re-run the full suite — don't just re-run the fixed test
