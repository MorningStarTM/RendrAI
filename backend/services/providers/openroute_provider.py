"""
src/providers/openrouter_provider.py
=====================================
OpenRouter concrete implementation of ModelProvider.

Drop-in replacement for BedrockProvider — same interface, different backend.
To switch SLMClient or ReasoningClient from Bedrock to OpenRouter:

    # In slm_validator.py, change:
    provider = BedrockProvider(model_id=CLAUDE_HAIKU)
    # to:
    provider = OpenRouterProvider(model_id="anthropic/claude-haiku-3")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

from backend.services.providers.model_provider import ModelProvider


log = logging.getLogger("openrouter_provider")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(ModelProvider):
    """
    OpenRouter text generation provider.

    Args:
        model_id:    OpenRouter model string e.g. "anthropic/claude-haiku-3"
        api_key:     OpenRouter API key (default: OPENROUTER_API_KEY env var)
        max_tokens:  Max tokens in response.
        temperature: Sampling temperature.

    Usage:
        provider = OpenRouterProvider(model_id="anthropic/claude-haiku-3")
        response = provider.generate("Validate this brief: ...")
    """

    def __init__(
        self,
        model_id:    str   = "anthropic/claude-haiku-3",
        api_key:     Optional[str] = None,
        max_tokens:  int   = 1024,
        temperature: float = 0.3,
    ):
        super().__init__(model_name=model_id)
        self.model_id    = model_id
        self.max_tokens  = max_tokens
        self.temperature = temperature
        self.api_key     = api_key or os.environ["OPENROUTER_API_KEY"]
        log.info(f"OpenRouterProvider initialised  model={model_id}")

    # ── ModelProvider interface ───────────────────────────────────────────────

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        opts        = options or {}
        max_tokens  = opts.get("max_tokens",  self.max_tokens)
        temperature = opts.get("temperature", self.temperature)
        system      = opts.get("system",      "")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model":       self.model_id,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }

        try:
            resp = requests.post(
                OPENROUTER_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except requests.RequestException as exc:
            log.error(f"OpenRouterProvider.generate failed: {exc}")
            raise

    def health_check(self) -> bool:
        try:
            self.generate("ping", options={"max_tokens": 5})
            return True
        except Exception as exc:
            log.warning(f"OpenRouterProvider health_check failed: {exc}")
            return False