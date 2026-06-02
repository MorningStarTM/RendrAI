# services/providers/bedrock_image_provider.py
"""
AWS Bedrock image generation provider for Stable Diffusion XL.
Implements ImageProvider interface so ImageClient can use it directly.
"""

from __future__ import annotations

import base64
import json
import logging
import random
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from backend.logger import logger
from backend.services.providers.image_provider import ImageProvider


STABLE_DIFFUSION_XL = "stability.stable-diffusion-xl-v1"


class BedrockImageProvider(ImageProvider):
    """
    Bedrock-hosted Stable Diffusion XL image provider.

    Args:
        model_id:      Bedrock model ID (default: SDXL v1).
        region:        AWS region.
        style_preset:  SD style preset string.
        cfg_scale:     Classifier-free guidance scale.
        steps:         Diffusion steps.

    Usage:
        provider = BedrockImageProvider()
        result   = provider.generate_image("a red apple on a table")
        # result["image_data"] → raw PNG bytes
    """

    def __init__(
        self,
        model_id:     str = "amazon.nova-canvas-v1:0",
        region:       str = "us-east-1",
        cfg_scale:    int = 8,
        steps:        int = 30,
    ):
        super().__init__(model_name=model_id)
        self.model_id     = model_id
        self.cfg_scale    = cfg_scale
        self.steps        = steps

        self._client = boto3.client(
            service_name="bedrock-runtime",
            region_name=region,
        )
        logger.info(f"BedrockImageProvider initialised  model={model_id}  region={region}")

    # ── ImageProvider interface ───────────────────────────────────────────────

    def generate_image(
        self,
        prompt:  str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate an image and return raw bytes.

        Args:
            prompt:  Positive prompt string.
            options: Optional overrides — keys: negative_prompt, seed,
                     style_preset, cfg_scale, steps.

        Returns:
            {
              "image_data": bytes,   # raw PNG bytes — written to disk by node_image_gen_local
              "image_url":  str,     # always "" (no S3 in dev)
              "format":     "png",
            }
        """
        opts = options or {}

        negative = opts.get("negative_prompt", "").strip()

        native_request = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
                **({"negativeText": negative} if negative else {}),
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "width":          1024,
                "height":         1024,
                "cfgScale":       opts.get("cfg_scale", self.cfg_scale),
                "seed":           opts.get("seed", random.randint(0, 858993460)),
                "quality":        "standard",
            },
        }


        logger.info(
            f"BedrockImageProvider.generate_image  "
            f"prompt_len={len(prompt)}"
        )

        try:
            response = self._client.invoke_model(
                modelId     = self.model_id,
                body        = json.dumps(native_request),
                contentType = "application/json",
                accept      = "application/json",
            )

            body     = json.loads(response["body"].read())
            b64_data = body["images"][0]          # ← Nova Canvas key (not "artifacts")
            image_bytes = base64.b64decode(b64_data)

            logger.info(f"BedrockImageProvider  bytes={len(image_bytes)}")

            return {
                "image_data": image_bytes,
                "image_url":  "",
                "format":     "png",
            }

        except (BotoCoreError, ClientError) as exc:
            logger.error(f"BedrockImageProvider.generate_image failed: {exc}")
            raise



    def health_check(self) -> bool:
        """Ping Bedrock with a minimal 1-step generation."""
        try:
            self._client.invoke_model(
                modelId     = self.model_id,
                body        = json.dumps({
                    "text_prompts": [{"text": "test", "weight": 1.0}],
                    "seed":  0,
                    "steps": 1,       # minimum steps — fast, cheap
                }),
                contentType = "application/json",
                accept      = "application/json",
            )
            return True
        except Exception as exc:
            logger.warning(f"BedrockImageProvider health_check failed: {exc}")
            return False