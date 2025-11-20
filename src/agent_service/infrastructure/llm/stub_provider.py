"""Stub LLM Provider for testing (temporary).

TODO: Replace with actual LLM provider implementation or import from monolith.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StubLLMProvider:
    """Stub LLM provider that returns placeholder responses.

    This is a temporary implementation to allow the agent service to start
    without the full monolith LLM infrastructure.

    TODO Phase 6: Implement real LLM provider with OpenAI/Anthropic/Fireworks routing.
    """

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Generate a stub response.

        Args:
            prompt: The prompt to send to the LLM
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            A placeholder response string
        """
        logger.warning("Using StubLLMProvider - responses are placeholders only")

        return """I understand you're troubleshooting an issue.

To help you effectively, I need to gather more information:

1. What specific problem are you experiencing?
2. When did this issue first occur?
3. Have there been any recent changes to the system?

Please provide these details so I can begin investigating.

[Note: This is a stub response from StubLLMProvider. Real LLM integration is TODO for Phase 6.]
"""
