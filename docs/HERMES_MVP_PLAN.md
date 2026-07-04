# Hermes MVP Implementation Plan (Revised)

## MVP Goal

Get Hermes integrated with **all core capabilities** needed for a functional MVP.

---

## Features Included in MVP

| Feature | Status | Implementation |
|---------|--------|----------------|
| Persistent agent memory | ✅ Yes | In-memory skill store |
| Skill generation | ✅ Yes | From execution traces |
| Subagents | ✅ Yes | Isolated agent spawning |
| Autonomous retries | ✅ Yes | Exponential backoff |
| Model-agnostic runtime | ✅ Yes | Abstract client interface |
| Basic reflection | ✅ Yes | Store failure/success info |

---

## Features Skipped (Add Later)

| Feature | Why Skip |
|---------|----------|
| RAG integration | Can add later, use in-memory first |
| Sandbox execution | Not critical for MVP |
| Scheduling | Not needed for MVP |
| Multi-model routing | Ollama-only for MVP |
| Full reflection/optimization | Just store basic info |

---

## Step-by-Step Implementation

### Step 1: Create Hermes Directory

```
shail/hermes/
├── __init__.py
├── types.py           # Core types
├── config.py          # Configuration
├── adapter.py        # Main adapter with retry
├── skill_memory.py   # Skill storage + generation
├── subagent_runtime.py # Subagent spawning
├── model_client.py   # Ollama client + abstraction
└── reflection.py     # Basic reflection (store only)
```

**Time**: 30 min

---

### Step 2: Core Types (`types.py`)

```python
# Enums
class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class RetryStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"

# Request/Response
class HermesRequest(BaseModel):
    request_id: str
    task: str
    context: Dict[str, Any] = {}
    enable_retry: bool = True

class HermesResponse(BaseModel):
    request_id: str
    status: ExecutionStatus
    result: Any = None
    error: str = None
    execution_time_ms: float = 0
    retry_count: int = 0
    skill_used: str = None

# Skill
class HermesSkill(BaseModel):
    skill_id: str
    name: str
    prompt_template: str
    success_rate: float = 1.0
    execution_count: int = 0

# Trace for reflection
class ExecutionTrace(BaseModel):
    trace_id: str
    task: str
    status: ExecutionStatus
    error: str = None
    execution_time_ms: float = 0

# Retry Policy
class RetryPolicy(BaseModel):
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    base_delay_ms: float = 1000
    max_delay_ms: float = 30000
```

**Time**: 1 hour

---

### Step 3: Configuration (`config.py`)

```python
class HermesConfig(BaseModel):
    enabled: bool = True
    ollama_endpoint: str = "http://localhost:11434"
    default_model: str = "llama3.2"
    default_retry_policy: RetryPolicy = RetryPolicy()
```

**Time**: 30 min

---

### Step 4: Model Client Abstraction (`model_client.py`)

```python
class ModelClient(ABC):
    """Abstract base for model clients"""
    @abstractmethod
    async def generate(self, prompt: str, model: str = None) -> str:
        pass

class OllamaClient(ModelClient):
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    async def generate(self, prompt: str, model: str = None) -> str:
        # Call Ollama API
        # Return response text
        pass

# Factory to get client
def get_model_client(provider: str = "ollama") -> ModelClient:
    # Return appropriate client
    return OllamaClient(endpoint)
```

**Time**: 1 hour

---

### Step 5: Skill Memory (`skill_memory.py`)

