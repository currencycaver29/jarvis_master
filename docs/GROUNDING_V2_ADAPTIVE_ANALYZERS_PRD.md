# Grounding V2 + Adaptive Domain Analyzers PRD

## Document Status

- Status: Draft for implementation
- Owner: SHAIL core platform
- Intended audience: product, architecture, backend, native, memory/RAG, UI, and future coding agents implementing this system
- Scope: Grounding retention, session summarization, long-term retrieval, anomaly detection, and adaptive software-specific analyzers

## 1. Executive Summary

SHAIL's current grounding system is useful for short-horizon context recovery, but it is still limited to a small in-memory timeline and heuristic search over recent accessibility events. That is enough for "what just happened?" in the last few minutes, but not enough for:

- recovering events from 2-3 hours ago
- retaining meaningful context across a full workday
- reliably detecting anomalies in complex software such as Gazebo, CAD tools, MATLAB, Simulink, IDEs, or simulation-heavy environments
- deciding when generic grounding is enough and when a domain-specific analyzer is required

This PRD defines a new architecture called **Grounding V2** plus **Adaptive Domain Analyzers**.

Grounding V2 upgrades SHAIL from a short-term "recent event searcher" into a layered perception and memory system with:

- configurable retention
- separate event and frame retention policies
- session summaries and anomaly-tagged episodes
- long-term searchable grounding memory
- improved retrieval over timeline summaries, not just raw events
- software-aware evidence fusion across UI, logs, frames, and structured telemetry

Adaptive Domain Analyzers extend Grounding V2 only when generic grounding is insufficient for a specific software environment. SHAIL should not create or require a custom analyzer for every plugin. Instead, SHAIL should:

1. attempt generic grounding first
2. measure confidence and anomaly-detection quality
3. determine whether the software complexity requires a domain extension
4. explain the need to the user
5. request consent before enabling deeper software-specific analyzers

This PRD is written to be implementation-driving. It defines product behavior, feature scope, user flows, data flows, architecture, storage strategy, tech map, rollout plan, and a repo-level implementation map.

## 2. Problem Statement

### Current pain points

SHAIL's current grounding stack has four structural limitations:

