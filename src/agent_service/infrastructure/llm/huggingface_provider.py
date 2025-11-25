"""HuggingFace provider implementation.

HuggingFace provides access to open-source LLMs through their Inference API.
Supports both free tier (with cold starts) and dedicated endpoints.

⚠️ WARNING: Free tier models may have 10-60 second cold start delays.
For production use, consider dedicated HuggingFace Inference Endpoints.
"""

import aiohttp
import asyncio
import json
from typing import List, Optional, Dict, Any

from .base import BaseLLMProvider, LLMResponse, ProviderConfig, ToolCall


class HuggingFaceProvider(BaseLLMProvider):
    """HuggingFace Inference API provider implementation"""

    @property
    def provider_name(self) -> str:
        return "huggingface"

    def is_available(self) -> bool:
        """Check if HuggingFace provider is properly configured"""
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
        """Generate response using HuggingFace Inference API

        Args:
            prompt: Input text prompt
            model: HuggingFace model ID (e.g., "meta-llama/Llama-3.2-3B-Instruct")
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            tools: Function calling tools (not supported by most HF models)
            tool_choice: Tool choice strategy (not supported)
            **kwargs: Additional HuggingFace-specific parameters

        Returns:
            LLMResponse with generated content

        Note:
            - Free tier models may take 10-60s to warm up (cold start)
            - Function calling (tools) is not supported by most HF models
            - Some models use different API formats - this handles common cases
        """
        self._start_timing()

        # Get effective model
        effective_model = self.get_effective_model(model)

        # Prepare headers for HuggingFace API
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        # Prepare request body for HuggingFace API format
        # Note: HuggingFace uses "inputs" instead of "messages"
        request_body = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "return_full_text": False,
                "do_sample": True
            }
        }

        # Add optional parameters
        if "top_p" in kwargs:
            request_body["parameters"]["top_p"] = kwargs["top_p"]
        if "top_k" in kwargs:
            request_body["parameters"]["top_k"] = kwargs["top_k"]
        if "repetition_penalty" in kwargs:
            request_body["parameters"]["repetition_penalty"] = kwargs["repetition_penalty"]
        if "stop_sequences" in kwargs:
            request_body["parameters"]["stop"] = kwargs["stop_sequences"]

        # Add wait_for_model parameter to handle cold starts
        request_body["options"] = {"wait_for_model": True}

        # Construct URL
        url = f"{self.config.base_url.rstrip('/')}/{effective_model}"

        # Make API request with retry logic for cold starts
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:

                    # Handle 503 (model loading)
                    if response.status == 503:
                        # Model is loading - wait and retry
                        await asyncio.sleep(10)
                        return await self._retry_request(
                            session, url, headers, request_body, effective_model
                        )

                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"HuggingFace API error {response.status}: {error_text}"
                        )

                    response_data = await response.json()

            except asyncio.TimeoutError:
                raise Exception(
                    f"HuggingFace API timeout. Model '{effective_model}' may be cold "
                    f"starting (can take 30-60s on free tier). Consider using a "
                    f"dedicated endpoint for production."
                )

        # Extract content from HuggingFace response
        content = self._extract_content(response_data)

        # Validate content
        content = self._validate_response_content(content)

        # Calculate response time
        response_time = self._get_response_time_ms()

        # Estimate token usage (HuggingFace doesn't always provide this)
        tokens_used = self._estimate_tokens(content)

        # Calculate confidence based on model and response quality
        confidence = self._calculate_confidence(effective_model, content, response_data)

        return LLMResponse(
            content=content,
            confidence=confidence,
            provider=self.provider_name,
            model=effective_model,
            tokens_used=tokens_used,
            response_time_ms=response_time,
            tool_calls=None,  # Most HF models don't support function calling
        )

    async def _retry_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict,
        request_body: dict,
        model: str
    ) -> LLMResponse:
        """Retry request after model loading"""
        async with session.post(
            url,
            headers=headers,
            json=request_body,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        ) as response:

            if response.status != 200:
                error_text = await response.text()
                raise Exception(
                    f"HuggingFace API error on retry {response.status}: {error_text}"
                )

            response_data = await response.json()

        content = self._extract_content(response_data)
        content = self._validate_response_content(content)
        response_time = self._get_response_time_ms()
        tokens_used = self._estimate_tokens(content)
        confidence = self._calculate_confidence(model, content, response_data)

        return LLMResponse(
            content=content,
            confidence=confidence,
            provider=self.provider_name,
            model=model,
            tokens_used=tokens_used,
            response_time_ms=response_time,
            tool_calls=None,
        )

    def _extract_content(self, response_data: Any) -> str:
        """Extract text content from HuggingFace API response

        HuggingFace models return different response formats:
        - Text generation: [{"generated_text": "..."}]
        - Some models: [{"text": "..."}]
        - Others: {"generated_text": "..."}
        """
        content = ""

        if isinstance(response_data, list) and len(response_data) > 0:
            # Standard array response
            first_result = response_data[0]
            if isinstance(first_result, dict):
                content = (
                    first_result.get("generated_text") or
                    first_result.get("text") or
                    ""
                )
        elif isinstance(response_data, dict):
            # Direct dict response
            content = (
                response_data.get("generated_text") or
                response_data.get("text") or
                ""
            )

        return str(content).strip()

    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count (rough approximation: ~4 chars per token)"""
        return max(1, len(content) // 4)

    def _calculate_confidence(self, model: str, content: str, response_data: dict) -> float:
        """Calculate confidence score based on model quality and response"""

        base_confidence = self.config.confidence_score

        # Model-specific confidence adjustments
        # Larger, newer models generally produce better results
        model_confidence_map = {
            # High-quality instruction models
            "meta-llama/llama-3": 0.85,
            "meta-llama/llama-2": 0.80,
            "mistralai/mistral": 0.82,
            "mistralai/mixtral": 0.85,
            "tiiuae/falcon": 0.78,
            # Smaller/older models
            "gpt2": 0.60,
            "distilgpt2": 0.55,
            "microsoft/dialogpt": 0.65,
        }

        # Find matching model confidence
        model_confidence = base_confidence
        model_lower = model.lower()
        for model_name, confidence in model_confidence_map.items():
            if model_name.lower() in model_lower:
                model_confidence = confidence
                break

        # Adjust based on content quality
        content_length = len(content.strip())

        if content_length == 0:
            return 0.0
        elif content_length < 30:
            # Very short responses might be less reliable
            model_confidence *= 0.7
        elif content_length > 300:
            # Longer responses from smaller models might be less coherent
            model_confidence *= 0.95

        # Check for common generation issues
        problematic_patterns = [
            "<unk>", "<pad>", "<eos>", "[UNK]", "[PAD]", "[EOS]",
            "sorry, i", "i cannot", "i can't", "not able to"
        ]

        content_lower = content.lower()
        for pattern in problematic_patterns:
            if pattern in content_lower:
                model_confidence *= 0.6
                break

        # Check for repetitive content (common with smaller models)
        words = content.split()
        if len(words) > 10:
            unique_words = set(words)
            repetition_ratio = len(unique_words) / len(words)
            if repetition_ratio < 0.7:  # High repetition
                model_confidence *= 0.8

        # Ensure confidence is within valid range
        return min(1.0, max(0.0, model_confidence))
