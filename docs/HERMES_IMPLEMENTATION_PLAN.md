# Hermes Integration Implementation Plan

## Overview

**Goal**: Integrate Hermes as a capability/runtime layer into SHAIL, NOT as the core orchestrator.

**Architecture**:
- SHAIL remains the brain (MasterPlanner, LangGraphExecutor, Worker Pool, Jarvis/SuperMemory, Graph Stream Server)
- Hermes becomes the adaptive nervous system

---

## Phase 1: Foundation (Sprint 1-2)

### Sprint 1: Hermes Adapter Layer (High Effort)

**Objective**: Create clean abstraction between LangGraphExecutor ↔ Hermes runtime

**Files to create**:
```
shail/hermes/
├── __init__.py
├── types.py              # All Pydantic models for typed interfaces
├── adapter.py           # Main HermesAdapter class
└── config.py            # Configuration models
```

**Steps**:

1. **Create `types.py`** - Define all type definitions:
   - `HermesRequest`, `HermesResponse`
   - `HermesSkill`, `HermesExecutionTrace`
   - `HermesEvent`, `HermesEventType`
   - `HermesSubagent`, `HermesRetryPolicy`
   - `HermesCheckpoint`, `HermesAdapterConfig`
   - Enums: `ExecutionStatus`, `RetryStrategy`, `ModelProvider`

2. **Create `adapter.py`** - Core adapter:
   - `HermesAdapter` class with typed interfaces
   - `execute()` method for task execution
   - Retry logic with configurable policies
   - Checkpoint creation/resumption
   - Event emission system

3. **Create `config.py`** - Configuration:
   - `HermesSettings` class
   - Environment variable handling
   - Default values

**Integration point**: `shail/orchestration/langgraph_integration.py`

---

### Sprint 2: Persistent Skill Memory (High Effort)

**Objective**: Connect Hermes skills to Jarvis vector memory

**Files to create**:
```
shail/hermes/
├── skill_memory.py      # Skill storage and retrieval
└── skill_store.py       # RAG integration
```

**Steps**:

1. **Create `skill_memory.py`**:
   - `SkillMemory` class
   - Store/retrieve skills with embeddings
   - Search skills via RAG
   - Track skill usage statistics (success_rate, execution_count)
   - Generate skills from execution traces

2. **Create `skill_store.py`**:
   - Integration with Jarvis RAG (`shail/memory/rag.py`)
   - Ingest skills as vector records
   - Semantic search for skill retrieval

**Integration point**: `shail/memory/rag.py` and `shail/memory/store.py`

---

## Phase 2: Core Capabilities (Sprint 3-4)

### Sprint 3: Reflective Learning Loop (High Effort)

**Objective**: Generate optimization summaries from failed/successful runs

**Files to create**:
```
shail/hermes/
├── reflection.py        # Reflection engine
└── optimizer.py         # Prompt/tool strategy optimizer
```

**Steps**:

1. **Create `reflection.py`**:
   - `ReflectionEngine` class
   - Analyze execution traces
   - Generate optimization summaries
   - Store reflections in RAG

2. **Create `optimizer.py`**:
   - Auto-improve prompts based on failures
   - Adjust tool strategies
   - Generate new skill candidates from reflections

**Integration point**: `shail/hermes/adapter.py` (add reflection after execution)

---

### Sprint 4: Subagent Runtime (Medium Effort)

**Objective**: Isolated agents spawned per graph node with retry support

**Files to create**:
```
shail/hermes/
├── subagent_runtime.py  # Subagent lifecycle management
└── subagent_pool.py     # Worker pool for subagents
```

**Steps**:

1. **Create `subagent_runtime.py`**:
   - `SubagentRuntime` class
   - Spawn isolated subagents
   - Retry with configurable policies
   - Checkpoint/resume support
   - Timeout handling

2. **Create `subagent_pool.py`**:
   - `SubagentPool` for managing multiple subagents
   - Resource limits (max concurrent)
   - Status tracking

**Integration point**: `shail/workers/task_worker.py` and `shail/orchestration/graph.py`

---

## Phase 3: Infrastructure (Sprint 5-6)

### Sprint 5: Tool Sandbox Layer (Medium Effort)

**Objective**: Docker/venv isolated tool execution

**Files to create**:
```
shail/hermes/
├── sandbox.py           # Sandbox execution engine
└── sandbox_config.py    # Sandbox configuration
```

**Steps**:

1. **Create `sandbox.py`**:
   - `ToolSandbox` class
   - Docker-based isolation
   - Virtual environment isolation
   - Permission recovery
   - Resource limits (memory, network, timeout)

2. **Create `sandbox_config.py`**:
   - `SandboxConfig` model
   - Environment variable handling

**Integration point**: `shail/tools/` and `shail/safety/permission_manager.py`

---

### Sprint 6: Event Streaming (Medium Effort)

**Objective**: Hermes events → graph_stream_server

