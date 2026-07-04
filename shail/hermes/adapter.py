"""
Hermes Core Adapter

Main adapter with autonomous retries and execution.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

from shail.hermes.types import (
    HermesRequest,
    HermesResponse,
    HermesSkill,
    ExecutionTrace,
    ExecutionStatus,
    RetryPolicy,
    RetryStrategy,
)

from shail.hermes.config import HermesConfig, get_hermes_config
from shail.hermes.model_client import ModelClient, get_model_client
from shail.hermes.multi_model import get_multi_model_runtime
from shail.hermes.persistent_memory import PersistentMemory, get_persistent_memory
from shail.hermes.reflection import Reflection, get_reflection
from shail.hermes.sandbox import ToolSandbox, get_sandbox
from shail.hermes.observability import get_hermes_observability


logger = logging.getLogger(__name__)


class HermesAdapter:
    """
    Core Hermes adapter with retry and execution.

    Features:
    - Execute tasks with skill-based execution
    - Autonomous retries with exponential backoff
    - Reflection after execution
    - Checkpoint support
    - Persistent, vectorized skill memory
    - Multi-model fallback (Ollama -> Claude)
    - Sandboxed tool execution
    - Real-time event observability
    """

    def __init__(self, config: Optional[HermesConfig] = None):
        self.config = config or get_hermes_config()
        # Use multi-model runtime for fallback capabilities
        self.model_client = get_multi_model_runtime()
        # Use PersistentMemory for vector storage and persistence
        self.skill_memory: PersistentMemory = get_persistent_memory()
        self.reflection: Reflection = get_reflection(self.skill_memory)
        # Sandbox for tool execution
        self.sandbox: ToolSandbox = get_sandbox()
        # Observability for event streaming
        self.observability = get_hermes_observability()

    async def run_in_sandbox(
        self,
        command: str,
        use_python: bool = False,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute a command or script in the isolated sandbox.
        """
        timeout = timeout or self.config.default_timeout_sec
        
        await self.observability.emit_event("sandbox_start", {"command": command[:200], "use_python": use_python})
        
        if use_python:
            result = await self.sandbox.run_python_script(command, timeout=timeout)
        else:
            result = await self.sandbox.run_command(command, timeout=timeout)
            
        await self.observability.emit_event("sandbox_end", {
            "success": result.success,
            "timed_out": result.timed_out,
            "execution_time_ms": result.execution_time_ms
        })

        # ── Permission Recovery Hook ──
        if not result.success and "Permission denied" in result.stderr:
            logger.warning("Permission denied detected in sandbox. Suggesting recovery.")
            await self.observability.emit_event("recovery_suggested", {
                "type": "permission",
                "message": "Permission denied. Try running 'bash setup_permissions.sh' to fix OS permissions.",
                "command": command
            })
            
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "execution_time_ms": result.execution_time_ms,
            "timed_out": result.timed_out
        }

    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        enable_retry: bool = True,
    ) -> HermesResponse:
        """
        Execute a task with Hermes capabilities.

        Args:
            task: Task description
            context: Execution context
            enable_retry: Enable autonomous retries

        Returns:
            HermesResponse with result or error
        """
        request_id = str(uuid.uuid4())
        context = context or {}

        await self.observability.emit_event("task_start", {"task": task[:200], "request_id": request_id})

        logger.info(f"Hermes executing task: {task[:50]}...")

        # Find applicable skill
        skills = self.skill_memory.search_skills(task)
        skill = skills[0] if skills else None

        if skill:
            logger.info(f"Using skill: {skill.name}")
            await self.observability.emit_event("skill_applied", {"skill_id": skill.skill_id, "name": skill.name})

        # Execute with or without retry
        if enable_retry:
            result = await self._execute_with_retry(
                request_id, task, context, skill
            )
        else:
            result = await self._execute_once(
                request_id, task, context, skill
            )
            
        await self.observability.emit_event("task_end", {
            "request_id": request_id,
            "status": result.status.value,
            "success": result.status == ExecutionStatus.COMPLETED
        })
        
        return result

    async def _execute_with_retry(
        self,
        request_id: str,
        task: str,
        context: Dict[str, Any],
        skill: Optional[HermesSkill],
    ) -> HermesResponse:
        """Execute with autonomous retry logic."""
        policy = self.config.default_retry_policy
        retry_count = 0
        last_error: Optional[str] = None

        while retry_count <= policy.max_retries:
            try:
                if retry_count > 0:
                    await self.observability.emit_event("retry_attempt", {
                        "request_id": request_id,
                        "attempt": retry_count,
                        "max_retries": policy.max_retries,
                        "last_error": last_error
                    })

                result = await self._execute_once(
                    request_id, task, context, skill
                )
                result.retry_count = retry_count
                logger.info(f"Task succeeded after {retry_count} retries")
                return result

            except Exception as e:
                retry_count += 1
                last_error = str(e)
                logger.warning(f"Attempt {retry_count} failed: {last_error}")

                if retry_count <= policy.max_retries:
                    # Calculate delay
                    delay = self._calculate_delay(policy, retry_count)
                    logger.info(f"Retrying in {delay}ms...")
                    await asyncio.sleep(delay / 1000)
                else:
                    logger.error(f"All {policy.max_retries} retries exhausted")

        # All retries exhausted - create failure response
        return HermesResponse(
            request_id=request_id,
            status=ExecutionStatus.FAILED,
            error=f"Retries exhausted: {last_error}",
            retry_count=retry_count,
            skill_used=skill.skill_id if skill else None,
        )

    def _calculate_delay(self, policy: RetryPolicy, attempt: int) -> float:
        """Calculate retry delay based on strategy."""
        if policy.strategy == RetryStrategy.EXPONENTIAL:
            # Exponential: 1000, 2000, 4000, 8000...
            delay = policy.base_delay_ms * (2 ** (attempt - 1))
        elif policy.strategy == RetryStrategy.LINEAR:
            # Linear: 1000, 2000, 3000, 4000...
            delay = policy.base_delay_ms * attempt
        elif policy.strategy == RetryStrategy.FIBONACCI:
            # Fibonacci: 1000, 1000, 2000, 3000, 5000...
            fib = [1, 1, 2, 3, 5, 8, 13, 21]
            idx = min(attempt - 1, len(fib) - 1)
            delay = policy.base_delay_ms * fib[idx]
        else:  # FIXED
            delay = policy.base_delay_ms

        # Cap at max delay
        return min(delay, policy.max_delay_ms)

    async def _execute_once(
        self,
        request_id: str,
        task: str,
        context: Dict[str, Any],
        skill: Optional[HermesSkill],
    ) -> HermesResponse:
        """Execute a single attempt (no retry)."""
        start_time = time.time()

        # Build prompt
        if skill:
            prompt = skill.prompt_template.format(task=task, **context)
            # Update skill stats
            self.skill_memory.update_skill_stats(skill.skill_id, success=True)
        else:
            # Default prompt format
            prompt = f"Task: {task}\n\nContext: {context}"

        try:
            # Call model
            response = await self.model_client.generate(prompt)

            execution_time = (time.time() - start_time) * 1000

            # Create trace for reflection
            trace = ExecutionTrace(
                trace_id=str(uuid.uuid4()),
                task=task,
                status=ExecutionStatus.COMPLETED,
                execution_time_ms=execution_time,
                result=response,
                skill_used=skill.skill_id if skill else None,
            )

            # Run reflection
            self.reflection.reflect(trace)

            return HermesResponse(
                request_id=request_id,
                status=ExecutionStatus.COMPLETED,
                result={"response": response},
                execution_time_ms=execution_time,
                skill_used=skill.skill_id if skill else None,
                model_used=self.config.default_model,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            # Create trace for reflection (failure)
            trace = ExecutionTrace(
                trace_id=str(uuid.uuid4()),
                task=task,
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time,
                skill_used=skill.skill_id if skill else None,
            )

            # Run reflection
            self.reflection.reflect(trace)

            # If skill was used, update its stats
            if skill:
                self.skill_memory.update_skill_stats(skill.skill_id, success=False)

            raise

    async def execute_with_skill(
        self,
        task: str,
        skill_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> HermesResponse:
        """Execute using a specific skill."""
        skill = self.skill_memory.get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        request_id = str(uuid.uuid4())
        context = context or {}

        return await self._execute_once(request_id, task, context, skill)

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        memory_stats = self.skill_memory.get_stats()
        reflection_summary = self.reflection.get_summary()

        return {
            "skills": memory_stats["total_skills"],
            "traces": memory_stats["total_traces"],
            "successful": memory_stats["successful_traces"],
            "failed": memory_stats["failed_traces"],
            "avg_skill_rate": memory_stats["avg_skill_success_rate"],
            "reflection": reflection_summary,
        }


# Singleton instance
_hermes_adapter: Optional[HermesAdapter] = None


def get_hermes_adapter() -> HermesAdapter:
    """Get singleton Hermes adapter."""
    global _hermes_adapter
    if _hermes_adapter is None:
        _hermes_adapter = HermesAdapter()
    return _hermes_adapter


def reset_hermes_adapter() -> HermesAdapter:
    """Reset Hermes adapter (for testing)."""
    global _hermes_adapter
    from shail.hermes.persistent_memory import reset_persistent_memory
    from shail.hermes.reflection import reset_reflection
    from shail.hermes.sandbox import reset_sandbox
    from shail.hermes.observability import reset_hermes_observability

    pm = reset_persistent_memory()
    reset_reflection(pm)
    reset_sandbox()
    reset_hermes_observability()

    _hermes_adapter = HermesAdapter()
    return _hermes_adapter