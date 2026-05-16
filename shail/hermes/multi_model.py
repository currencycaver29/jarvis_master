"""
Multi-Model Client

Add Claude as fallback to Ollama for Sprint 8 MVP.
Model-agnostic runtime with fallback chain.

For production:
- Add OpenAI, Gemini clients
- Add cost-based routing
- Add latency-based routing
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from shail.hermes.model_client import ModelClient


logger = logging.getLogger(__name__)


class ClaudeClient(ModelClient):
    """Anthropic Claude client for Hermes."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-haiku-20240307",
    ):
        self.api_key = api_key
        self.model = model
        self._client = None

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate response from Claude."""
        model = model or self.model

        # Check if API key is available
        if not self.api_key:
            # Try to get from environment
            import os
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not set")

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }

                payload = {
                    "model": model,
                    "max_tokens": max_tokens or 1024,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }

                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Claude API error: {response.status} - {error_text}")

                    data = await response.json()
                    return data["content"][0]["text"]

        except Exception as e:
            logger.error(f"Claude generation failed: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if Claude API is available."""
        if not self.api_key:
            import os
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            return False

        try:
            # Just check if we can make a simple request
            await self.generate("Hi", max_tokens=5)
            return True
        except Exception:
            return False


class MultiModelClient(ModelClient):
    """
    Multi-model client with fallback chain.

    Tries Ollama first, falls back to Claude if Ollama fails.
    """

    def __init__(
        self,
        ollama_endpoint: str = "http://localhost:11434",
        claude_api_key: Optional[str] = None,
        default_model: str = "llama3.2",
        fallback_to_claude: bool = True,
    ):
        from shail.hermes.model_client import OllamaClient

        self.ollama_client = OllamaClient(endpoint=ollama_endpoint, default_model=default_model)
        self.claude_client = None

        if claude_api_key:
            self.claude_client = ClaudeClient(api_key=claude_api_key)
        else:
            # Try to get from environment
            import os
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            if anthropic_key:
                self.claude_client = ClaudeClient(api_key=anthropic_key)

        self.fallback_to_claude = fallback_to_claude
        self.default_model = default_model

        # Track which model last succeeded
        self._last_successful_provider = None

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate with fallback chain."""
        model = model or self.default_model

        # Try Ollama first
        try:
            result = await self.ollama_client.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._last_successful_provider = "ollama"
            return result

        except Exception as ollama_error:
            logger.warning(f"Ollama failed: {ollama_error}")

            # Try Claude if enabled
            if self.fallback_to_claude and self.claude_client:
                try:
                    result = await self.claude_client.generate(
                        prompt=prompt,
                        model="claude-3-haiku-20240307",
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    self._last_successful_provider = "claude"
                    logger.info("Fallback to Claude succeeded")
                    return result

                except Exception as claude_error:
                    logger.error(f"Claude fallback failed: {claude_error}")
                    raise Exception(f"All models failed. Ollama: {ollama_error}, Claude: {claude_error}")

            # No fallback available
            raise

    async def health_check(self) -> bool:
        """Check if any model is available."""
        # Check Ollama
        ollama_healthy = await self.ollama_client.health_check()
        if ollama_healthy:
            return True

        # Check Claude if available
        if self.claude_client:
            claude_healthy = await self.claude_client.health_check()
            if claude_healthy:
                return True

        return False

    def get_available_providers(self) -> list:
        """Get list of available providers."""
        providers = ["ollama"]
        if self.claude_client:
            providers.append("claude")
        return providers

    def get_last_successful_provider(self) -> Optional[str]:
        """Get the provider that last succeeded."""
        return self._last_successful_provider


# Factory function
def get_multi_model_client(
    provider: str = "multi",
    **kwargs,
) -> ModelClient:
    """
    Get model client based on provider.

    Args:
        provider: "ollama", "claude", "multi", or "mock"
        **kwargs: Additional parameters

    Returns:
        ModelClient instance
    """
    if provider == "ollama":
        from shail.hermes.model_client import OllamaClient
        return OllamaClient(**kwargs)

    elif provider == "claude":
        return ClaudeClient(**kwargs)

    elif provider == "multi":
        return MultiModelClient(**kwargs)

    elif provider == "mock":
        from shail.hermes.model_client import MockClient
        return MockClient()

    else:
        raise ValueError(f"Unknown provider: {provider}")


# Singleton for multi-model
_multi_model_client: Optional[MultiModelClient] = None


def get_multi_model_runtime() -> MultiModelClient:
    """Get singleton multi-model runtime."""
    global _multi_model_client
    if _multi_model_client is None:
        _multi_model_client = MultiModelClient()
    return _multi_model_client