**Files to create**:
```
shail/hermes/
├── event_bridge.py      # Bridge to graph stream
└── events.py            # Event definitions
```

**Steps**:

1. **Create `event_bridge.py`**:
   - `HermesEventBridge` class
   - Subscribe to Hermes events
   - Forward to WebSocket server
   - Real-time node_start/node_done/error sync

2. **Create `events.py`**:
   - Event type definitions
   - Event serialization

**Integration point**: `apps/shail/websocket_server.py`

---

## Phase 4: Advanced Features (Sprint 7-8)

### Sprint 7: Memory + RAG Integration (High Effort)

**Objective**: Persist completed graphs into Jarvis

**Files to create**:
```
shail/hermes/
├── memory_integration.py  # Graph persistence
└── retrieval.py            # Semantic retrieval
```

**Steps**:

1. **Create `memory_integration.py`**:
   - Persist completed graph states
   - Store execution traces
   - Index for retrieval

2. **Create `retrieval.py`**:
   - Semantic retrieval for future planning
   - Context loading from memory

**Integration point**: `shail/memory/rag.py` and `shail/orchestration/graph.py`

---

### Sprint 8: Multi-Model Runtime (Medium Effort)

**Objective**: Ollama/Gemma + Claude + OpenAI routing with fallback

**Files to create**:
```
shail/hermes/
├── model_router.py      # Multi-model routing
├── model_clients.py     # Provider clients
└── model_config.py      # Model configuration
```

**Steps**:

1. **Create `model_router.py`**:
   - `ModelRouter` class
   - Task-based model selection
   - Fallback chain on failures
   - Cost/speed/quality strategies

2. **Create `model_clients.py`**:
   - `OllamaClient`, `ClaudeClient`, `OpenAIClient`, `GeminiClient`
   - Unified interface
   - Health checks

3. **Create `model_config.py`**:
   - Route configuration
   - Provider settings

**Integration point**: `shail/llm/` and `shail/orchestration/worker_llms.py`

---

## Implementation Order

| Sprint | Component | Dependencies | Est. Time |
|--------|-----------|--------------|-----------|
| 1 | Adapter Layer | None | 2-3 days |
| 2 | Skill Memory | 1 | 2-3 days |
| 3 | Reflection | 1, 2 | 2-3 days |
| 4 | Subagent Runtime | 1 | 2 days |
| 5 | Sandbox | 1 | 2 days |
| 6 | Event Bridge | 1 | 1-2 days |
| 7 | Memory Integration | 2, 3 | 2-3 days |
| 8 | Multi-Model | 1 | 2 days |

**Total**: ~17-20 days

---

## Key Integration Points

### 1. LangGraphExecutor (`shail/orchestration/langgraph_integration.py`)
```python
# Add Hermes retry logic
from shail.hermes.adapter import get_hermes_adapter

def execute_node(self, node, context):
    adapter = get_hermes_adapter()
    return await adapter.execute(node.task, context)
```

### 2. Worker Pool (`shail/workers/task_worker.py`)
```python
# Add subagent spawning
from shail.hermes.subagent_runtime import get_subagent_runtime

async def process_task(self, task):
    runtime = get_subagent_runtime()
    subagent = await runtime.spawn(task.text, task.context)
```

### 3. WebSocket Server (`apps/shail/websocket_server.py`)
```python
# Add event bridge
from shail.hermes.event_bridge import get_hermes_event_bridge

bridge = get_hermes_event_bridge(ws_manager)
await bridge.start()
```

### 4. Memory (`shail/memory/`)
```python
# Connect skills to RAG
from shail.hermes.skill_memory import get_skill_memory

memory = get_skill_memory()
await memory.store_skill(skill)
```

---

## Production Requirements Checklist

- [x] Typed interfaces (Pydantic in types.py)
- [x] Async-safe execution (async/await throughout)
- [x] Resumable graph checkpoints (HermesCheckpoint)
- [x] Isolated workers (SubagentRuntime)
- [x] Structured logs (logging module)
- [x] WebSocket observability (EventBridge)
- [x] Retry-safe execution (RetryPolicy)
- [x] Tool timeout handling (SandboxConfig)
- [x] Zero hardcoded provider logic (ModelRouter)

---

## DO NOT

- ❌ Replace LangGraph - keep existing `shail/orchestration/graph.py`
- ❌ Replace MasterPlanner - keep `shail/orchestration/master_planner.py`
- ❌ Tightly couple Hermes internals - use adapter pattern only
- ❌ Move orchestration ownership to Hermes - SHAIL remains the brain

---

## Testing Strategy

1. **Unit tests** for each module
2. **Integration tests** for integration points
3. **E2E tests** for full execution flow
4. **Load tests** for subagent runtime

---

## Next Steps

1. Start with **Sprint 1: Adapter Layer**
2. Create base types and adapter
3. Test basic execution flow
4. Proceed to Sprint 2-8 sequentially

Would you like me to begin implementing Sprint 1?