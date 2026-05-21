"""
src/core/model_provider.py
==========================
Abstract base for all text model providers.
Concrete implementations: BedrockProvider, OpenRouteProvider, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("ModelProvider")
    

class ModelProvider(ABC):
    """
    Abstract base class defining the interface for all model providers.
    """

    def __init__(self, model_name: str = ""):
        self.model_name = model_name

    # ── Core abstract API ──────────────────────────────────────────────────────

    @abstractmethod
    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Generate text from a prompt."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the model provider is available."""
        pass

    # ── Convenience / compatibility layer ─────────────────────────────────────

    def predict(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Alias for generate() — backwards compatibility."""
        return self.generate(prompt, options)

    # ── Batch helpers ─────────────────────────────────────────────────────────

    def generate_batch(
        self,
        prompt: str,
        num_samples: int,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Generate multiple samples from the same prompt.
        Default: sequential calls. Override for native batch APIs.
        """
        log.info(f"Generating {num_samples} samples via sequential calls")
        results = []
        for i in range(num_samples):
            log.info(f"Generating sample {i + 1}/{num_samples}")
            results.append(self.generate(prompt, options))
        return results

    def supports_batch_generation(self) -> bool:
        """Return True if provider supports efficient native batch generation."""
        return False