```python
class SkillMemory:
    def __init__(self):
        self._skills: Dict[str, HermesSkill] = {}
        self._traces: Dict[str, ExecutionTrace] = {}

    def store_skill(self, skill: HermesSkill):
        self._skills[skill.skill_id] = skill

    def get_skill(self, skill_id: str) -> HermesSkill:
        return self._skills.get(skill_id)

    def search_skills(self, query: str) -> List[HermesSkill]:
        """Simple keyword match for MVP"""
        query_lower = query.lower()
        return [s for s in self._skills.values()
                if query_lower in s.name.lower()]

    def generate_skill_from_trace(self, trace: ExecutionTrace) -> HermesSkill:
        """Generate skill from successful trace"""
        if trace.status != ExecutionStatus.COMPLETED:
            return None

        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        return HermesSkill(
            skill_id=skill_id,
            name=f"Skill: {trace.task[:40]}",
            prompt_template=f"Task: {trace.task}\n\nContext: {{context}}",
        )

    def store_trace(self, trace: ExecutionTrace):
        self._traces[trace.trace_id] = trace

    def get_traces(self, status: ExecutionStatus = None) -> List[ExecutionTrace]:
        if status:
            return [t for t in self._traces.values() if t.status == status]
        return list(self._traces.values())
```

**Time**: 1.5 hours

---

### Step 6: Basic Reflection (`reflection.py`)

```python
class Reflection:
    """Store failure/success info for later analysis"""

    def __init__(self, skill_memory: SkillMemory):
        self.skill_memory = skill_memory

    def reflect(self, trace: ExecutionTrace):
        """Analyze trace and potentially generate skill"""
        # Store trace
        self.skill_memory.store_trace(trace)

        # If successful and slow, generate skill
        if trace.status == ExecutionStatus.COMPLETED:
            if trace.execution_time_ms > 2000:  # 2+ seconds
                skill = self.skill_memory.generate_skill_from_trace(trace)
                if skill:
                    self.skill_memory.store_skill(skill)

        # If failed, could add to retry logic later
        # For MVP, just store the failure info
        return {
            "trace_id": trace.trace_id,
            "status": trace.status,
            "generated_skill": trace.status == ExecutionStatus.COMPLETED
        }
```

**Time**: 1 hour

---

### Step 7: Core Adapter with Retry (`adapter.py`)

```python
class HermesAdapter:
    def __init__(self, config: HermesConfig = None):
        self.config = config or HermesConfig()
        self.model_client = get_model_client()
        self.skill_memory = SkillMemory()
        self.reflection = Reflection(self.skill_memory)

    async def execute(
        self,
        task: str,
        context: Dict[str, Any] = None,
        enable_retry: bool = True,
    ) -> HermesResponse:
        request_id = str(uuid.uuid4())
        context = context or {}

        # Find applicable skill
        skills = self.skill_memory.search_skills(task)
        skill = skills[0] if skills else None

        # Execute with retry
        if enable_retry:
            return await self._execute_with_retry(
                request_id, task, context, skill
            )
        else:
            return await self._execute_once(
                request_id, task, context, skill
            )

    async def _execute_with_retry(
        self, request_id, task, context, skill
    ) -> HermesResponse:
        policy = self.config.default_retry_policy
        retry_count = 0

        while retry_count <= policy.max_retries:
            try:
                result = await self._execute_once(
                    request_id, task, context, skill
                )
                result.retry_count = retry_count
                return result

            except Exception as e:
                retry_count += 1
                if retry_count <= policy.max_retries:
                    delay = self._calculate_delay(policy, retry_count)
                    await asyncio.sleep(delay / 1000)
                else:
                    return HermesResponse(
                        request_id=request_id,
                        status=ExecutionStatus.FAILED,
                        error=str(e),
                        retry_count=retry_count,
                    )

    def _calculate_delay(self, policy: RetryPolicy, attempt: int) -> float:
        if policy.strategy == RetryStrategy.EXPONENTIAL:
            return min(
                policy.base_delay_ms * (2 ** (attempt - 1)),
                policy.max_delay_ms
            )
        elif policy.strategy == RetryStrategy.LINEAR:
            return min(policy.base_delay_ms * attempt, policy.max_delay_ms)
        else:  # FIXED
            return policy.base_delay_ms

    async def _execute_once(
        self, request_id, task, context, skill
    ) -> HermesResponse:
        start_time = time.time()

        # Build prompt
        if skill:
            prompt = skill.prompt_template.format(task=task, **context)
        else:
            prompt = f"Task: {task}\n\nContext: {context}"

        # Call model
        response = await self.model_client.generate(prompt)

        execution_time = (time.time() - start_time) * 1000

        # Store trace for reflection
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            task=task,
            status=ExecutionStatus.COMPLETED,
            execution_time_ms=execution_time,
        )
        self.reflection.reflect(trace)

        return HermesResponse(
            request_id=request_id,
            status=ExecutionStatus.COMPLETED,
            result={"response": response},
            execution_time_ms=execution_time,
            skill_used=skill.skill_id if skill else None,
        )
```

