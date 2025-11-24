"""Multi-Provider LLM with Fallback Chain and Task-Specific Routing.

Implements intelligent fallback logic across multiple LLM providers:
1. OpenAI (GPT-4, GPT-3.5)
2. Anthropic (Claude)
3. Groq (ultra-fast Llama/Mixtral)
4. Gemini (Google)
5. Fireworks (open source models)
6. OpenRouter (aggregated access)
7. Local LLM (Ollama, LM Studio, LocalAI, vLLM)

Environment variables:
- OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL
- ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_BASE_URL
- GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL
- GEMINI_API_KEY, GEMINI_MODEL, GEMINI_BASE_URL
  - FIREWORKS_API_KEY, FIREWORKS_MODEL, FIREWORKS_BASE_URL
  - OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL
  - LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL, LOCAL_LLM_BASE_URL
  
  Task-Specific Provider Routing (Optional):
- CHAT_PROVIDER, CHAT_MODEL - Main diagnostic conversations
- MULTIMODAL_PROVIDER, MULTIMODAL_MODEL - Visual evidence processing
- SYNTHESIS_PROVIDER, SYNTHESIS_MODEL - Knowledge base RAG queries
- STRICT_PROVIDER_MODE - Disable fallback (fail if specified provider unavailable)
"""

import logging
import os
from typing import Optional, List, Type

from .base import ProviderConfig
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .fireworks_provider import FireworksProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider

# Import observability components
from agent_service.infrastructure.logging import get_logger
from agent_service.infrastructure.observability import get_tracer

logger = get_logger(__name__)


