"""
Hermes - Adaptive Capability Layer for SHAIL

MVP Features:
- Persistent agent memory (in-memory + file-based)
- Skill generation from execution traces
- Subagents for parallel execution
- Autonomous retries with exponential backoff
- Model-agnostic runtime (Ollama + Claude fallback)
- Basic reflection (store failure/success)
"""

# Sprint 1: Types and Config
from shail.hermes.types import (
    HermesRequest,
    HermesResponse,
    HermesSkill,
    ExecutionTrace,
    ExecutionStatus,
    RetryPolicy,
    RetryStrategy,
    HermesSubagent,
    HermesCheckpoint,
)

from shail.hermes.config import HermesConfig, get_hermes_config

from shail.hermes.model_client import ModelClient, OllamaClient, get_model_client, get_ollama_client

# Sprint 2: Skill Memory and Reflection
from shail.hermes.skill_memory import SkillMemory, get_skill_memory, reset_skill_memory
from shail.hermes.reflection import Reflection, get_reflection

# Sprint 3: Core Adapter
from shail.hermes.adapter import HermesAdapter, get_hermes_adapter, reset_hermes_adapter

# Sprint 4: Subagent Runtime
from shail.hermes.subagent_runtime import SubagentRuntime, get_subagent_runtime, reset_subagent_runtime

# Sprint 7: Persistent Memory (MVP - file-based)
from shail.hermes.persistent_memory import PersistentMemory, get_persistent_memory

# Sprint 8: Multi-Model Runtime
from shail.hermes.multi_model import (
    ClaudeClient,
    MultiModelClient,
    get_multi_model_client,
    get_multi_model_runtime,
)

# Integration with SHAIL
from shail.hermes.integration import (
    HermesSHAILIntegration,
    get_hermes_sail_integration,
    execute_with_hermes_retry,
    spawn_hermes_subagent,
    get_hermes_stats,
)


__all__ = [
    # Types
    "HermesRequest",
    "HermesResponse",
    "HermesSkill",
    "ExecutionTrace",
    "ExecutionStatus",
    "RetryPolicy",
    "RetryStrategy",
    "HermesSubagent",
    "HermesCheckpoint",
    # Config
    "HermesConfig",
    "get_hermes_config",
    # Model Client
    "ModelClient",
    "OllamaClient",
    "get_model_client",
    "get_ollama_client",
    # Skill Memory
    "SkillMemory",
    "get_skill_memory",
    "reset_skill_memory",
    # Reflection
    "Reflection",
    "get_reflection",
    # Adapter
    "HermesAdapter",
    "get_hermes_adapter",
    "reset_hermes_adapter",
    # Subagent
    "SubagentRuntime",
    "get_subagent_runtime",
    "reset_subagent_runtime",
    # Persistent Memory (Sprint 7)
    "PersistentMemory",
    "get_persistent_memory",
    # Multi-Model (Sprint 8)
    "ClaudeClient",
    "MultiModelClient",
    "get_multi_model_client",
    "get_multi_model_runtime",
    # Integration with SHAIL
    "HermesSHAILIntegration",
    "get_hermes_sail_integration",
    "execute_with_hermes_retry",
    "spawn_hermes_subagent",
    "get_hermes_stats",
]