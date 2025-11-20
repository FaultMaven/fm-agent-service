"""Multi-Provider LLM with Fallback Chain.

Implements intelligent fallback logic:
1. Try OpenAI (primary - fast, reliable)
2. Fallback to Anthropic (secondary - high quality)
3. Fallback to Fireworks (tertiary - open source, cheap)

Environment variables:
- OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL
- ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_BASE_URL
- FIREWORKS_API_KEY, FIREWORKS_MODEL, FIREWORKS_BASE_URL
"""

import logging
import os
from typing import Optional

from .base import ProviderConfig
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .fireworks_provider import FireworksProvider

logger = logging.getLogger(__name__)


class MultiProviderLLM:
    """Multi-provider LLM with automatic fallback chain.

    Tries providers in order until one succeeds:
    1. OpenAI (if configured)
    2. Anthropic (if configured)
    3. Fireworks (if configured)

    Falls back gracefully if earlier providers fail.
    """

    def __init__(self):
        """Initialize all available providers based on environment."""
        self.providers = []
        self.provider_names = []

        # Try to initialize OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            openai_config = ProviderConfig(
                name="openai",
                api_key=openai_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                models=[
                    os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "gpt-4o",
                    "gpt-4-turbo",
                    "gpt-3.5-turbo"
                ],
                default_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                timeout=60,
                confidence_score=0.9,
            )
            openai_provider = OpenAIProvider(openai_config)
            if openai_provider.is_available():
                self.providers.append(openai_provider)
                self.provider_names.append("openai")
                logger.info("✅ OpenAI provider initialized")

        # Try to initialize Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            anthropic_config = ProviderConfig(
                name="anthropic",
                api_key=anthropic_key,
                base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
                models=[
                    os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307"
                ],
                default_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                timeout=60,
                confidence_score=0.95,
            )
            anthropic_provider = AnthropicProvider(anthropic_config)
            if anthropic_provider.is_available():
                self.providers.append(anthropic_provider)
                self.provider_names.append("anthropic")
                logger.info("✅ Anthropic provider initialized")

        # Try to initialize Fireworks
        fireworks_key = os.getenv("FIREWORKS_API_KEY")
        if fireworks_key:
            fireworks_config = ProviderConfig(
                name="fireworks",
                api_key=fireworks_key,
                base_url=os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
                models=[
                    os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-70b-instruct"),
                    "accounts/fireworks/models/llama-v3p1-405b-instruct",
                    "accounts/fireworks/models/mixtral-8x22b-instruct"
                ],
                default_model=os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-70b-instruct"),
                timeout=60,
                confidence_score=0.85,
            )
            fireworks_provider = FireworksProvider(fireworks_config)
            if fireworks_provider.is_available():
                self.providers.append(fireworks_provider)
                self.provider_names.append("fireworks")
                logger.info("✅ Fireworks provider initialized")

        if not self.providers:
            logger.warning(
                "⚠️ No LLM providers configured! Set at least one of: "
                "OPENAI_API_KEY, ANTHROPIC_API_KEY, or FIREWORKS_API_KEY"
            )
        else:
            logger.info(
                f"🎯 MultiProviderLLM initialized with {len(self.providers)} provider(s): "
                f"{', '.join(self.provider_names)}"
            )

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate text using fallback chain.

        Tries each provider in order until one succeeds.

        Args:
            prompt: The prompt to send to the LLM
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            model: Optional model override
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text content as string

        Raises:
            RuntimeError: If all providers fail or none configured
        """
        if not self.providers:
            raise RuntimeError(
                "No LLM providers available. Configure at least one provider "
                "by setting OPENAI_API_KEY, ANTHROPIC_API_KEY, or FIREWORKS_API_KEY"
            )

        last_error = None

        for i, provider in enumerate(self.providers):
            provider_name = self.provider_names[i]

            try:
                logger.info(f"🔄 Trying provider {i + 1}/{len(self.providers)}: {provider_name}")

                response = await provider.generate(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )

                logger.info(
                    f"✅ Success with {provider_name}: {response.model}, "
                    f"{response.tokens_used} tokens, {response.response_time_ms}ms, "
                    f"confidence={response.confidence:.2f}"
                )

                return response.content

            except Exception as e:
                last_error = e
                logger.warning(
                    f"❌ {provider_name} failed: {type(e).__name__}: {str(e)}"
                )

                # If this isn't the last provider, try the next one
                if i < len(self.providers) - 1:
                    logger.info(f"⏭️  Falling back to next provider...")
                    continue
                else:
                    # This was the last provider
                    logger.error(f"💥 All {len(self.providers)} provider(s) failed")

        # All providers failed
        raise RuntimeError(
            f"All LLM providers failed. Last error: {type(last_error).__name__}: {str(last_error)}"
        )

    def get_status(self) -> dict:
        """Get status of all configured providers.

        Returns:
            Dictionary with provider availability and configuration
        """
        return {
            "providers_configured": len(self.providers),
            "providers": [
                {
                    "name": name,
                    "available": True,
                    "models": provider.get_supported_models(),
                    "default_model": provider.config.default_model
                }
                for name, provider in zip(self.provider_names, self.providers)
            ],
            "fallback_chain": " → ".join(self.provider_names) if self.provider_names else "None"
        }
