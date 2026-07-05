# Hermes-SHAIL Integration Guide

## Overview

Hermes is integrated as a **capability layer** into SHAIL, NOT as a replacement for the core orchestrator.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SHAIL (The Brain)                       │
├─────────────────────────────────────────────────────────────┤
│  MasterPlanner  │  LangGraphExecutor  │  Worker Pool      │
│  Jarvis/SuperMemory  │  Graph Stream Server                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               Hermes (Adaptive Nervous System)           │
├─────────────────────────────────────────────────────────────┤
│  HermesSHAILIntegration  │  HermesAdapter  │  SubagentRuntime │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### 1. Simple Task Execution with Retry

```python
from shail.hermes.integration import execute_with_hermes_retry

# Execute a task with automatic retry on failure
result = await execute_with_hermes_retry(
    task="Analyze the codebase",
    context={"path": "/project"}
)

print(f"Success: {result['success']}")
print(f"Result: {result['result']}")
print(f"Retries: {result['retry_count']}")
```

### 2. Subagent Spawning (Parallel Execution)

```python
from shail.hermes.integration import spawn_hermes_subagent

# Spawn a subagent for background execution
subagent_id = await spawn_hermes_subagent(
    task="Process large dataset",
    context={"file": "data.csv"}
)
print(f"Subagent: {subagent_id}")
```

### 3. Full Integration Instance

```python
from shail.hermes.integration import get_hermes_sail_integration

integration = get_hermes_sail_integration()

# Execute with Hermes capabilities
result = await integration.execute_task_with_hermes(
    task_text="Complex analysis",
    context={"data": dataset},
    use_subagent=True  # Spawn as subagent
)

# Get statistics
stats = integration.get_hermes_stats()
print(f"Skills: {stats['memory']['total_skills']}")
print(f"Subagents completed: {stats['subagents']['completed']}")
```

### 4. Integration with Worker Pool

```python
# In task_worker.py or similar
from shail.hermes.integration import get_hermes_sail_integration

integration = get_hermes_sail_integration()

# Instead of direct execution
async def process_task(task_text, context):
    # Use Hermes with retry and fallback
    result = await integration.execute_task_with_hermes(
        task_text,
        context,
        use_subagent=False
    )
    return result
```

### 5. Parallel Task Execution

```python
from shail.hermes.integration import get_hermes_sail_integration

integration = get_hermes_sail_integration()

tasks = [
    "Analyze file A",
    "Analyze file B",
    "Analyze file C",
]

# Execute all in parallel using subagents
results = await integration.execute_parallel_tasks(tasks)
```

## Integration Points

### Worker Pool (`shail/workers/task_worker.py`)

Replace direct execution with Hermes:

```python
# Before
result = self.router.route(request)

# After
from shail.hermes.integration import get_hermes_sail_integration
integration = get_hermes_sail_integration()
result = await integration.execute_task_with_hermes(request.text)
```

### LangGraph Nodes (`shail/orchestration/nodes/`)

Add retry capability to nodes:

```python
from shail.hermes.integration import get_hermes_sail_integration

integration = get_hermes_sail_integration()

async def analysis_node(state):
    result = await integration.execute_with_retry(
        node_name="analysis",
        task=state["task"],
        context=state
    )
    return {"analysis": result}
```

### Multi-Model Fallback

```python
from shail.hermes.multi_model import get_multi_model_runtime

runtime = get_multi_model_runtime()

# Automatically tries Ollama first, falls back to Claude
result = await runtime.generate("Your prompt here")
```

## Features Available

| Feature | Description |
|---------|-------------|
| **Retry Logic** | Automatic retry with exponential backoff |
| **Skill Memory** | Persistent storage of generated skills |
| **Subagents** | Parallel execution of tasks |
| **Multi-Model** | Ollama + Claude fallback |
| **Reflection** | Analyzes failures and generates improvements |
| **Statistics** | Track execution metrics |

## Configuration

Environment variables:

```bash
# Ollama
OLLAMA_ENDPOINT=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Claude (optional)
ANTHROPIC_API_KEY=sk-...

# Hermes settings
HERMES_ENABLED=true
HERMES_USE_SUBAGENTS=true
HERMES_USE_FALLBACK=true
```

## Files

```
shail/hermes/
├── __init__.py           # Exports
├── types.py              # Type definitions
├── config.py            # Configuration
├── model_client.py      # Ollama client
├── multi_model.py        # Multi-model (Ollama + Claude)
├── adapter.py           # Core execution adapter
├── skill_memory.py      # In-memory skill storage
├── reflection.py         # Basic reflection
├── subagent_runtime.py   # Subagent spawning
├── persistent_memory.py # File-based JSON storage
├── integration.py       # ← SHAIL integration
└── storage/             # Persisted data (auto-created)
    ├── skills.json
    └── traces.json
```

## Next Steps

1. **Test the integration** with real tasks
2. **Connect to Worker Pool** by modifying `task_worker.py`
3. **Add LangGraph nodes** using `execute_with_retry`
4. **Monitor statistics** via `get_hermes_stats()`

## DO NOT

- ❌ Replace LangGraphExecutor
- ❌ Replace MasterPlanner
- ❌ Make Hermes the orchestrator
- ❌ Tightly couple Hermes internals into SHAIL core