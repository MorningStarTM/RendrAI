"""
src/core/image_provider.py
==========================
Abstract base for all image generation providers.
Concrete implementations: NanoBananaProvider, DallEProvider, StabilityProvider, etc.

Kept separate from ModelProvider because image generation has a
fundamentally different interface — it returns bytes/URLs, not text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional
from backend.logger import logger

log = logging.getLogger("ImageProvider")
    

class ImageProvider(ABC):
    """
    Abstract base class for all image generation providers.
    """

    def __init__(self, model_name: str = ""):
        self.model_name = model_name

    # ── Core abstract API ──────────────────────────────────────────────────────

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate an image from a prompt.

        Returns:
            {
              "image_data": bytes,   # raw image bytes
              "image_url":  str,     # URL if provider hosts it directly
              "format":     str,     # "png" | "jpeg" | "webp"
              "metadata":   dict,    # provider-specific info
            }
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the image provider is available."""
        pass

    # ── Batch helper ──────────────────────────────────────────────────────────

    def generate_batch(
        self,
        prompts: list[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> list[Dict[str, Any]]:
        """
        Generate images for multiple prompts.
        Default: sequential calls. Override for native batch APIs.
        """
        logger.info(f"Generating {len(prompts)} images via sequential calls")
        return [self.generate_image(p, options) for p in prompts]