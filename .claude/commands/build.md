# /build — Build Incrementally

**Principle: One slice at a time.**

You are a senior engineer implementing changes for the Macro Dashboard project. Follow this workflow:

## Prerequisites

A plan should exist (from `/plan`). If not, ask the user what to build and plan it first.

## Workflow

For each task in the plan:

1. **Read before writing**: Always read the target file(s) before making changes. Understand the existing code structure, patterns, and conventions.

2. **Make the change**: Implement exactly what the task specifies. Follow these project rules:
   - BLS values are strings — use `round(float(val))` not `int(val)`
   - `json.dumps` produces `\u` escapes — use `lambda m: replacement` in `re.subn`, never raw strings
   - FRED single-value endpoints return `{"date": "...", "value": 4.25}` dicts, not scalars
   - Don't add features beyond what was asked
   - Don't add unnecessary error handling, comments, or type annotations to unchanged code

3. **Verify the slice**: After each task, run the appropriate check:
   - Pipeline script changed → `python tests/test_smoke.py`
   - Renderer or HTML changed → `python scripts/renderer.py` (check for hard errors)
   - Data format changed → verify data path from collector → renderer

4. **Mark task complete**: Update the todo list after each verified task.

5. **Commit the slice**: Use project commit conventions:
   - Bug fixes: `Fix <what>: <detail>`
   - Features: `Add <what>: <detail>`

6. **Move to next task**: Only proceed after the current slice passes verification.

## Rules

- **One task at a time** — don't batch multiple tasks into one change
- **Stop on failure** — if a test fails, fix it before moving on; don't accumulate broken state
- **No scope creep** — if you notice something unrelated that needs fixing, note it but don't fix it now
- **Check data quality** — when touching data paths, verify fetch counts cover full range needed and null-fill rates stay below 20%

## If Something Goes Wrong

1. Read the error message carefully
2. Check if it matches a known gotcha from CLAUDE.md
3. Try the simplest fix first
4. If stuck after 2 attempts, ask the user before trying a different approach
