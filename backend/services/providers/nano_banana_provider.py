"""
src/providers/nano_banana_provider.py
======================================
Google Nano Banana (Gemini native image generation) via the Gemini API.

Uses the official `google-genai` SDK — not Vertex AI.
All you need is a GEMINI_API_KEY. No GCP project or service account required.

Available models (from docs):
  NANO_BANANA_2   = "gemini-3.1-flash-image-preview"  ← fastest, high-volume
  NANO_BANANA_PRO = "gemini-3-pro-image-preview"       ← highest quality, thinking
  NANO_BANANA     = "gemini-2.5-flash-image"           ← speed + efficiency

Switching to a different image provider (Stability, DALL-E, Flux):
  → swap this class in ImageClient — zero changes to agent.py or BriefManager.

Install:
  pip install google-genai
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Literal, Optional
from venv import logger

from backend.logger import logger
from backend.services.providers.image_provider import ImageProvider



# ── Model constants ────────────────────────────────────────────────────────────
NANO_BANANA_2   = "gemini-3.1-flash-image-preview"   # fast, high-volume
NANO_BANANA_PRO = "gemini-3-pro-image-preview"        # professional, thinking
NANO_BANANA     = "gemini-2.5-flash-image"            # speed + efficiency

# Valid aspect ratios per docs
ASPECT_RATIOS = Literal[
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]

# Valid resolutions — NOTE: uppercase K required by API ("2k" will be rejected)
RESOLUTIONS = Literal["512", "1K", "2K", "4K"]


class NanoBananaProvider(ImageProvider):
    """
    Google Nano Banana image generation via the Gemini API.

    Args:
        model:          Gemini image model ID. Default: NANO_BANANA_2 (fastest).
        api_key:        Gemini API key. Default: reads GEMINI_API_KEY env var.
        aspect_ratio:   Output aspect ratio. Default: "1:1".
        image_size:     Output resolution. Default: "1K".
                        Use "512" for lowest latency, "4K" for highest quality.
                        Note: "512" only available on NANO_BANANA_2.
        thinking_level: "minimal" (default, lowest latency) | "high" (better quality).
                        Only applies to NANO_BANANA_2 and NANO_BANANA_PRO.

    Usage:
        provider = NanoBananaProvider()
        result   = provider.generate_image("A dragon in watercolor style")

    Swap to Pro model for best quality:
        provider = NanoBananaProvider(model=NANO_BANANA_PRO, image_size="2K")
    """

    def __init__(
        self,
        model:           str            = NANO_BANANA_2,
        api_key:         Optional[str]  = None,
        aspect_ratio:    str            = "1:1",
        image_size:      str            = "1K",
        thinking_level:  str            = "minimal",
    ):
        super().__init__(model_name=model)
        self.model          = model
        self.aspect_ratio   = aspect_ratio
        self.image_size     = image_size
        self.thinking_level = thinking_level
        self._api_key       = api_key or os.environ["GEMINI_API_KEY"]

        logger.info(
            f"NanoBananaProvider initialised  model={model}  "
            f"aspect_ratio={aspect_ratio}  image_size={image_size}"
        )

    # ── ImageProvider interface ───────────────────────────────────────────────

    def generate_image(
        self,
        prompt:  str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate an image via Nano Banana (Gemini API).

        Args:
            prompt:  Full prompt string.
                     Tip from docs: descriptive narrative > keyword list.
            options: Runtime overrides:
                       aspect_ratio    str  e.g. "16:9"
                       image_size      str  "512" | "1K" | "2K" | "4K"
                       thinking_level  str  "minimal" | "high"
                       negative_prompt str  folded into prompt naturally
                                           (Gemini has no hard negative field)

        Returns:
            {
              "image_data": bytes,   # raw PNG bytes
              "image_url":  str,     # empty — filled by StorageClient after S3 upload
              "format":     "png",
              "metadata": {
                "model":        str,
                "prompt":       str,
                "aspect_ratio": str,
                "image_size":   str,
              }
            }
        """
        from google import genai
        from google.genai import types

        opts            = options or {}
        aspect_ratio    = opts.get("aspect_ratio",    self.aspect_ratio)
        image_size      = opts.get("image_size",      self.image_size)
        thinking_level  = opts.get("thinking_level",  self.thinking_level)
        negative_prompt = opts.get("negative_prompt", "")

        # Gemini has no hard negative-prompt field — fold it in naturally
        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}. Avoid: {negative_prompt}."

        # response_format controls aspect ratio + resolution
        response_format = {
            "image": {
                "aspectRatio": aspect_ratio,
                "imageSize":   image_size,     # must be uppercase K e.g. "2K"
            }
        }

        config_kwargs: Dict[str, Any] = {
            "response_modalities": ["IMAGE"],  # image only — no text padding
            "response_format":     response_format,
        }

        # Thinking config — supported on Flash and Pro, not on gemini-2.5-flash-image
        if self.model in (NANO_BANANA_2, NANO_BANANA_PRO):
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=thinking_level,
                include_thoughts=False,   # skip interim thought images in response
            )

        logger.info(
            f"NanoBananaProvider.generate_image  model={self.model}  "
            f"aspect_ratio={aspect_ratio}  image_size={image_size}  "
            f"thinking={thinking_level}  prompt_len={len(full_prompt)}"
        )

        client = genai.Client(api_key=self._api_key)

        response = client.models.generate_content(
            model    = self.model,
            contents = [full_prompt],
            config   = types.GenerateContentConfig(**config_kwargs),
        )

        image_data = self._extract_image_bytes(response)

        logger.info(
            f"NanoBananaProvider: image generated  bytes={len(image_data)}"
        )

        return {
            "image_data": image_data,
            "image_url":  "",       # StorageClient fills this after S3 upload
            "format":     "png",
            "metadata": {
                "model":        self.model,
                "prompt":       full_prompt,
                "aspect_ratio": aspect_ratio,
                "image_size":   image_size,
            },
        }

    def generate_batch(
        self,
        prompts: List[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate images for multiple prompts sequentially.
        For very large batches (50+) consider using the Gemini Batch API instead.
        See: https://ai.google.dev/gemini-api/docs/batch-api
        """
        logger.info(f"NanoBananaProvider.generate_batch  count={len(prompts)}")
        return [self.generate_image(p, options) for p in prompts]

    def health_check(self) -> bool:
        """Quick check — generates the smallest possible image."""
        try:
            result = self.generate_image(
                "a small red circle",
                options={"image_size": "512", "aspect_ratio": "1:1"},
            )
            return bool(result.get("image_data"))
        except Exception as exc:
            logger.warning(f"NanoBananaProvider.health_check failed: {exc}")
            return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _extract_image_bytes(self, response) -> bytes:
        """
        Walk response parts and return the first non-thought image's raw bytes.

        The API may return thought images (interim reasoning steps) before the
        final image. Per the docs, thought parts have `part.thought == True`.
        We skip those and return only the final rendered image.
        """
        for part in response.parts:
            if getattr(part, "thought", False):
                # Reasoning/thought image — skip
                continue
            if part.inline_data is not None:
                return part.inline_data.data

        logger.error(
            "Nano Banana response contained no image data. "
            f"Parts received: {[type(p).__name__ for p in response.parts]}"
        )
        raise ValueError("No image data found in response.")