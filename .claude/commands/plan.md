# /plan — Plan How to Build It

**Principle: Small, atomic tasks.**

You are a senior engineer breaking down a feature into an implementation plan for the Macro Dashboard project. Follow this workflow:

## Prerequisites

A spec should exist before planning. If one doesn't, suggest running `/spec` first.

## Steps

1. **Review the spec**: Understand the goal, files affected, and acceptance criteria.

2. **Break into atomic tasks**: Each task should:
   - Touch 1-2 files maximum
   - Be independently testable
   - Take no more than one focused implementation step
   - Have a clear "done" condition

3. **Order tasks by dependency**: Tasks that other tasks depend on come first. Prefer this order:
   - Data layer changes (`collector.py`, `data/` files) first
   - Processing changes (`analyzer.py`, `briefing_agent.py`) second
   - Presentation changes (`renderer.py`, `index.html`) third
   - Validation updates (`validator.py`) fourth
   - Test updates last

4. **Identify risks** for each task:
   - BLS string-to-number conversions
   - Regex pattern conflicts in renderer
   - API response format assumptions
   - Data alignment / null-fill issues

5. **Define checkpoints**: After which tasks should we run tests?
   - `python tests/test_smoke.py` — after any pipeline script change
   - `python scripts/renderer.py` — after renderer or data format changes
   - `python scripts/visual_qa.py` — after any HTML/presentation change

## Output Format

```
## Implementation Plan: [Feature Name]

### Task List
1. [ ] **[Task name]** — [file(s)] — [what to do]
   - Done when: [condition]
   - Risk: [if any]

2. [ ] **[Task name]** — [file(s)] — [what to do]
   - Done when: [condition]
   - Checkpoint: run smoke tests

[...]

### Test Checkpoints
- After task N: `python tests/test_smoke.py`
- After task N: `python scripts/visual_qa.py`

### Estimated Scope
- Files modified: N
- Branch strategy: [main / feature branch]
```

Use the TodoWrite tool to track the tasks so progress is visible throughout implementation.
