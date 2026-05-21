"""
services/slm_validator.py
=========================
SLM client — validates the brief and returns structured tags.
Called by node_slm_validate() in agent.py.

Default provider : AWS Bedrock (Claude Haiku)
Swap provider    : pass any ModelProvider instance to __init__
"""

from __future__ import annotations

from asyncio.log import logger
import json
import logging
import re
from typing import Any, Dict, Optional

from backend.services.providers.model_provider import ModelProvider
from backend.services.providers.bedrock_provider import BedrockProvider, CLAUDE_HAIKU


log = logging.getLogger("SLMClient")
    
SYSTEM_PROMPT = """You are a creative brief validator.
Given a list of brief elements, extract structured tags and validate suitability for image generation.

Respond ONLY with valid JSON:
{
  "tags": [
    {"category": "subject|style|color|mood|lighting|setting|quality", "value": "<value>", "confidence": 0.0-1.0}
  ],
  "is_valid": true,
  "feedback": "<optional notes>"
}"""


class SLMClient:
    """
    Validates a creative brief and returns structured tags.

    Args:
        provider: Any ModelProvider instance.
                  Default: BedrockProvider with Claude Haiku.
                  Swap to OpenRouterProvider or any other with zero changes to agent.py.

    Usage in agent.py:
        result = slm_client.validate(context)
        # {"tags": [...], "is_valid": bool, "feedback": str}

    Swap provider example:
        from src.providers.openrouter_provider import OpenRouterProvider
        slm = SLMClient(provider=OpenRouterProvider(model_id="anthropic/claude-haiku-3"))
    """

    def __init__(self, provider: Optional[ModelProvider] = None):
        self.provider = provider or BedrockProvider(model_id=CLAUDE_HAIKU)
        log.info(f"SLMClient initialised  provider={self.provider.model_name}")

    # ── Called by node_slm_validate() ────────────────────────────────────────

    def validate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate brief elements and return structured tags.

        Args:
            context: From BriefManager.get_slm_context()
                {
                  "chat_id":   str,
                  "task":      "validate_and_tag",
                  "elements":  [...],
                  "raw_input": str,
                }

        Returns:
            {"tags": [...], "is_valid": bool, "feedback": str}
        """
        log.info(f"SLMClient.validate  chat_id={context.get('chat_id')}  elements={len(context.get('elements', []))}")

        prompt = self._build_prompt(context)
        raw    = self.provider.generate(prompt, options={"system": SYSTEM_PROMPT, "max_tokens": 1024})
        result = self._parse_response(raw)

        log.info(f"SLMClient.validate  tags={len(result.get('tags', []))}  valid={result.get('is_valid')}")
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        elements_json = json.dumps(context.get("elements", []), indent=2)
        return (
            f"Brief ID: {context.get('chat_id')}\n\n"
            f"Brief elements:\n{elements_json}\n\n"
            f"Original input:\n{context.get('raw_input', '')}\n\n"
            "Validate and extract tags."
        )

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("SLMClient: response is not valid JSON — returning fallback")
            return {"tags": [], "is_valid": False, "feedback": f"Parse error. Raw: {raw[:200]}"}