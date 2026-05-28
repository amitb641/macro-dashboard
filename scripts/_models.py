"""
Single source of truth for Anthropic model IDs.

Every agent that calls the Anthropic API imports the constants below instead
of hardcoding model strings. This avoids the multi-file fix-up that
followed pipeline run #116, where 'claude-sonnet-4-6-20250514' had been
copy-pasted into briefing_agent.py and visual_review.py and both 404'd
when Anthropic deprecated the alias.

When Anthropic releases a new model:
  1. Update the constant below.
  2. preflight.py (Agent 0) auto-validates the new ID against
     /v1/models on the next run; pipeline halts if it isn't served.
  3. No other file changes needed.

Naming convention: family name (no date suffix) when Anthropic offers it.
Date suffix when only the dated alias is served.

Reference: https://docs.anthropic.com/en/docs/about-claude/models
"""

# Default model for text-only AI agents (Agent 3 briefing, Agent 9 earnings)
SONNET = 'claude-sonnet-4-6'

# Vision-capable model (Agent 8 visual review — multimodal screenshots)
SONNET_VISION = 'claude-sonnet-4-6'

# Reserved for higher-stakes reasoning (not currently used in pipeline,
# kept here so when adoption is needed the constant is already centralised)
OPUS = 'claude-opus-4-7'

# Reserved for low-cost / high-throughput tasks (not currently used)
HAIKU = 'claude-haiku-4-5-20251001'

# All IDs the pre-flight should validate against Anthropic's /v1/models.
# Keep this synced with the constants above.
ALL_MODEL_IDS = sorted({SONNET, SONNET_VISION, OPUS, HAIKU})


# ── Cost model ────────────────────────────────────────────────────────
# List prices in USD per 1,000,000 tokens. Single source of truth for
# cost tracking (scripts/inspect_agent_memory.py --cost). Update if
# Anthropic pricing changes. Cache tiers use the standard multipliers:
# a cache WRITE costs 1.25× base input, a cache READ costs 0.10× base.
MODEL_PRICING = {
    'claude-opus-4-7':           {'input': 15.0, 'output': 75.0},
    'claude-sonnet-4-6':         {'input': 3.0,  'output': 15.0},
    'claude-haiku-4-5-20251001': {'input': 1.0,  'output': 5.0},
}
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT  = 0.10


def price_for(model: str) -> dict:
    """Per-1M-token price dict for a model; falls back to Sonnet rates for
    an unknown id (cost stays approximate, never crashes)."""
    return MODEL_PRICING.get(model, MODEL_PRICING['claude-sonnet-4-6'])


def cost_usd(model: str, usage: dict) -> float:
    """USD cost of one call from its logged `usage` dict. Handles cache
    tokens when present. Anthropic's `input_tokens` already EXCLUDES
    cached tokens, so the four buckets sum without double counting."""
    if not usage:
        return 0.0
    p = price_for(model)
    inp    = usage.get('input_tokens') or 0
    out    = usage.get('output_tokens') or 0
    cwrite = usage.get('cache_creation_input_tokens') or 0
    cread  = usage.get('cache_read_input_tokens') or 0
    return (
        inp    * p['input'] +
        out    * p['output'] +
        cwrite * p['input'] * _CACHE_WRITE_MULT +
        cread  * p['input'] * _CACHE_READ_MULT
    ) / 1_000_000.0
