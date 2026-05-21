"""
Hermes Integration with SHAIL

Integrates Hermes as a capability layer into SHAIL without replacing the core orchestrator.

SHAIL-native (NOT replaced):
- MasterPlanner
- LangGraphExecutor
- Worker Pool
- Jarvis/SuperMemory
- Graph Stream Server

Hermes provides:
- Retry logic for failed tasks
- Skill-based execution
- Subagent spawning for parallel tasks
- Multi-model fallback
- Persistent memory
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List

from shail.hermes import (
    HermesAdapter,
    get_hermes_adapter,
    SubagentRuntime,
    get_subagent_runtime,
    get_persistent_memory,
    get_multi_model_runtime,
    MultiModelClient,
    HermesResponse,
    ExecutionStatus,
)


logger = logging.getLogger(__name__)


class HermesSHAILIntegration:
    """
    Integration layer connecting Hermes to SHAIL components.

    This class provides methods to enhance existing SHAIL components
    with Hermes capabilities without replacing the orchestrator.
    """

    def __init__(self):
        self.adapter = get_hermes_adapter()
        self.subagent_runtime = get_subagent_runtime()
        self.persistent_memory = get_persistent_memory()
        self.multi_model = get_multi_model_runtime()

        # Settings
        self.hermes_enabled = True
        self.use_subagents = True
        self.use_fallback = True

    async def initialize(self):
        """Initialize Hermes integration with SHAIL."""
        logger.info("Initializing Hermes-SHAIL integration")

        # Check model availability
        ollama_healthy = await self.adapter.model_client.health_check()
        logger.info(f"Ollama available: {ollama_healthy}")

        # Setup multi-model fallback
        if self.use_fallback:
            logger.info("Multi-model fallback enabled")

        logger.info("Hermes-SHAIL integration ready")

    # ===== Integration with Worker Pool =====

    async def execute_task_with_hermes(
        self,
        task_text: str,
        context: Optional[Dict[str, Any]] = None,
        use_subagent: bool = False,
    ) -> HermesResponse:
        """
        Execute a task using Hermes capabilities.

        This can be called from TaskWorker to leverage:
        - Retry logic on failure
        - Skill-based execution
        - Multi-model fallback
        """
        if not self.hermes_enabled:
            raise Exception("Hermes integration is disabled")

        if use_subagent and self.use_subagents:
            # Spawn as subagent for parallel execution
            subagent_id = await self.subagent_runtime.spawn(task_text, context)
            logger.info(f"Task spawned as subagent: {subagent_id}")

            # Wait for completion
            result = await self.subagent_runtime.spawn_and_wait(task_text, context)
            return result
        else:
            # Direct execution with retry
            return await self.adapter.execute(task_text, context, enable_retry=True)

    async def execute_parallel_tasks(
        self,
        tasks: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[HermesResponse]:
        """
        Execute multiple tasks in parallel using subagents.

        This replaces the need for manual worker distribution -
        Hermes handles it with subagents.
        """
        subagent_ids = []

        for task in tasks:
            subagent_id = await self.subagent_runtime.spawn(task, context)
            subagent_ids.append(subagent_id)

        # Wait for all to complete
        results = []
        for subagent_id in subagent_ids:
            result = await self.subagent_runtime.spawn_and_wait(
                tasks[subagent_ids.index(subagent_id)],
                context,
            )
            results.append(result)

        return results

    # ===== Integration with LangGraph =====

    async def execute_with_retry(
        self,
        node_name: str,
        task: str,
        context: Dict[str, Any],
    ) -> HermesResponse:
        """
        Execute a graph node with Hermes retry logic.

        This can be called from LangGraph nodes that need retry capability.
        """
        logger.info(f"Executing node '{node_name}' with Hermes retry")

        result = await self.adapter.execute(
            task=task,
            context=context,
            enable_retry=True,
        )

        return result

    # ===== Integration with Memory =====

    def get_hermes_skills(self) -> List[Any]:
        """Get all stored Hermes skills."""
        return self.persistent_memory.get_all_skills()

    def get_hermes_stats(self) -> Dict[str, Any]:
        """Get Hermes statistics."""
        return {
            "adapter": self.adapter.get_stats(),
            "subagents": self.subagent_runtime.get_stats(),
            "memory": self.persistent_memory.get_stats(),
        }

    # ===== Multi-Model Integration =====

    async def get_best_model(self) -> str:
        """Get the best available model."""
        providers = self.multi_model.get_available_providers()
        if not providers:
            return "none"

        # Prefer Ollama, fallback to Claude
        if "ollama" in providers:
            return "ollama"
        elif "claude" in providers:
            return "claude"
        return providers[0]


# Singleton
_hermes_sail_integration: Optional[HermesSHAILIntegration] = None


def get_hermes_sail_integration() -> HermesSHAILIntegration:
    """Get singleton Hermes-SHAIL integration."""
    global _hermes_sail_integration
    if _hermes_sail_integration is None:
        _hermes_sail_integration = HermesSHAILIntegration()
    return _hermes_sail_integration


def reset_hermes_sail_integration() -> HermesSHAILIntegration:
    """Reset Hermes-SHAIL integration singleton (for testing)."""
    global _hermes_sail_integration
    from shail.hermes.adapter import reset_hermes_adapter
    from shail.hermes.subagent_runtime import reset_subagent_runtime
    
    reset_hermes_adapter()
    reset_subagent_runtime()
    
    _hermes_sail_integration = HermesSHAILIntegration()
    return _hermes_sail_integration


# ===== Helper Functions =====

async def execute_with_hermes_retry(task: str, context: Dict = None) -> Dict:
    """
    Simple helper to execute a task with Hermes retry.

    Usage:
        result = await execute_with_hermes_retry("Analyze this", {"key": "value"})
    """
    integration = get_hermes_sail_integration()
    response = await integration.execute_task_with_hermes(task, context)

    return {
        "success": response.status == ExecutionStatus.COMPLETED,
        "result": response.result,
        "error": response.error,
        "execution_time_ms": response.execution_time_ms,
        "retry_count": response.retry_count,
    }


async def spawn_hermes_subagent(task: str, context: Dict = None) -> str:
    """
    Simple helper to spawn a Hermes subagent.

    Usage:
        subagent_id = await spawn_hermes_subagent("Process this", {"data": "xyz"})
    """
    integration = get_hermes_sail_integration()
    return await integration.subagent_runtime.spawn(task, context)


def get_hermes_stats() -> Dict:
    """Get Hermes statistics."""
    integration = get_hermes_sail_integration()
    return integration.get_hermes_stats()