# /code-simplify — Simplify the Code

**Principle: Clarity over cleverness.**

You are a senior engineer simplifying code in the Macro Dashboard project. Follow this workflow:

## Scope

Identify the target: either a specific file the user mentions, or review recent changes via `git diff`.

## What to Look For

### 1. Dead Code
- Unused imports, variables, or functions
- Commented-out code blocks
- Unreachable code paths
- Backwards-compatibility shims for removed features

### 2. Unnecessary Complexity
- Abstractions used only once — inline them
- Helper functions for one-time operations — inline them
- Over-engineered error handling for impossible scenarios
- Feature flags or config for things that should just be the code
- Premature generalizations (3 similar lines > a premature abstraction)

### 3. Clarity Improvements
- Confusing variable names (especially in data pipeline context)
- Long functions that do multiple unrelated things
- Nested conditionals that could be flattened
- Magic numbers without context (especially API-related values)

### 4. Project-Specific Patterns
- Renderer regex patterns: ensure they're readable with comments if complex
- Data transformations: ensure BLS string→float→round pattern is clear
- API response handling: ensure FRED dict format is obvious
- Pipeline stage boundaries: ensure inputs/outputs are clear

## Rules

- **Only simplify, don't add features**
- **Don't change behavior** — simplification must be functionally identical
- **Don't touch what you don't understand** — if a pattern looks odd but works, research it before changing
- **Run tests after every change**: `python tests/test_smoke.py`
- **Preserve known gotcha handling** — the workarounds in CLAUDE.md exist for good reasons

## Output Format

```
## Simplification: [file or scope]

### Changes Made
1. [file:line] — [what was simplified and why]

### Removed
- N lines of dead code
- N unnecessary abstractions

### Test Results
- Smoke tests: 29/29 passed (behavior unchanged)
```