1. **Short retention horizon**
   - The buffer defaults to 300 seconds in [`shail/perception/buffer.py`](/Users/reyhan/jarvis_master/shail/perception/buffer.py#L29)
   - This is too short for debugging multi-step workflows, simulations, long-running tasks, or delayed failures

2. **Raw-data-heavy design**
   - Accessibility events and thumbnails are stored as recent rolling data only
   - There is no robust session compression layer between "just happened" and "long-term memory"

3. **Weak semantic retrieval**
   - `query_semantic` is mostly heuristic keyword matching over event text
   - It performs poorly on abstract queries such as:
     - "the robot started drifting after I changed controller gains"
     - "the sim became unstable after contact"
     - "the CAD model broke after constraint edits"

4. **No adaptive domain intelligence**
   - Generic grounding can catch obvious textual failures
   - It cannot reliably diagnose software-specific anomalies in complex environments without richer signals

### Why this matters

Without stronger grounding, SHAIL will:

- forget important context too quickly
- ask the user to repeat too much
- misidentify the wrong moment in the timeline
- struggle with professional workflows involving simulations, robotics, design tools, or complex apps
- fail to detect important anomalies that do not appear as simple UI text

## 3. Vision

Build a grounding system that allows SHAIL to answer:

- What happened recently?
- What happened two hours ago in this software session?
- What is the most likely failure point in the user's workflow?
- Is this software state abnormal?
- Is generic grounding sufficient, or do we need a software-specific analyzer?

The result should feel like SHAIL has:

- short-term sensory memory
- session-level understanding
- long-term searchable work memory
- adaptive expertise for difficult software only when needed

## 4. Goals

### Product goals

1. Increase grounding retention from 5 minutes to configurable multi-hour and full-day workflows
2. Preserve useful evidence without storing unlimited raw screenshots
3. Improve event recovery quality for ambiguous historical queries
4. Detect anomalies in a broader range of software using layered evidence
5. Introduce software-specific analyzers only when generic grounding is insufficient
6. Keep the user in control with transparent consent for deeper analyzers

### Technical goals

1. Separate event retention, frame retention, and query horizon
2. Add session summarization and anomaly-tagging pipelines
3. Store searchable timeline episodes in RAG/vector memory
4. Upgrade retrieval to operate on summaries, chunks, and tags
5. Support UI + logs + frames + telemetry correlation
6. Add analyzer registration and capability-threshold logic

## 5. Non-Goals

The first version of this project is not intended to:

- build a fully autonomous analyzer for every plugin by default
- retain full-resolution video for entire day-long sessions
- replace domain-native observability tooling
- silently ingest deep software-specific telemetry without user consent
- infer all anomalies visually without logs or software signals

## 6. Users and Personas

### Persona A: General SHAIL user

This user wants SHAIL to remember what happened earlier and help recover context without repeating everything.

Needs:
- "What error did I see earlier?"
- "Which app showed the warning?"
- "What changed before this issue?"

### Persona B: Simulation and robotics user

This user works in Gazebo, ROS, simulators, or robotics tooling and needs help understanding failures that unfold over time.

Needs:
- detect controller issues
- detect instability, drift, or spawn failures
- connect simulator UI evidence with console logs and runtime state

### Persona C: Professional workflow user

This user works in CAD, IDEs, browser workflows, MATLAB, or similar environments and wants SHAIL to recover multi-step context.

Needs:
- trace failures across many screens and windows
- detect workflow regressions
- understand the software context behind an anomaly

### Persona D: Power user / privacy-sensitive user

This user wants value from grounding but needs control over:

- how long data is retained
- what kind of data is stored
- whether deeper analyzers can inspect software-specific logs or telemetry

## 7. User Stories

### Retention stories

- As a user, I want SHAIL to recover what happened 2-3 hours ago so I do not need to reproduce a problem immediately.
- As a user, I want recent raw context preserved for immediate debugging, but older data compressed into useful summaries.
- As a user, I want to configure how long grounding data is retained.

### Retrieval stories

- As a user, I want SHAIL to answer "what happened before the crash?" using session-level understanding.
- As a user, I want grounding to understand queries that do not contain exact UI text.
- As a user, I want SHAIL to use app, logs, screenshots, and timing together when finding the relevant episode.

### Anomaly-detection stories

- As a user, I want SHAIL to detect obvious failure signals such as error banners, warnings, exceptions, and failed actions.
- As a user of complex software, I want SHAIL to detect state-level anomalies when generic UI text is insufficient.
- As a user, I want SHAIL to explain when a domain-specific analyzer would improve accuracy and ask for consent first.

## 8. Current State Summary

### Existing components

- `GroundingBuffer` in [`shail/perception/buffer.py`](/Users/reyhan/jarvis_master/shail/perception/buffer.py)
- `GroundingAgent` in [`shail/perception/grounding_agent.py`](/Users/reyhan/jarvis_master/shail/perception/grounding_agent.py)
- `VisionObservationAgent` in [`shail/perception/vision_agent.py`](/Users/reyhan/jarvis_master/shail/perception/vision_agent.py)
- native capture and accessibility bridge in [`shail/perception/integration.py`](/Users/reyhan/jarvis_master/shail/perception/integration.py) and [`shail/perception/native_bridge.py`](/Users/reyhan/jarvis_master/shail/perception/native_bridge.py)
- long-term retrieval primitives in [`shail/memory/rag.py`](/Users/reyhan/jarvis_master/shail/memory/rag.py)

### Existing strengths

- live access to accessibility events and screen frames
- short-term temporal and keyword retrieval
- simple grounding confidence scoring
- escalation to user guidance when grounding confidence is low

### Existing gaps

- hardcoded short retention
- no event retention policy separate from frame retention
- no episode summarization
- no analyzer capability model
- no software-specific anomaly framework
- metrics declared but not fully wired

## 9. Product Requirements

## 9.1 Configurable Retention

Grounding V2 must support separate policies for:

- event retention
- frame retention
- query horizon
- summarization cutover
- long-term episode retention

### Required config fields

- `GROUNDING_EVENT_RETENTION_SECONDS`
- `GROUNDING_FRAME_RETENTION_SECONDS`
- `GROUNDING_QUERY_WINDOW_SECONDS`
- `GROUNDING_SUMMARY_CUTOFF_SECONDS`
- `GROUNDING_FRAME_CAPTURE_INTERVAL_SECONDS`
- `GROUNDING_FRAME_KEYFRAME_ONLY`
- `GROUNDING_MAX_FRAMES_PER_SESSION`
- `GROUNDING_EPISODE_RETENTION_DAYS`

### Behavior

- raw events can live longer than raw frames
- query horizon should not require every raw frame to still exist
- episodes should remain searchable after raw data is pruned

## 9.2 Frame Retention Optimization

Grounding V2 must avoid storing all thumbnails for long durations.

### Required behavior

- downsample frame capture over time
- keep keyframes when significant changes occur
- deduplicate visually identical or nearly identical frames
- keep frame hash + metadata when image files are deleted
- allow frame storage policy to differ by software class

### Expected result

SHAIL can preserve useful visual evidence over hours without retaining wasteful, redundant image history.

## 9.3 Session and Episode Summarization

Grounding V2 must create timeline summaries from older raw data.

### Definition

A **session episode** is a grouped narrative chunk representing a meaningful block of user activity, for example:

- "Gazebo session from 14:05 to 14:18 with controller warnings and unstable motion"
- "VS Code editing session for project X with repeated test failures"
- "Browser workflow where login failed after form submission"

### Required behavior

- group events by app, window, time proximity, and task context
- generate narrative summaries every few minutes
- attach anomaly tags
- store summary records into long-term memory / RAG
- keep references back to:
  - time range
  - app name
  - window title
  - event count
  - anomaly count
  - frame references
  - software domain

## 9.4 Improved Retrieval

Grounding V2 retrieval must search across:

- recent raw events
- recent frame metadata
- session summaries
- long-term episode memory
- software-specific anomaly tags

### Retrieval modes

1. **Immediate lookup**
   - last 5-30 minutes
   - prioritize raw events and recent frames

2. **Session lookup**
   - 30 minutes to several hours
   - prioritize summarized episodes

3. **Historical lookup**
   - same day or beyond
   - prioritize long-term indexed summaries and tagged episodes

### Retrieval quality targets

Queries such as:

- "the sim became unstable after contact"
- "the warning in Gazebo around lunch"
- "the test failure after I changed controller gains"
- "the browser flow where checkout broke"

should retrieve evidence using app, timing, anomaly tags, and summary semantics rather than exact keyword matching alone.

## 9.5 Adaptive Domain Analyzers

Grounding V2 must support optional analyzers for complex software only when generic grounding is insufficient.

### Key principle

Domain analyzers are extensions, not replacements.

The system flow must always be:

1. generic grounding first
2. confidence evaluation
3. analyzer eligibility check
4. user-facing explanation
5. consented analyzer enablement
6. analyzer-augmented grounding and anomaly detection

### Examples of candidate domains

- Gazebo / robotics simulation
- IDE / code debugging
- browser workflow and form automation
- CAD / engineering software
- MATLAB / Simulink

### Examples of non-candidates

- simple note-taking apps
- basic file browsing
- simple terminal usage where generic grounding is already sufficient

## 9.6 Consent and Transparency

SHAIL must not silently enable deep software-specific analyzers that require extra data collection or software-specific introspection.

### Required user communication

When SHAIL proposes a deeper analyzer, it must explain:

- why generic grounding is not enough
- what extra signals are needed
- what user value this enables
- what data is stored and for how long
- whether the analyzer can be turned off later

### Example message

"Generic grounding can recover screenshots and accessibility events, but Gazebo failures often depend on simulator logs, ROS topics, and state changes that do not appear clearly in the UI. Enabling a Gazebo analyzer would let SHAIL detect instability, spawn failures, controller errors, and simulation regressions more accurately. Do you want to enable this analyzer for Gazebo sessions?"

## 10. Feature Set

## 10.1 Grounding V2 Core Features

### Feature: retention policy engine

Purpose:
- centralize time and storage behavior for grounding data

Capabilities:
- per-data-type retention
- per-domain policy overrides
- policy introspection for UI/debugging

### Feature: frame thinning and keyframe retention

Purpose:
- keep visual evidence useful but cheap

Capabilities:
- hash-based duplicate suppression
- temporal downsampling
- keyframe marking on detected change
- metadata-only retention after image deletion

### Feature: session episode builder

Purpose:
- compress noisy event streams into narrative units

Capabilities:
- event clustering
- app/window grouping
- anomaly tag generation
- long-term episode storage

### Feature: long-term grounding memory

Purpose:
- allow retrieval beyond hot-memory window

Capabilities:
- vector/RAG-backed episode indexing
- metadata filtering by app, time, task, anomaly type
- recall by semantic query

### Feature: multi-layer retrieval router

Purpose:
- query the right storage layer for the user's request

Capabilities:
- recent raw lookup
- session summary retrieval
- historical search
- evidence fusion and reranking

### Feature: anomaly tagging

Purpose:
- attach reusable labels to suspicious events and episodes

Examples:
- `error_text`
- `warning_banner`
- `crash_signal`
- `physics_instability`
- `spawn_failure`
- `constraint_conflict`
- `network_failure`

### Feature: analyzer capability resolver

Purpose:
- determine whether generic grounding is sufficient

Capabilities:
- software-domain identification
- confidence threshold checks
- analyzer availability lookup
- extension recommendation

## 10.2 Adaptive Domain Analyzer Features

### Feature: analyzer registry

Purpose:
- register available domain analyzers in a standard way

Each analyzer must declare:
- analyzer id
- supported software domains
- required signals
- optional signals
- risk/consent level
- anomaly types handled
- confidence calibration strategy

### Feature: analyzer lifecycle

Purpose:
- enable analyzers during plugin install or after repeated failures

Phases:
- suggested
- awaiting consent
- enabled
- disabled
- deprecated

### Feature: analyzer evidence fusion

Purpose:
- combine generic grounding with software-native signals

Examples:
- Gazebo: UI + simulator logs + ROS topics + frame sequences
- IDE: editor diagnostics + test output + terminal logs + active file context
- browser: DOM state + accessibility + screenshot + network/log traces

## 11. User Flows

## 11.1 Flow A: recover a recent issue

User says:
"What was the error I saw in Terminal a few minutes ago?"

Flow:
1. planner marks request as context-heavy
2. grounding retrieval router first checks hot memory
3. recent events and frames are searched
4. best segment is selected
5. vision/log evidence are cross-checked
6. result is returned with confidence and evidence summary

Success criteria:
- answer retrieved without asking user to repeat context

## 11.2 Flow B: recover a 2-hour-old issue

User says:
"What warning showed up in Gazebo earlier this afternoon?"

Flow:
1. raw buffer may no longer contain the direct event
2. retrieval router checks summarized episodes
3. long-term grounding memory is queried by app + time + semantics
4. matching session episode is found
5. evidence references are surfaced
6. if confidence is enough, return grounded narrative
7. if confidence is weak, ask a clarifying question

Success criteria:
- SHAIL retrieves the correct session summary even after raw events have aged out

## 11.3 Flow C: detect anomaly in complex software using generic grounding

User says:
"Why did the browser checkout flow fail?"

Flow:
1. generic grounding retrieves relevant browser session episode
2. anomaly tags show repeated form failures and warning banners
3. cross-check layer compares UI, logs, and task history
4. if generic grounding reaches target confidence, no domain analyzer is needed

Success criteria:
- no unnecessary analyzer installation or domain extension

## 11.4 Flow D: SHAIL proposes a domain analyzer

User says:
"Why did the robot drift after I changed controller gains?"

Flow:
1. generic grounding attempts recovery
2. confidence is low or evidence is incomplete
3. software domain is identified as Gazebo / robotics simulation
4. capability resolver determines a Gazebo analyzer would materially improve detection
5. SHAIL explains why generic grounding is insufficient
6. user approves or declines analyzer enablement
7. if approved, analyzer is enabled and future grounding includes simulator-aware evidence

Success criteria:
- analyzer is added only when justified and consented

## 11.5 Flow E: plugin install with analyzer suggestion

User installs or connects a software plugin.

Flow:
1. plugin registers supported software domain and complexity metadata
2. SHAIL evaluates whether Grounding V2 is probably sufficient
3. if likely sufficient, no analyzer prompt
4. if likely insufficient, show optional analyzer recommendation
5. user can enable now, later, or never

Success criteria:
- no analyzer bloat
- user stays informed and in control

## 12. Functional Requirements

### FR-1
System must support separate retention values for:
- events
- frames
- retrieval window
- summaries
- long-term episodes

### FR-2
System must support aging frames out while preserving frame metadata and hashes.

### FR-3
System must build app/window/time-grouped session episodes at scheduled intervals.

### FR-4
System must persist summarized episodes into long-term searchable memory.

### FR-5
System must route retrieval queries across hot, session, and historical layers.

### FR-6
System must score grounding results using multi-source evidence.

### FR-7
System must expose confidence and rationale for retrieved segments or episodes.

### FR-8
System must identify software domain for the current session when possible.

### FR-9
System must determine whether a domain analyzer is recommended based on confidence, software complexity, and missing evidence types.

### FR-10
System must request user consent before enabling a domain analyzer that adds software-specific collection or introspection.

## 13. Non-Functional Requirements

### Performance

- hot-memory lookup should stay near interactive speed
- summarization jobs must not block live grounding
- analyzer extension should not degrade default responsiveness for simple queries

### Privacy

- retention and analyzer scope must be configurable
- older visual artifacts may be replaced by metadata-only records
- PII masking must continue for accessibility text

### Reliability

- grounding should degrade gracefully if capture or accessibility streams disconnect
- historical retrieval should still work when raw buffer is gone

### Observability

- metrics must be fully wired for attempts, confidence, summary generation, analyzer use, and user-guidance escalations

## 14. Architecture Overview

## 14.1 Target architecture layers

### Layer 1: Short-term layer

Data:
- recent raw accessibility events
- recent thumbnails
- recent console/log lines

Purpose:
- immediate recovery of "what just happened?"

Storage:
- memory-backed rolling buffers
- short-lived local file artifacts for retained frames

### Layer 2: Session layer

Data:
- grouped episodes by app/window/time
- summaries every few minutes
- anomaly tags
- selected keyframes or frame metadata

Purpose:
- recover workflows across hours
- provide better semantic grounding than raw event matching

Storage:
- SQLite + local serialized summaries, or equivalent episode store

### Layer 3: Long-term layer

Data:
- vector-indexed episodes
- anomaly-tagged summaries
- software/time/task metadata

Purpose:
- semantic retrieval across same-day and historical sessions

Storage:
- existing RAG/vector layer in [`shail/memory/rag.py`](/Users/reyhan/jarvis_master/shail/memory/rag.py)
- vector backend: pgvector or Chroma per [`apps/shail/settings.py`](/Users/reyhan/jarvis_master/apps/shail/settings.py#L33)

### Layer 4: Domain analyzers

Data:
- software-specific evidence
- analyzer-specific anomaly logic

Purpose:
- improve detection in complex software where generic grounding is not enough

### Layer 5: Cross-check layer

Data:
- UI events
- logs
- frames
- tool/plugin state
- analyzer outputs

Purpose:
- merge multiple evidence channels into one confidence-scored explanation

## 14.2 Core runtime flow

1. native services stream accessibility and capture data
2. Perception connector ingests and normalizes signals
3. hot grounding buffers retain recent events and frames
4. summarization worker compresses older raw signals into episodes
5. episode records are persisted and indexed in long-term memory
6. user query arrives
7. retrieval router chooses hot/session/historical search path
8. evidence is reranked and anomaly-tagged
9. if generic confidence is sufficient, result is returned
10. if generic confidence is insufficient and software complexity is high, analyzer recommendation path is triggered

## 15. Detailed Component Design

## 15.1 Retention Policy Manager

New component:
- `shail/perception/retention_policy.py`

Responsibilities:
- centralize retention values
- define per-domain overrides
- compute data aging thresholds
- expose effective policy for UI/debugging

Suggested config object:

```python
class GroundingRetentionPolicy:
    event_retention_seconds: int
    frame_retention_seconds: int
    query_window_seconds: int
    summary_cutoff_seconds: int
    episode_retention_days: int
    frame_capture_interval_seconds: float
    keep_metadata_after_frame_delete: bool
```

## 15.2 Grounding Buffer V2

Existing base:
- [`shail/perception/buffer.py`](/Users/reyhan/jarvis_master/shail/perception/buffer.py)

Required upgrades:
- separate event and frame retention
- support frame metadata retention after image deletion
- support console/log line ingestion
- support event grouping markers for summarization
- support querying across:
  - raw events
  - frame metadata
  - recent session summaries

## 15.3 Episode Builder

New component:
- `shail/perception/episode_builder.py`

Responsibilities:
- cluster events into episodes by time proximity, app, window, and task context
- build episode summaries
- extract anomaly tags
- attach frame references
- emit long-term memory records

Suggested output model:

```python
class SessionEpisode(BaseModel):
    episode_id: str
    software_domain: str
    app_name: str
    window_title: Optional[str]
    start_time: float
    end_time: float
    summary: str
    anomaly_tags: list[str]
    event_count: int
    frame_refs: list[str]
    log_refs: list[str]
    metadata: dict[str, Any]
```

## 15.4 Historical Grounding Store

New component:
- `shail/perception/episode_store.py`

Responsibilities:
- persist session episodes
- support time and metadata filtering
- support export into RAG ingestion records
- support cleanup by retention policy

## 15.5 Retrieval Router

New component:
- `shail/perception/retrieval_router.py`

Responsibilities:
- choose hot/session/historical query path
- merge candidates from multiple stores
- rerank using:
  - query semantics
  - app context
  - anomaly tags
  - temporal hints
  - task context

## 15.6 Domain Analyzer Framework

New components:
- `shail/perception/analyzers/base.py`
- `shail/perception/analyzers/registry.py`
- `shail/perception/analyzers/capability_resolver.py`
- per-domain analyzer modules under `shail/perception/analyzers/`

Analyzer contract:

```python
class DomainAnalyzer:
    analyzer_id: str
    supported_domains: list[str]
    required_signals: list[str]
    optional_signals: list[str]
    consent_level: str

    def can_handle(self, context: AnalyzerContext) -> bool: ...
    def analyze(self, context: AnalyzerContext) -> AnalyzerResult: ...
    def explain_value(self) -> str: ...
```

## 15.7 Consent Flow

New components:
- `shail/safety/domain_analyzer_permissions.py`
- UI prompts under app layer

Responsibilities:
- store analyzer consent decisions
- distinguish one-time vs persistent enablement
- explain additional data use
- allow revoke/disable later

## 16. Domain Analyzer Strategy

## 16.1 Generic grounding sufficiency model

For each software/plugin, track:

- `generic_grounding_sufficient`
- `needs_log_ingestion`
- `needs_state_adapter`
- `needs_visual_anomaly_model`
- `needs_cross_process_correlation`

Decision logic:

- if generic grounding consistently reaches confidence target, do not propose analyzer
- if confidence is repeatedly low for same software domain, evaluate analyzer recommendation

## 16.2 Gazebo analyzer example

Signals:
- Gazebo UI events
- simulator console logs
- ROS topic health
- spawn/load failures
- frame-level motion instability markers

Anomalies:
- plugin load failure
- world load failure
- spawn failure
- physics instability
- controller instability
- missing topic or disconnected node
- repeated reset/crash loop

Output:
- anomaly type
- evidence set
- confidence
- suggested next action

## 16.3 IDE/code analyzer example

Signals:
- editor diagnostics
- active file and test context
- terminal output
- debugger state
- recent code-change summaries

Anomalies:
- test regression
- import error
- environment mismatch
- syntax error
- repeated failure after code edits

## 17. Tech Map / Stack

## 17.1 Existing stack

### Core backend
- Python
- FastAPI
- Pydantic
- asyncio

### Native integration
- Swift on macOS
- native accessibility and screen capture services
- WebSocket bridge

### UI
- React + Vite dashboard in `apps/shail-ui`
- SwiftUI macOS client in `apps/mac/ShailUI`

### Memory and storage
- SQLite for task and permission persistence
- Redis for async task queue
- RAG/vector memory through pgvector or Chroma
- Gemini embeddings per settings

### LLMs
- Gemini
- optional Kimi K2
- optional OpenAI worker

## 17.2 New stack additions for this initiative

### Must-have additions
- retention policy module
- episode builder
- episode store
- retrieval router
- analyzer registry
- analyzer consent manager

### Likely storage additions
- SQLite tables or a dedicated local store for session episodes
- RAG namespaces for grounding episodes and anomaly summaries

### Optional future additions
- approximate image similarity / perceptual hash library
- lightweight log-ingestion adapters per domain
- temporal anomaly scoring module

## 18. Data Model

## 18.1 Raw event model

Use existing `AccessibilityEvent` plus optional new fields:
- `session_id`
- `software_domain`
- `task_id`

## 18.2 Raw frame metadata model

New or extended frame metadata:
- `frame_id`
- `ts`
- `path`
- `hash`
- `phash`
- `width`
- `height`
- `retained_image`
- `change_score`
- `software_domain`

## 18.3 Session episode model

Core fields:
- episode id
- software domain
- app name
- window title
- time range
- summary
- anomaly tags
- event refs
- frame refs
- log refs
- confidence metadata

## 18.4 Analyzer result model

Suggested fields:
- analyzer_id
- domain
- anomaly_type
- confidence
- evidence
- suggested_action
- requires_followup

## 19. Repo-Level Implementation Map

## 19.1 Existing files to modify

- [`shail/perception/buffer.py`](/Users/reyhan/jarvis_master/shail/perception/buffer.py)
  - add retention policy integration
  - support log lines and frame metadata retention

- [`shail/perception/integration.py`](/Users/reyhan/jarvis_master/shail/perception/integration.py)
  - add smarter frame persistence, dedup, and aging strategy

- [`shail/perception/grounding_agent.py`](/Users/reyhan/jarvis_master/shail/perception/grounding_agent.py)
  - route retrieval across raw/session/historical layers
  - use richer scoring

- [`shail/perception/vision_agent.py`](/Users/reyhan/jarvis_master/shail/perception/vision_agent.py)
  - consume episode/frame metadata better
  - support domain-aware observation hooks

- [`shail/orchestration/master_planner.py`](/Users/reyhan/jarvis_master/shail/orchestration/master_planner.py)
  - add analyzer recommendation and consent path

- [`apps/shail/settings.py`](/Users/reyhan/jarvis_master/apps/shail/settings.py)
  - add new grounding and analyzer config fields

- [`shail/memory/rag.py`](/Users/reyhan/jarvis_master/shail/memory/rag.py)
  - add grounding/episode namespaces and ingestion helpers

## 19.2 New files to add

- `shail/perception/retention_policy.py`
- `shail/perception/episode_builder.py`
- `shail/perception/episode_store.py`
- `shail/perception/retrieval_router.py`
- `shail/perception/log_buffer.py`
- `shail/perception/analyzers/base.py`
- `shail/perception/analyzers/registry.py`
- `shail/perception/analyzers/capability_resolver.py`
- `shail/perception/analyzers/gazebo.py`
- `shail/safety/domain_analyzer_permissions.py`
- `docs/ANALYZER_CONSENT_MODEL.md` (optional supporting design doc)

## 20. UI Requirements

### macOS/desktop UI

Need screens or components for:

- grounding retention settings
- current grounding status
- analyzer recommendation prompt
- analyzer consent details
- enabled analyzer list
- evidence explanation view

### Dashboard / debug UI

Need panels for:

- recent grounding events
- session episodes
- anomaly tags
- active analyzers
- retrieval confidence breakdown

## 21. Metrics and Success Criteria

### Product metrics

- percentage of historical queries answered without user re-explaining
- anomaly-detection precision for supported domains
- user approval rate for recommended analyzers
- reduction in repeated clarification requests

### System metrics

- grounding query latency
- episode summarization latency
- storage growth over time
- frame dedup ratio
- historical retrieval hit rate
- analyzer usage rate by domain

### Quality targets

- Grounding V2 should materially outperform current grounding for queries beyond 5 minutes
- domain analyzers should only be recommended when generic confidence repeatedly falls below threshold

## 22. Rollout Plan

### Phase 1: Grounding V2 foundations

- configurable retention
- event/frame split
- frame dedup and metadata preservation
- summary cutoff

### Phase 2: session and long-term grounding

- episode builder
- episode store
- long-term RAG ingestion
- retrieval router

### Phase 3: adaptive analyzer framework

- analyzer registry
- capability resolver
- consent flow
- first analyzer recommendation path

### Phase 4: first domain analyzers

- Gazebo analyzer
- IDE/code analyzer
- browser/workflow analyzer

### Phase 5: cross-check and quality tuning

- evidence fusion tuning
- metrics wiring
- confidence calibration

## 23. Risks

### Risk: storage explosion

Mitigation:
- frame dedup
- metadata-only retention
- configurable policies
- episode summarization

### Risk: analyzer sprawl

Mitigation:
- capability thresholds
- opt-in analyzers only
- generic-first architecture

### Risk: privacy concerns

Mitigation:
- transparent consent
- retention controls
- analyzer-scoped permissions
- PII masking and bounded storage

### Risk: false anomaly detection

Mitigation:
- cross-check across signals
- domain-specific confidence calibration
- user guidance fallback

## 24. Open Questions

1. Should episode storage live in SQLite first, or go directly through RAG-backed records?
2. Should log ingestion be unified under perception or registered as plugin-specific adapters?
3. How should analyzer consent be stored: per app, per domain, per plugin, or per project?
4. Should frame change detection use simple hashing first or perceptual hashes from day one?
5. How much of analyzer recommendation should be proactive at plugin install vs reactive after low-confidence runs?

## 25. Implementation Readiness Notes

This PRD is designed so that an implementation agent can use it directly to build the feature set in this repository.

Minimum implementation order:

1. add settings and retention policy manager
2. upgrade buffer and integration for split retention
3. add episode builder and episode store
4. ingest episodes into RAG
5. add retrieval router and GroundingAgent V2 query path
6. add analyzer registry and capability resolver
7. add analyzer consent flow
8. implement first domain analyzer, starting with Gazebo

## 26. Final Product Principle

The system should behave like this:

- SHAIL first tries to understand the user's recent and historical workflow using one strong generic grounding engine
- SHAIL only proposes software-specific expertise when the software is complex enough that generic grounding is not reliably sufficient
- SHAIL explains why the extension matters and asks for consent before deepening its access

That keeps the system:

- scalable
- privacy-aware
- implementation-friendly
- adaptive rather than bloated
- strong enough for complex debugging and workflow recovery
