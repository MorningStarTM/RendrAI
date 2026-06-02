"""
src/providers/bedrock_provider.py
=================================
AWS Bedrock concrete implementation of ModelProvider.
Supports any Bedrock-hosted model — currently used for:
  - Claude Haiku  (SLM / validator)
  - Claude Sonnet (Reasoning model)

Switching to a different Bedrock model = change the model_id string.
Switching away from Bedrock entirely = swap this class for another provider.
"""

from __future__ import annotations

from asyncio.log import logger
import json
import logging
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from backend.logger import logger
from backend.services.providers.model_provider import ModelProvider
log = logging.getLogger("BedrockProvider")

# Model ID constants — change here to switch Bedrock model versions
CLAUDE_HAIKU  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
CLAUDE_SONNET = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
STABLE_DIFFUSION = "stability.stable-diffusion-xl-v1"

class BedrockProvider(ModelProvider):
    """
    AWS Bedrock text generation provider.

    Args:
        model_id:   Bedrock model ID string.
        region:     AWS region (default: us-east-1).
        max_tokens: Max tokens in the response.
        temperature: Sampling temperature.

    Usage:
        provider = BedrockProvider(model_id=CLAUDE_HAIKU)
        response = provider.generate("Validate this brief: ...")
    """

    def __init__(
        self,
        model_id:    str   = CLAUDE_HAIKU,
        region:      str   = "us-east-1",
        max_tokens:  int   = 1024,
        temperature: float = 0.3,
    ):
        super().__init__(model_name=model_id)
        self.model_id    = model_id
        self.max_tokens  = max_tokens
        self.temperature = temperature

        self._client = boto3.client(
            service_name="bedrock-runtime",
            region_name=region,
        )
        logger.info(f"BedrockProvider initialised  model={model_id}  region={region}")

    # ── ModelProvider interface ───────────────────────────────────────────────

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """
        Send a prompt to Bedrock and return the text response.

        Args:
            prompt:  The full prompt string.
            options: Override defaults — keys: max_tokens, temperature, system.
        """
        opts        = options or {}
        max_tokens  = opts.get("max_tokens",  self.max_tokens)
        temperature = opts.get("temperature", self.temperature)
        system      = opts.get("system",      "")

        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        max_tokens,
            "temperature":       temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        try:
            response = self._client.invoke_model(
                modelId     = self.model_id,
                body        = json.dumps(body),
                contentType = "application/json",
                accept      = "application/json",
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]

        except (BotoCoreError, ClientError) as exc:
            logger.error(f"BedrockProvider.generate failed: {exc}")
            raise

    def health_check(self) -> bool:
        """Ping Bedrock with a minimal prompt."""
        try:
            self.generate("ping", options={"max_tokens": 5})
            return True
        except Exception as exc:
            logger.warning(f"BedrockProvider health_check failed: {exc}")
            return False