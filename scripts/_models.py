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