**Time**: 2.5 hours

---

### Step 8: Subagent Runtime (`subagent_runtime.py`)

```python
class SubagentRuntime:
    def __init__(self, adapter: HermesAdapter, max_concurrent: int = 10):
        self.adapter = adapter
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._subagents: Dict[str, dict] = {}

    async def spawn(
        self,
        task: str,
        context: Dict[str, Any] = None,
        parent_id: str = None,
    ) -> str:
        subagent_id = f"sub_{uuid.uuid4().hex[:8]}"

        self._subagents[subagent_id] = {
            "task": task,
            "context": context or {},
            "parent_id": parent_id,
            "status": ExecutionStatus.PENDING,
        }

        # Execute in background
        asyncio.create_task(self._execute(subagent_id, task, context))

        return subagent_id

    async def _execute(self, subagent_id, task, context):
        async with self._semaphore:
            self._subagents[subagent_id]["status"] = ExecutionStatus.RUNNING

            result = await self.adapter.execute(task, context)

            self._subagents[subagent_id]["status"] = (
                ExecutionStatus.COMPLETED if result.status == ExecutionStatus.COMPLETED
                else ExecutionStatus.FAILED
            )
            self._subagents[subagent_id]["result"] = result

    async def get_status(self, subagent_id: str) -> dict:
        return self._subagents.get(subagent_id, {})
```

**Time**: 1.5 hours

---

### Step 9: Integration Test

```python
# Test full flow
async def test_hermes_mvp():
    # Create adapter
    adapter = HermesAdapter()

    # Test 1: Basic execution
    result = await adapter.execute("What is Python?")
    print(f"Result: {result.result}")

    # Test 2: With skill
    skill = HermesSkill(
        skill_id="test_skill",
        name="Code Analysis",
        prompt_template="Analyze: {task}\n\nContext: {path}"
    )
    adapter.skill_memory.store_skill(skill)
    result = await adapter.execute("Analyze this code", {"path": "/src"})
    print(f"With skill: {result.skill_used}")

    # Test 3: Retry (should fail 3 times then succeed)
    # (Requires mock to test retry)

    # Test 4: Subagent
    runtime = SubagentRuntime(adapter)
    subagent_id = await runtime.spawn("Calculate 2+2")
    await asyncio.sleep(1)
    status = await runtime.get_status(subagent_id)
    print(f"Subagent status: {status}")

# Run test
asyncio.run(test_hermes_mvp())
```

**Time**: 1 hour

---

## MVP Summary

| Step | Component | Time |
|------|-----------|------|
| 1 | Directory structure | 30 min |
| 2 | Core types | 1 hour |
| 3 | Configuration | 30 min |
| 4 | Model client abstraction | 1 hour |
| 5 | Skill memory | 1.5 hours |
| 6 | Basic reflection | 1 hour |
| 7 | Core adapter + retry | 2.5 hours |
| 8 | Subagent runtime | 1.5 hours |
| 9 | Integration test | 1 hour |

**Total MVP**: ~10.5 hours (1-2 days)

---

## What's Included

✅ Persistent agent memory (in-memory)
✅ Skill generation (from traces)
✅ Subagents (isolated spawning)
✅ Autonomous retries (exponential backoff)
✅ Model-agnostic runtime (abstract client)
✅ Basic reflection (store failure/success)

---

## Ready to Start?

Let me know and I'll begin implementing **Step 1** - creating the directory structure and all files.