"""
Subagent Runtime

Isolated Hermes agents spawned per graph node/task.
Supports retries + resumable execution.
"""

import asyncio
import logging
import uuid
import time
from typing import Any, Dict, List, Optional, Callable, Awaitable
from concurrent.futures import ThreadPoolExecutor

from shail.hermes.types import (
    HermesSubagent,
    HermesRequest,
    HermesResponse,
    ExecutionStatus,
)
from shail.hermes.config import get_hermes_config
from shail.hermes.types import RetryPolicy
from shail.hermes.adapter import HermesAdapter, get_hermes_adapter


logger = logging.getLogger(__name__)


class SubagentRuntime:
    """
    Runtime for isolated Hermes subagents.

    Features:
    - Isolated execution contexts per subagent
    - Retry support with configurable policies
    - Resumable execution via checkpoints
    - Resource limits (max concurrent)
    """

    def __init__(
        self,
        adapter: Optional[HermesAdapter] = None,
        max_concurrent: int = 10,
        default_timeout: float = 300.0,
    ):
        self.adapter = adapter or get_hermes_adapter()
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout

        self._subagents: Dict[str, HermesSubagent] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._checkpoints: Dict[str, Dict] = {}

    async def spawn(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Spawn a new subagent with isolated execution context.

        Args:
            task: Task description
            context: Execution context
            parent_id: Parent request ID for hierarchy
            timeout: Execution timeout in seconds

        Returns:
            Subagent ID
        """
        subagent_id = f"sub_{uuid.uuid4().hex[:8]}"
        context = context or {}

        subagent = HermesSubagent(
            subagent_id=subagent_id,
            parent_id=parent_id,
            task=task,
            context=context,
            status=ExecutionStatus.PENDING,
        )

        self._subagents[subagent_id] = subagent
        logger.info(f"Spawned subagent: {subagent_id}")

        # Execute in background with concurrency limit
        task = asyncio.create_task(
            self._execute_subagent(
                subagent_id,
                task,
                context,
                timeout or self.default_timeout,
            )
        )
        self._active_tasks[subagent_id] = task

        return subagent_id

    async def _execute_subagent(
        self,
        subagent_id: str,
        task: str,
        context: Dict[str, Any],
        timeout: float,
    ):
        """Execute a subagent with semaphore-based concurrency control."""
        subagent = self._subagents.get(subagent_id)
        if not subagent:
            logger.error(f"Subagent not found: {subagent_id}")
            return

        async with self._semaphore:
            subagent.status = ExecutionStatus.RUNNING
            logger.info(f"Subagent {subagent_id} started")

            start_time = time.time()

            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self.adapter.execute(task, context, enable_retry=True),
                    timeout=timeout,
                )

                execution_time = (time.time() - start_time) * 1000

                subagent.status = (
                    ExecutionStatus.COMPLETED
                    if result.status == ExecutionStatus.COMPLETED
                    else ExecutionStatus.FAILED
                )
                subagent.result = result

                logger.info(
                    f"Subagent {subagent_id} completed: {subagent.status.value} "
                    f"in {execution_time:.2f}ms"
                )

            except asyncio.TimeoutError:
                execution_time = (time.time() - start_time) * 1000
                subagent.status = ExecutionStatus.FAILED
                logger.error(
                    f"Subagent {subagent_id} timed out after {execution_time:.2f}ms"
                )

            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                subagent.status = ExecutionStatus.FAILED
                logger.error(f"Subagent {subagent_id} failed: {e}")

            finally:
                # Clean up active task
                if subagent_id in self._active_tasks:
                    del self._active_tasks[subagent_id]

    async def spawn_and_wait(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> HermesResponse:
        """
        Spawn a subagent and wait for completion.

        Args:
            task: Task description
            context: Execution context
            timeout: Maximum wait time in seconds

        Returns:
            HermesResponse from subagent execution
        """
        subagent_id = await self.spawn(task, context, timeout=timeout)

        # Wait for completion
        timeout_sec = timeout or self.default_timeout
        try:
            await asyncio.wait_for(
                self._wait_for_subagent(subagent_id),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Wait timeout for subagent: {subagent_id}")

        # Get result
        subagent = self._subagents.get(subagent_id)
        if subagent and subagent.result:
            return subagent.result
        else:
            return HermesResponse(
                request_id=subagent_id,
                status=ExecutionStatus.FAILED,
                error="Subagent did not complete",
            )

    async def _wait_for_subagent(self, subagent_id: str):
        """Wait for a specific subagent to complete."""
        while subagent_id in self._active_tasks:
            await asyncio.sleep(0.1)

    async def cancel(self, subagent_id: str) -> bool:
        """
        Cancel a running subagent.

        Args:
            subagent_id: ID of subagent to cancel

        Returns:
            True if cancelled, False if not found
        """
        subagent = self._subagents.get(subagent_id)
        if not subagent:
            return False

        # Cancel if still running
        if subagent_id in self._active_tasks:
            task = self._active_tasks[subagent_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        subagent.status = ExecutionStatus.CANCELLED
        logger.info(f"Subagent {subagent_id} cancelled")
        return True

    async def get_status(self, subagent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current subagent status.

        Args:
            subagent_id: ID of subagent

        Returns:
            Status dict or None if not found
        """
        subagent = self._subagents.get(subagent_id)
        if not subagent:
            return None

        return {
            "subagent_id": subagent.subagent_id,
            "task": subagent.task,
            "status": subagent.status.value,
            "parent_id": subagent.parent_id,
            "has_result": subagent.result is not None,
        }

    async def list_subagents(
        self,
        status: Optional[ExecutionStatus] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all subagents, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of subagent status dicts
        """
        subagents = []

        for subagent in self._subagents.values():
            if status and subagent.status != status:
                continue

            subagents.append({
                "subagent_id": subagent.subagent_id,
                "task": subagent.task,
                "status": subagent.status.value,
                "parent_id": subagent.parent_id,
                "has_result": subagent.result is not None,
            })

        return subagents

    async def get_active_count(self) -> int:
        """Get count of active (running) subagents."""
        return sum(
            1 for s in self._subagents.values()
            if s.status == ExecutionStatus.RUNNING
        )

    async def get_pending_count(self) -> int:
        """Get count of pending subagents."""
        return sum(
            1 for s in self._subagents.values()
            if s.status == ExecutionStatus.PENDING
        )

    async def get_completed_count(self) -> int:
        """Get count of completed subagents."""
        return sum(
            1 for s in self._subagents.values()
            if s.status == ExecutionStatus.COMPLETED
        )

    async def get_failed_count(self) -> int:
        """Get count of failed subagents."""
        return sum(
            1 for s in self._subagents.values()
            if s.status == ExecutionStatus.FAILED
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        return {
            "total_subagents": len(self._subagents),
            "active": sum(
                1 for s in self._subagents.values()
                if s.status == ExecutionStatus.RUNNING
            ),
            "running": sum(
                1 for s in self._subagents.values()
                if s.status == ExecutionStatus.RUNNING
            ),
            "pending": sum(
                1 for s in self._subagents.values()
                if s.status == ExecutionStatus.PENDING
            ),
            "completed": sum(
                1 for s in self._subagents.values()
                if s.status == ExecutionStatus.COMPLETED
            ),
            "failed": sum(
                1 for s in self._subagents.values()
                if s.status == ExecutionStatus.FAILED
            ),
            "max_concurrent": self.max_concurrent,
            "available_slots": self.max_concurrent - self._semaphore._value,
        }

    async def cleanup(
        self,
        older_than_seconds: int = 3600,
        keep_completed: bool = True,
    ):
        """
        Clean up old subagents.

        Args:
            older_than_seconds: Remove subagents older than this
            keep_completed: Keep completed subagents
        """
        now = time.time()
        to_remove = []

        for subagent_id, subagent in self._subagents.items():
            age = now - subagent.created_at

            if age > older_than_seconds:
                # Don't remove if completed and we want to keep them
                if keep_completed and subagent.status == ExecutionStatus.COMPLETED:
                    continue
                to_remove.append(subagent_id)

        for subagent_id in to_remove:
            del self._subagents[subagent_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} subagents")


# Singleton instance
_subagent_runtime: Optional[SubagentRuntime] = None


def get_subagent_runtime(
    adapter: Optional[HermesAdapter] = None,
    max_concurrent: int = 10,
) -> SubagentRuntime:
    """Get singleton subagent runtime."""
    global _subagent_runtime
    if _subagent_runtime is None:
        _subagent_runtime = SubagentRuntime(adapter, max_concurrent)
    return _subagent_runtime


def reset_subagent_runtime(
    adapter: Optional[HermesAdapter] = None,
    max_concurrent: int = 10,
) -> SubagentRuntime:
    """Reset subagent runtime singleton (for testing)."""
    global _subagent_runtime
    _subagent_runtime = SubagentRuntime(adapter, max_concurrent)
    return _subagent_runtime