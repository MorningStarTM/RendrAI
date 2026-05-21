"""
services/reasoning_model.py
===========================
Reasoning client — generates image-generation prompts from a validated brief.
Called by node_reasoning() in agent.py.

Default provider : AWS Bedrock (Claude Sonnet)
Swap provider    : pass any ModelProvider instance to __init__
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional
from venv import logger

from backend.services.providers.model_provider import ModelProvider
from backend.services.providers.bedrock_provider import BedrockProvider, CLAUDE_SONNET


log = logging.getLogger("ReasoningClient")
    
SYSTEM_PROMPT = """You are an expert creative director and prompt engineer for AI image generation.

Given a validated creative brief with structured tags, generate 1-4 detailed image-generation prompts.

Rules:
- Each prompt must be self-contained and richly descriptive.
- Include: subject, style, lighting, mood, color, composition, quality keywords.
- Append negative prompt hints after " | negative: ".

Respond ONLY with valid JSON:
{
  "prompts": [
    {
      "index":       0,
      "description": "<short label>",
      "positive":    "<full positive prompt>",
      "negative":    "<negative prompt>",
      "full_prompt": "<positive> | negative: <negative>",
      "aspect_ratio": "1:1"
    }
  ]
}"""


class ReasoningClient:
    """
    Generates image-generation prompts from the validated brief + tags.

    Args:
        provider: Any ModelProvider instance.
                  Default: BedrockProvider with Claude Sonnet.
                  Swap to OpenRouterProvider or any other with zero changes to agent.py.

    Usage in agent.py:
        result = reasoning_client.generate_prompts(context)
        # {"prompts": [str, ...]}

    Swap provider example:
        from src.providers.openrouter_provider import OpenRouterProvider
        reasoning = ReasoningClient(provider=OpenRouterProvider(model_id="anthropic/claude-sonnet-4"))
    """

    def __init__(self, provider: Optional[ModelProvider] = None):
        self.provider = provider or BedrockProvider(model_id=CLAUDE_SONNET)
        log.info(f"ReasoningClient initialised  provider={self.provider.model_name}")

    # ── Called by node_reasoning() ────────────────────────────────────────────

    def generate_prompts(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate image-generation prompts from the validated brief.

        Args:
            context: From BriefManager.get_reasoning_context()
                {
                  "chat_id":  str,
                  "task":     "generate_image_prompts",
                  "elements": [...],
                  "tags":     [...],
                }

        Returns:
            {"prompts": [str, ...]}   ← flat list of full_prompt strings
                                        ready for ImageClient.generate()
        """
        log.info(f"ReasoningClient.generate_prompts  chat_id={context.get('chat_id')}  tags={len(context.get('tags', []))}")

        prompt  = self._build_prompt(context)
        raw     = self.provider.generate(prompt, options={"system": SYSTEM_PROMPT, "max_tokens": 2048})
        parsed  = self._parse_response(raw)

        # Extract flat list of full_prompt strings for BriefManager / agent
        prompt_objects = parsed.get("prompts", [])
        flat_prompts   = [p.get("full_prompt", p.get("positive", "")) for p in prompt_objects]

        log.info(f"ReasoningClient: generated {len(flat_prompts)} prompt(s)")
        return {"prompts": flat_prompts, "prompt_objects": prompt_objects}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        elements_json = json.dumps(context.get("elements", []), indent=2)
        tags_json     = json.dumps(context.get("tags", []),     indent=2)
        return (
            f"Brief ID: {context.get('chat_id')}\n\n"
            f"Brief elements:\n{elements_json}\n\n"
            f"Validated tags:\n{tags_json}\n\n"
            "Generate image prompts."
        )

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("ReasoningClient: response is not valid JSON — returning fallback")
            # Try to recover any long quoted strings as prompts
            fallback = re.findall(r'"([^"]{30,})"', raw)
            return {"prompts": [{"index": i, "full_prompt": p, "positive": p, "negative": ""} for i, p in enumerate(fallback[:4])]}