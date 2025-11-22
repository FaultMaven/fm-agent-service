"""Google Gemini provider implementation.

Google Gemini API with multi-modal capabilities.
"""

import aiohttp
from typing import List, Optional, Dict, Any

from .base import BaseLLMProvider, LLMResponse, ProviderConfig


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider implementation"""

    @property
    def provider_name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        """Check if Gemini provider is properly configured"""
        return bool(
            self.config.api_key and
            self.config.base_url and
            self.config.models
        )

    def get_supported_models(self) -> List[str]:
        """Get list of supported models"""
        return self.config.models.copy()

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using Gemini API"""

        self._start_timing()

        # Get effective model
        effective_model = self.get_effective_model(model)

        # Prepare Gemini API request format
        generation_config = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }

        # Add optional parameters
        if "top_p" in kwargs:
            generation_config["topP"] = kwargs["top_p"]
        if "top_k" in kwargs:
            generation_config["topK"] = kwargs["top_k"]

        request_body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": generation_config,
            # Safety settings for troubleshooting use case
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
        }

        # Gemini API uses query parameter for API key
        url = f"{self.config.base_url.rstrip('/')}/models/{effective_model}:generateContent"
        params = {"key": self.config.api_key}
        headers = {"Content-Type": "application/json"}

        # Make request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                params=params,
                headers=headers,
                json=request_body,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as response:

                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Gemini API error {response.status}: {error_text}"
                    )

                data = await response.json()

                # Extract response content from Gemini format
                content = ""
                tokens_used = 0

                if "candidates" in data and data["candidates"]:
                    candidate = data["candidates"][0]

                    if "content" in candidate and "parts" in candidate["content"]:
                        for part in candidate["content"]["parts"]:
                            if "text" in part:
                                content += part["text"]

                    # Extract token usage
                    if "usageMetadata" in data:
                        tokens_used = data["usageMetadata"].get("totalTokenCount", 0)

                # Handle safety blocks
                if not content and "candidates" in data:
                    candidate = data["candidates"][0]
                    if "finishReason" in candidate:
                        finish_reason = candidate["finishReason"]
                        if finish_reason in ["SAFETY", "BLOCKED_REASON_UNSPECIFIED"]:
                            raise Exception("Content blocked by Gemini safety filters")

                if content:
                    content = self._validate_response_content(content)

                response_time = self._get_response_time_ms()

                return LLMResponse(
                    content=content,
                    confidence=self.config.confidence_score,
                    provider=self.provider_name,
                    model=effective_model,
                    tokens_used=tokens_used,
                    response_time_ms=response_time,
                    tool_calls=None,  # Gemini function calling uses different format
                )
