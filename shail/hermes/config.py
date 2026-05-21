"""
Hermes Configuration

Configuration for Hermes MVP.
"""

from pydantic import BaseModel, Field
from shail.hermes.types import RetryPolicy, RetryStrategy


class HermesConfig(BaseModel):
    """Configuration for Hermes adapter."""
    enabled: bool = Field(default=True, description="Enable Hermes")
    ollama_endpoint: str = Field(
        default="http://localhost:11434",
        description="Ollama API endpoint"
    )
    default_model: str = Field(
        default="llama3.2",
        description="Default model to use"
    )
    default_retry_policy: RetryPolicy = Field(
        default_factory=lambda: RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            max_retries=3,
            base_delay_ms=1000,
            max_delay_ms=30000,
        ),
        description="Default retry policy"
    )
    max_concurrent_subagents: int = Field(
        default=10,
        description="Maximum concurrent subagents"
    )
    skill_memory_enabled: bool = Field(
        default=True,
        description="Enable skill memory"
    )
    reflection_enabled: bool = Field(
        default=True,
        description="Enable reflection"
    )
    # Sandbox settings
    sandbox_enabled: bool = Field(
        default=True,
        description="Enable tool sandboxing"
    )
    default_timeout_sec: float = Field(
        default=60.0,
        description="Default timeout for tool execution"
    )
    sandbox_dir: str = Field(
        default="~/Library/Application Support/SHAIL/sandbox",
        description="Directory for sandbox environments"
    )


# Global config instance
_hermes_config: HermesConfig = None


def get_hermes_config() -> HermesConfig:
    """Get Hermes configuration singleton."""
    global _hermes_config
    if _hermes_config is None:
        _hermes_config = HermesConfig()
    return _hermes_config


def set_hermes_config(config: HermesConfig):
    """Set Hermes configuration."""
    global _hermes_config
    _hermes_config = config