class MultiProviderLLM:
    """Multi-provider LLM with automatic fallback chain.

    Tries providers in order until one succeeds.
    Providers are initialized based on available API keys.
    """

    def __init__(self):
        """Initialize all available providers based on environment."""
        self.providers = []
        self.provider_names = []
        self.provider_map = {}  # Map provider name to provider instance

        # Task-specific routing configuration
        self.strict_mode = os.getenv("STRICT_PROVIDER_MODE", "false").lower() == "true"
        self.task_config = {
            "chat": {
                "provider": os.getenv("CHAT_PROVIDER", "auto"),
                "model": os.getenv("CHAT_MODEL")
            },
            "multimodal": {
                "provider": os.getenv("MULTIMODAL_PROVIDER", "auto"),
                "model": os.getenv("MULTIMODAL_MODEL")
            },
            "synthesis": {
                "provider": os.getenv("SYNTHESIS_PROVIDER", "auto"),
                "model": os.getenv("SYNTHESIS_MODEL")
            }
        }

        # Initialize providers using helper
        self._try_init_provider(
            name="openai",
            provider_class=OpenAIProvider,
            env_prefix="OPENAI",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            models=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            confidence=0.9
        )

        self._try_init_provider(
            name="anthropic",
            provider_class=AnthropicProvider,
            env_prefix="ANTHROPIC",
            default_base_url="https://api.anthropic.com/v1",
            default_model="claude-3-5-sonnet-20241022",
            models=[
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307"
            ],
            confidence=0.95
        )

        self._try_init_provider(
            name="fireworks",
            provider_class=FireworksProvider,
            env_prefix="FIREWORKS",
            default_base_url="https://api.fireworks.ai/inference/v1",
            default_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
            models=[
                "accounts/fireworks/models/llama-v3p1-70b-instruct",
                "accounts/fireworks/models/llama-v3p1-405b-instruct",
                "accounts/fireworks/models/mixtral-8x22b-instruct"
            ],
            confidence=0.85
        )

        self._try_init_provider(
            name="groq",
            provider_class=GroqProvider,
            env_prefix="GROQ",
            default_base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
            models=[
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768"
            ],
            confidence=0.88
        )

        self._try_init_provider(
            name="gemini",
            provider_class=GeminiProvider,
            env_prefix="GEMINI",
            default_base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-1.5-pro",
            models=["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
            confidence=0.82
        )

        self._try_init_provider(
            name="openrouter",
            provider_class=OpenAIProvider,  # OpenRouter uses OpenAI-compatible API
            env_prefix="OPENROUTER",
            default_base_url="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-3.5-sonnet",
            models=[
                "anthropic/claude-3.5-sonnet",
                "openai/gpt-4-turbo",
                "google/gemini-pro"
            ],
            confidence=0.85
        )

        self._try_init_provider(
            name="local",
            provider_class=OpenAIProvider,  # Local LLMs use OpenAI-compatible API
            env_prefix="LOCAL_LLM",
            default_base_url="http://localhost:11434/v1",
            default_model="llama2",
            models=[
                "llama2",
                "llama3",
                "llama3.1",
                "mistral",
                "mixtral",
                "codellama",
                "phi",
                "gemma"
            ],
            confidence=0.75
        )

        if not self.providers:
            logger.warning(
                "⚠️ No LLM providers configured! Set at least one API key: "
                "OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, "
                "FIREWORKS_API_KEY, OPENROUTER_API_KEY, or LOCAL_LLM_API_KEY"
            )
        else:
            logger.info(
                f"🎯 MultiProviderLLM initialized with {len(self.providers)} provider(s): "
                f"{', '.join(self.provider_names)}"
            )

            # Log task-specific routing configuration
            task_routing_active = any(
                cfg["provider"] != "auto" for cfg in self.task_config.values()
            )
            if task_routing_active:
                logger.info("📍 Task-specific provider routing enabled:")
                for task_type, cfg in self.task_config.items():
                    if cfg["provider"] != "auto":
                        model_info = f" (model: {cfg['model']})" if cfg['model'] else ""
                        logger.info(f"  • {task_type}: {cfg['provider']}{model_info}")
                if self.strict_mode:
                    logger.info("  ⚠️  STRICT MODE: Fallback disabled")
            else:
                logger.info("🔄 Using automatic fallback chain for all tasks")

    def _try_init_provider(
        self,
        name: str,
        provider_class: Type,
        env_prefix: str,
        default_base_url: str,
        default_model: str,
        models: List[str],
        confidence: float
    ):
        """Helper to reduce provider initialization boilerplate."""
        api_key = os.getenv(f"{env_prefix}_API_KEY")
        if not api_key:
            return

        try:
            # Check for model override from environment, otherwise use default
            env_model = os.getenv(f"{env_prefix}_MODEL")
            if env_model:
                default_model = env_model
                
            config = ProviderConfig(
                name=name,
                api_key=api_key,
                base_url=os.getenv(f"{env_prefix}_BASE_URL", default_base_url),
                models=models,
                default_model=default_model,
                timeout=60,
                confidence_score=confidence,
            )

            provider = provider_class(config)
            if provider.is_available():
                self.providers.append(provider)
                self.provider_names.append(name)
                self.provider_map[name] = provider
                logger.info(f"✅ {name.capitalize()} provider initialized (model: {default_model})")
        
        except Exception as e:
            logger.warning(f"Failed to initialize {name} provider: {e}")

    def _resolve_task_provider(self, task_type: str) -> tuple[Optional[object], Optional[str]]:
        """Resolve which provider and model to use for a specific task type.

        Args:
            task_type: Type of task ("chat", "multimodal", "synthesis")

        Returns:
            Tuple of (provider_instance, model_override) or (None, None) for auto fallback
        """
        if task_type not in self.task_config:
            return None, None

        cfg = self.task_config[task_type]
        provider_name = cfg["provider"]
        model_override = cfg["model"]

        # "auto" means use fallback chain
        if provider_name == "auto":
            return None, model_override

        # Get the specific provider
        provider = self.provider_map.get(provider_name)

        if provider is None:
            if self.strict_mode:
                raise RuntimeError(
                    f"STRICT MODE: {task_type} task requires provider '{provider_name}' "
                    f"but it is not configured. Set {provider_name.upper()}_API_KEY."
                )
            else:
                logger.warning(
                    f"⚠️  {task_type} task configured for '{provider_name}' but provider "
                    f"not available. Falling back to auto."
                )
                return None, model_override

        return provider, model_override

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
        task_type: str = "chat",
        **kwargs
    ) -> str:
        """Generate text using task-specific routing or fallback chain.

        If task-specific provider is configured, uses that provider.
        Otherwise, tries providers in order until one succeeds.

        Args:
            prompt: The prompt to send to the LLM
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            model: Optional model override
            task_type: Type of task ("chat", "multimodal", "synthesis")
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text content as string

        Raises:
            RuntimeError: If all providers fail, none configured, or strict mode violation
        """
        if not self.providers:
            raise RuntimeError(
                "No LLM providers available. Configure at least one provider "
                "by setting OPENAI_API_KEY, ANTHROPIC_API_KEY, or FIREWORKS_API_KEY"
            )

        # Check for task-specific provider configuration
        task_provider, task_model = self._resolve_task_provider(task_type)

        # If task-specific model is set, use it (unless explicit model override provided)
        if task_model and not model:
            model = task_model

        # If task-specific provider is set, try it first
        if task_provider:
            provider_name = next(
                name for name, p in self.provider_map.items() if p == task_provider
            )
            logger.info(
                f"🎯 Using task-specific provider for '{task_type}': {provider_name}"
                + (f" (model: {model})" if model else "")
            )

            try:
                # Add tracing for LLM generation
                tracer = get_tracer()
                with tracer.trace("llm_generate", provider=provider_name, model=model, task=task_type) as span:
                    response = await task_provider.generate(
                        prompt=prompt,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )
                    
                    if span:
                        span.log({
                            "tokens": response.tokens_used,
                            "latency_ms": response.response_time_ms,
                            "confidence": response.confidence
                        })

                logger.info(
                    f"✅ Success with {provider_name}: {response.model}, "
                    f"{response.tokens_used} tokens, {response.response_time_ms}ms, "
                    f"confidence={response.confidence:.2f}"
                )

                return response.content

            except Exception as e:
                if self.strict_mode:
                    # In strict mode, fail immediately without fallback
                    raise RuntimeError(
                        f"STRICT MODE: {task_type} task failed with provider '{provider_name}': "
                        f"{type(e).__name__}: {str(e)}"
                    )
                else:
                    # In non-strict mode, log warning and fall back to auto chain
                    logger.warning(
                        f"❌ Task-specific provider '{provider_name}' failed: "
                        f"{type(e).__name__}: {str(e)}"
                    )
                    logger.info("⏭️  Falling back to automatic provider chain...")

        # Use automatic fallback chain
        last_error = None

        for i, provider in enumerate(self.providers):
            provider_name = self.provider_names[i]

            try:
                logger.info(f"🔄 Trying provider {i + 1}/{len(self.providers)}: {provider_name}")

                # Add tracing for LLM generation (fallback chain)
                tracer = get_tracer()
                with tracer.trace("llm_generate", provider=provider_name, model=model, task=task_type, fallback_attempt=i+1) as span:
                    response = await provider.generate(
                        prompt=prompt,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )
                    
                    if span:
                        span.log({
                            "tokens": response.tokens_used,
                            "latency_ms": response.response_time_ms,
                            "confidence": response.confidence
                        })

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
        """Get status of all configured providers and task-specific routing.

        Returns:
            Dictionary with provider availability and configuration
        """
        status = {
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
            "fallback_chain": " → ".join(self.provider_names) if self.provider_names else "None",
            "strict_mode": self.strict_mode
        }

        # Add task-specific routing info
        task_routing = {}
        for task_type, cfg in self.task_config.items():
            if cfg["provider"] != "auto":
                task_routing[task_type] = {
                    "provider": cfg["provider"],
                    "model": cfg["model"],
                    "available": cfg["provider"] in self.provider_map
                }

        if task_routing:
            status["task_routing"] = task_routing

        return status
