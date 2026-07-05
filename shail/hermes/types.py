"""
Hermes Type Definitions

Core types for Hermes MVP implementation.
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Enums
class ExecutionStatus(str, Enum):
    """Execution status for tasks and subagents."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class RetryStrategy(str, Enum):
    """Retry strategies for autonomous retries."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


# Request/Response
class HermesRequest(BaseModel):
    """Request to Hermes adapter."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task: str = Field(description="Task description")
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context")
    enable_retry: bool = Field(default=True, description="Enable autonomous retries")


class HermesResponse(BaseModel):
    """Response from Hermes adapter."""
    model_config = {"protected_namespaces": ()}

    request_id: str
    status: ExecutionStatus
    result: Optional[Any] = Field(default=None, description="Execution result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time_ms: float = Field(default=0, description="Execution time in milliseconds")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    skill_used: Optional[str] = Field(default=None, description="Skill ID used if any")
    model_used: Optional[str] = Field(default=None, description="Model used for execution")


# Skill
class HermesSkill(BaseModel):
    """Generated skill from execution traces."""
    skill_id: str = Field(default_factory=lambda: f"skill_{uuid.uuid4().hex[:8]}")
    name: str = Field(description="Skill name")
    prompt_template: str = Field(description="Prompt template for skill execution")
    description: Optional[str] = Field(default=None, description="Skill description")
    success_rate: float = Field(default=1.0, description="Success rate (0-1)")
    execution_count: int = Field(default=0, description="Number of executions")
    tags: List[str] = Field(default_factory=list, description="Skill tags")


# Execution Trace for Reflection
class ExecutionTrace(BaseModel):
    """Execution trace for reflection and skill generation."""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task: str = Field(description="Task that was executed")
    status: ExecutionStatus = Field(description="Execution status")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time_ms: float = Field(default=0, description="Execution time in ms")
    result: Optional[Any] = Field(default=None, description="Execution result")
    retry_count: int = Field(default=0, description="Retries used")
    skill_used: Optional[str] = Field(default=None, description="Skill ID used, if any")


# Retry Policy
class RetryPolicy(BaseModel):
    """Configuration for autonomous retries."""
    strategy: RetryStrategy = Field(default=RetryStrategy.EXPONENTIAL)
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    base_delay_ms: float = Field(default=1000, description="Base delay in milliseconds")
    max_delay_ms: float = Field(default=30000, description="Maximum delay in milliseconds")
    retry_on_errors: List[str] = Field(
        default_factory=lambda: ["timeout", "rate_limit", "transient"],
        description="Error types to retry on"
    )


# Subagent
class HermesSubagent(BaseModel):
    """Isolated subagent for parallel execution."""
    subagent_id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")
    parent_id: Optional[str] = Field(default=None, description="Parent request ID")
    task: str = Field(description="Task for subagent")
    context: Dict[str, Any] = Field(default_factory=dict)
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    created_at: float = Field(default_factory=lambda: __import__("time").time())
    result: Optional[HermesResponse] = Field(default=None)


# Checkpoint
class HermesCheckpoint(BaseModel):
    """Resumable checkpoint for graph execution."""
    checkpoint_id: str = Field(default_factory=lambda: f"ckpt_{uuid.uuid4().hex[:8]}")
    request_id: str = Field(description="Associated request ID")
    state: Dict[str, Any] = Field(default_factory=dict, description="Checkpoint state")
    created_at: float = Field(default_factory=lambda: __import__("time").time())
    expires_at: Optional[float] = Field(default=None)