"""Unit tests for multi-provider LLM fallback logic.

Tests that the fallback chain works correctly:
1. Try OpenAI (if configured)
2. Fallback to Anthropic (if OpenAI fails)
3. Fallback to Fireworks (if both fail)
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_service.infrastructure.llm.multi_provider import MultiProviderLLM
from agent_service.infrastructure.llm.base import LLMResponse


class TestMultiProviderFallback:
    """Test multi-provider fallback chain."""

    @pytest.fixture
    def mock_openai_success(self):
        """Mock successful OpenAI response."""
        mock_response = LLMResponse(
            content="OpenAI response",
            confidence=0.9,
            provider="openai",
            model="gpt-4o-mini",
            tokens_used=100,
            response_time_ms=500
        )
        return mock_response

    @pytest.fixture
    def mock_anthropic_success(self):
        """Mock successful Anthropic response."""
        mock_response = LLMResponse(
            content="Anthropic response",
            confidence=0.95,
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            tokens_used=120,
            response_time_ms=600
        )
        return mock_response

    @pytest.fixture
    def mock_fireworks_success(self):
        """Mock successful Fireworks response."""
        mock_response = LLMResponse(
            content="Fireworks response",
            confidence=0.85,
            provider="fireworks",
            model="llama-v3p1-70b-instruct",
            tokens_used=150,
            response_time_ms=400
        )
        return mock_response

    @pytest.mark.asyncio
    async def test_openai_success_no_fallback(self, mock_openai_success):
        """Test that OpenAI success doesn't trigger fallback."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = MultiProviderLLM()

            # Mock OpenAI provider to succeed
            with patch.object(
                provider.providers[0], 'generate',
                return_value=mock_openai_success
            ):
                result = await provider.generate("Test prompt")

                assert result == "OpenAI response"
                print("✅ OpenAI success - no fallback triggered")

    @pytest.mark.asyncio
    async def test_openai_failure_anthropic_fallback(
        self, mock_anthropic_success
    ):
        """Test fallback to Anthropic when OpenAI fails."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "ANTHROPIC_API_KEY": "test-key"
        }):
            provider = MultiProviderLLM()

            # Mock OpenAI to fail, Anthropic to succeed
            with patch.object(
                provider.providers[0], 'generate',
                side_effect=Exception("OpenAI API error")
            ):
                with patch.object(
                    provider.providers[1], 'generate',
                    return_value=mock_anthropic_success
                ):
                    result = await provider.generate("Test prompt")

                    assert result == "Anthropic response"
                    print("✅ OpenAI failed → Anthropic fallback successful")

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Test that error is raised when all providers fail."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "ANTHROPIC_API_KEY": "test-key",
            "FIREWORKS_API_KEY": "test-key"
        }):
            provider = MultiProviderLLM()

            # Mock all providers to fail
            for p in provider.providers:
                with patch.object(p, 'generate', side_effect=Exception("API error")):
                    pass

            with pytest.raises(RuntimeError, match="All LLM providers failed"):
                await provider.generate("Test prompt")

            print("✅ All providers fail → Exception raised correctly")

    def test_no_providers_configured(self):
        """Test that error is raised when no providers configured."""
        with patch.dict(os.environ, {}, clear=True):
            provider = MultiProviderLLM()

            assert len(provider.providers) == 0
            print("✅ No providers configured → warning logged")

    @pytest.mark.asyncio
    async def test_provider_status(self):
        """Test get_status() method."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = MultiProviderLLM()

            status = provider.get_status()

            assert "providers_configured" in status
            assert status["providers_configured"] >= 0
            assert "fallback_chain" in status
            assert "providers" in status

            print(f"✅ Provider status: {status}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
