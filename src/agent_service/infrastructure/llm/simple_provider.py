"""Simple LLM Provider for FaultMaven Agent Service.

This is a minimal wrapper around OpenAI provider that implements the
ILLMProvider interface expected by MilestoneEngine.

For Phase 6.1: Basic OpenAI integration only.
TODO Phase 6.2: Add Anthropic and Fireworks fallback providers.
TODO Phase 6.3: Port full registry and router from monolith.
"""

import logging
import os
from typing import Optional

from .base import ProviderConfig
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class SimpleLLMProvider:
    """Simple LLM provider with OpenAI support.

    This implements the generate() method expected by MilestoneEngine.

    Environment variables required:
    - OPENAI_API_KEY: OpenAI API key
    - OPENAI_BASE_URL: OpenAI API base URL (default: https://api.openai.com/v1)
    - OPENAI_MODEL: Model to use (default: gpt-4o-mini)
    """

    def __init__(self):
        """Initialize provider with environment configuration."""
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not api_key:
            logger.warning(
                "OPENAI_API_KEY not set - LLM provider will fail. "
                "Set environment variable or use StubLLMProvider for testing."
            )

        # Create OpenAI provider config
        config = ProviderConfig(
            name="openai",
            api_key=api_key,
            base_url=base_url,
            models=[model, "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            default_model=model,
            timeout=60,
            confidence_score=0.9,
        )

        self.provider = OpenAIProvider(config)
        self.default_model = model

        if self.provider.is_available():
            logger.info(f"✅ SimpleLLMProvider initialized with OpenAI ({model})")
        else:
            logger.warning("⚠️ SimpleLLMProvider initialized but OpenAI not available (missing API key)")

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
        task_type: str = "chat",
        **kwargs
    ) -> str:
        """Generate text completion.

        This method signature matches what MilestoneEngine expects.

        Args:
            prompt: The prompt to send to the LLM
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            model: Optional model override
            task_type: Type of task (ignored by SimpleLLMProvider - only uses single provider)
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text content as string

        Raises:
            Exception: If OpenAI API call fails
        """
        if not self.provider.is_available():
            raise RuntimeError(
                "OpenAI provider not available. Set OPENAI_API_KEY environment variable."
            )

        # Call OpenAI provider
        response = await self.provider.generate(
            prompt=prompt,
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        logger.info(
            f"LLM Response: {response.provider}/{response.model}, "
            f"{response.tokens_used} tokens, {response.response_time_ms}ms"
        )

        return response.content
