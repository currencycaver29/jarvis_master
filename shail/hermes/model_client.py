"""
Model Client Abstraction

Abstract model client interface and Ollama implementation.
Supports model-agnostic runtime for MVP.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional
import aiohttp

from shail.hermes.config import get_hermes_config


logger = logging.getLogger(__name__)


class ModelClient(ABC):
    """Abstract base class for model clients."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a response from the model.

        Args:
            prompt: Input prompt
            model: Model name (optional, uses default)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the model client is healthy."""
        pass


class OllamaClient(ModelClient):
    """Ollama model client for local models."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        config = get_hermes_config()
        self.endpoint = endpoint or config.ollama_endpoint
        self.default_model = default_model or config.default_model
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate response from Ollama."""
        model = model or self.default_model
        session = await self._get_session()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with session.post(
                f"{self.endpoint}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama error {response.status}: {error_text}")

                data = await response.json()
                return data.get("response", "")

        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise Exception(f"Failed to connect to Ollama: {e}")

    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.endpoint}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                return response.status == 200
        except Exception:
            return False


class MockClient(ModelClient):
    """Mock client for testing without Ollama."""

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return a mock response."""
        return f"Mock response to: {prompt[:50]}..."

    async def health_check(self) -> bool:
        """Always healthy."""
        return True


# Client factory
def get_model_client(provider: str = "ollama") -> ModelClient:
    """
    Get model client based on provider.

    Args:
        provider: Provider name ("ollama", "mock")

    Returns:
        ModelClient instance
    """
    if provider == "ollama":
        return OllamaClient()
    elif provider == "mock":
        return MockClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")


# Singleton instances
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get singleton Ollama client."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client