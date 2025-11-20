"""Anthropic provider implementation.

Copied from monolith: faultmaven/infrastructure/llm/providers/anthropic.py
Implements Claude API integration for high-quality reasoning tasks.
"""

import json
import time
from typing import List, Optional

import aiohttp

from .base import BaseLLMProvider, LLMResponse, ProviderConfig


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider implementation"""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        """Check if Anthropic provider is properly configured"""
        return bool(
            self.config.api_key and
            self.config.base_url and
            self.config.models
        )

    def get_supported_models(self) -> List[str]:
        """Get list of supported Claude models"""
        return self.config.models.copy()

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """Generate text using Anthropic Claude API"""
        start_time = time.time()

        # Use specified model or default
        selected_model = model or self.config.default_model
        if not selected_model:
            selected_model = "claude-3-5-sonnet-20241022"

        # Prepare headers for Anthropic API
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01"
        }

        # Prepare request body for Anthropic API format
        request_body = {
            "model": selected_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        # Add any additional parameters
        if "system" in kwargs:
            request_body["system"] = kwargs["system"]

        if "stop_sequences" in kwargs:
            request_body["stop_sequences"] = kwargs["stop_sequences"]

        # Make API request
        url = f"{self.config.base_url.rstrip('/')}/messages"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:

                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Anthropic API request failed: {response.status} - {error_text}"
                    )

                response_data = await response.json()

        # Extract content from Anthropic response format
        content = ""
        if "content" in response_data and response_data["content"]:
            # Anthropic returns content as a list of blocks
            for block in response_data["content"]:
                if block.get("type") == "text":
                    content += block.get("text", "")

        # Calculate metrics
        response_time_ms = int((time.time() - start_time) * 1000)
        tokens_used = response_data.get("usage", {}).get("output_tokens", 0)

        # Calculate confidence based on model and response quality
        confidence = self._calculate_confidence(selected_model, content, response_data)

        return LLMResponse(
            content=content,
            confidence=confidence,
            provider=self.provider_name,
            model=selected_model,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
            cached=False
        )

    def _calculate_confidence(self, model: str, content: str, response_data: dict) -> float:
        """Calculate confidence score for Anthropic response"""
        base_confidence = self.config.confidence_score

        # Anthropic models have different confidence characteristics
        model_confidence_map = {
            "claude-3-5-sonnet": 0.95,
            "claude-3-opus": 0.95,
            "claude-3-sonnet": 0.90,
            "claude-3-haiku": 0.85,
        }

        # Find matching model confidence
        model_confidence = base_confidence
        for model_name, confidence in model_confidence_map.items():
            if model_name in model.lower():
                model_confidence = confidence
                break

        # Adjust based on content quality
        content_length = len(content.strip())

        if content_length == 0:
            return 0.0
        elif content_length < 50:
            model_confidence *= 0.8
        elif content_length > 500:
            model_confidence *= 1.05

        # Check for refusal or inability to answer
        refusal_indicators = [
            "i cannot", "i can't", "i'm not able", "i don't have",
            "i'm sorry", "i apologize", "i cannot provide"
        ]

        content_lower = content.lower()
        for indicator in refusal_indicators:
            if indicator in content_lower:
                model_confidence *= 0.6
                break

        # Ensure confidence is within valid range
        return min(1.0, max(0.0, model_confidence))
