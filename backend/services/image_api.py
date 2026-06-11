"""
services/image_api.py
=====================
Image generation client — generates one image per prompt.
Called by node_image_gen() in agent.py.

Default provider : Google Imagen (Nano Banana)
Swap provider    : pass any ImageProvider instance to __init__
"""

from __future__ import annotations

from asyncio.log import logger
import logging
from typing import Any, Dict, Optional

from backend.services.providers.image_provider import ImageProvider
from backend.services.providers.nano_banana_provider import NanoBananaProvider
from backend.logger import logger    

class ImageClient:
    """
    Generates an image from a single prompt string.

    Args:
        provider: Any ImageProvider instance.
                  Default: NanoBananaProvider (Google Imagen).
                  Swap to StabilityProvider, DallEProvider, or FluxProvider
                  with zero changes to agent.py.

    Usage in agent.py:
        result = image_client.generate(prompt, metadata)
        # {"image_url": str, "s3_key": str}

    Swap provider example:
        from src.providers.stability_provider import StabilityProvider
        image_client = ImageClient(provider=StabilityProvider())
    """

    def __init__(self, provider: Optional[ImageProvider] = None):
        self.provider = provider or NanoBananaProvider()
        logger.info(f"ImageClient initialised  provider={self.provider.model_name}")

    # ── Called by node_image_gen() ────────────────────────────────────────────

    def generate(
        self,
        prompt:      str,
        metadata:    Optional[Dict[str, Any]] = None,
        input_image: Optional[bytes] = None,          # ← add this
    ) -> Dict[str, Any]:
        meta = metadata or {}
        logger.info(
            f"ImageClient.generate  chat_id={meta.get('chat_id')}  "
            f"index={meta.get('prompt_index')}  prompt_len={len(prompt)}"
        )

        positive, _, negative = prompt.partition("| negative:")
        positive = positive.strip()
        negative = negative.strip()

        options = {"negative_prompt": negative} if negative else {}
        result  = self.provider.generate_image(positive, options=options, input_image=input_image)  # ← pass it

        logger.info(f"ImageClient.generate  format={result.get('format')}  data_bytes={len(result.get('image_data', b''))}")

        return {
            "image_data": result.get("image_data", b""),
            "image_url":  result.get("image_url",  ""),
            "s3_key":     "",
            "format":     result.get("format", "png"),
        }