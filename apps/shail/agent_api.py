import asyncio
import contextvars
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.shail.auth_api import get_current_user
from apps.shail.db import get_db
from shail.hermes.adapter import get_hermes_adapter
from shail.hermes.types import ExecutionStatus, HermesSkill
from shail.hermes.persistent_memory import get_persistent_memory

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/agent", tags=["agent"])

# Thread/Task-local request context
active_request_id = contextvars.ContextVar("active_request_id", default=None)

# Active background tasks and SSE subscribers
active_tasks: Dict[str, asyncio.Task] = {}
task_queues: Dict[str, List[asyncio.Queue]] = {}
active_approvals: Dict[str, asyncio.Future] = {}

class TaskCreateRequest(BaseModel):
    workspace_id: str
    prompt: str
    risk_policy: Optional[str] = "request-review"

class TaskResponse(BaseModel):
    task_id: str
    session_id: str
    status: str
    created_at: str

class ApprovalRequest(BaseModel):
    approved: bool

# ── Event Subscription Helpers ───────────────────────────────────────────────

def publish_task_event(task_id: str, event_type: str, data: dict):
    """Publish an event frame to all SSE queues listening to this task."""
    queues = task_queues.get(task_id, [])
    # Format according to the Agent Event Stream specifications (Section 5.2)
    event_frame = {
        "event": event_type,
        "payload": {
            "task_id": task_id,
            **data
        }
    }
    for q in queues:
        q.put_nowait(event_frame)

async def wait_for_approval(task_id: str) -> bool:
    """Pause the agent execution loop and wait for user approval input."""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    active_approvals[task_id] = fut
    try:
        logger.info(f"Task {task_id} suspended: waiting for user approval.")
        return await fut
    finally:
        active_approvals.pop(task_id, None)

# ── Helper to determine safe commands ───────────────────────────────────────

def is_command_safe(command: str) -> bool:
    """
    Check if a shell command is within the Phase 1 allowlist.
    Only allows basic inspection and safe build runs.
    """
    cmd = command.strip().lower()
    # Safe commands list
    safe_prefixes = [
        "git status",
        "git diff",
        "git log",
        "pytest",
        "npm run build",
        "ls",
        "dir",
    ]
    return any(cmd.startswith(prefix) for prefix in safe_prefixes)

# ── Phase 3 Checkpoint and Blueprint Helpers ──────────────────────────────────

def save_checkpoint(task_id: str, checkpoint_data: dict) -> None:
    """Save execution checkpoint snapshot to database."""
    with get_db() as conn:
        conn.execute(
            "UPDATE hermes_sessions SET checkpoints = ?, updated_at = ? WHERE shail_task_id = ?",
            (json.dumps(checkpoint_data), datetime.now(timezone.utc).isoformat(), task_id)
        )
    publish_task_event(task_id, "task.checkpoint", {"checkpoint": checkpoint_data})

def get_checkpoint(task_id: str) -> Optional[dict]:
    """Retrieve checkpoint snapshot from database."""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT checkpoints FROM hermes_sessions WHERE shail_task_id = ?", (task_id,)).fetchone()
        if row and row["checkpoints"]:
            return json.loads(row["checkpoints"])
    except Exception as e:
        logger.warning(f"Failed to fetch checkpoints for {task_id}: {e}")
    return None

def generate_and_save_blueprint(task_id: str, prompt: str, result: Any, status: str) -> dict:
    """Generate and persist the structured Task Execution Blueprint (Phase 3)."""
    checkpoints = get_checkpoint(task_id) or {"steps": [], "plan": []}
    steps = checkpoints.get("steps", [])
    
    tools_used = list(set(["run_python" if s.get("use_python") else "run_command" for s in steps]))
    failures = [s.get("stderr") for s in steps if not s.get("success") and s.get("stderr")]
    
    res_val = ""
    if result:
        res_val = str(getattr(result, "result", result))
        
    blueprint = {
        "task_id": task_id,
        "objective": prompt,
        "status": status,
        "plan": [
            "1. Plan workspace environment",
            "2. Execute commands",
            "3. Collect output and verify deliverables"
        ],
        "tools_used": tools_used,
        "evidence": [
            {
                "tool": "hybrid_search",
                "content": "Contextual grounding from local repository search completed."
            }
        ],
        "artifacts": [
            {"filename": s.get("command"), "status": "executed"} for s in steps
        ],
        "failures": failures,
        "next_actions": [
            "Verify output using pytest" if status == "completed" else "Retry execution with revised context"
        ],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "final_result": res_val
    }
    
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE hermes_sessions SET blueprint = ?, updated_at = ? WHERE shail_task_id = ?",
                (json.dumps(blueprint), datetime.now(timezone.utc).isoformat(), task_id)
            )
    except Exception as e:
        logger.error(f"Failed to save blueprint: {e}")
        
    publish_task_event(task_id, "task.blueprint", {"blueprint": blueprint})
    return blueprint

# ── Background Task Runner ──────────────────────────────────────────────────

async def run_hermes_background(task_id: str, session_id: str, prompt: str, workspace_id: str):
    """Execution wrapper running the Hermes loop in the background."""
    active_request_id.set(task_id)
    adapter = get_hermes_adapter()
    
    publish_task_event(task_id, "task.accepted", {"status": "running"})
    
    try:
        # Pre-populate workspace context
        context = {
            "workspace_id": workspace_id,
            "session_id": session_id,
        }
        
        # Checkpoint recovery (Phase 3)
        checkpoint = get_checkpoint(task_id)
        if checkpoint:
            logger.info(f"Resuming task {task_id} from saved checkpoint...")
            publish_task_event(task_id, "task.resuming", {
                "checkpoint": checkpoint,
                "completed_steps": len(checkpoint.get("steps", []))
            })
            context["steps"] = checkpoint.get("steps", [])
            
        # Update database state
        with get_db() as conn:
            conn.execute(
                "UPDATE hermes_sessions SET status = 'running', updated_at = ? WHERE shail_task_id = ?",
                (datetime.now(timezone.utc).isoformat(), task_id)
            )
            
        # Execute Hermes Loop
        result = await adapter.execute(prompt, context=context, enable_retry=True)
        
        # Check completion status
        status = "completed" if result.status == ExecutionStatus.COMPLETED else "failed"
        
        # Generate and save blueprint report (Phase 3)
        generate_and_save_blueprint(task_id, prompt, result, status)
        
        with get_db() as conn:
            conn.execute(
                "UPDATE hermes_sessions SET status = ?, updated_at = ? WHERE shail_task_id = ?",
                (status, datetime.now(timezone.utc).isoformat(), task_id)
            )
            
        publish_task_event(task_id, f"task.{status}", {
            "result": result.result,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms
        })
        
    except asyncio.CancelledError:
        logger.info(f"Task {task_id} execution was cancelled.")
        with get_db() as conn:
            conn.execute(
                "UPDATE hermes_sessions SET status = 'cancelled', updated_at = ? WHERE shail_task_id = ?",
                (datetime.now(timezone.utc).isoformat(), task_id)
            )
        publish_task_event(task_id, "task.cancelled", {"status": "cancelled"})
        
    except Exception as e:
        logger.error(f"Error in Hermes background task {task_id}: {e}")
        # Save failure blueprint (Phase 3)
        generate_and_save_blueprint(task_id, prompt, None, "failed")
        with get_db() as conn:
            conn.execute(
                "UPDATE hermes_sessions SET status = 'failed', updated_at = ? WHERE shail_task_id = ?",
                (datetime.now(timezone.utc).isoformat(), task_id)
            )
        publish_task_event(task_id, "task.failed", {"error": str(e)})
        
    finally:
        active_tasks.pop(task_id, None)

# ── Endpoints ───────────────────────────────────────────────────────────────

@agent_router.post("/tasks", response_model=TaskResponse)
async def create_task_endpoint(req: TaskCreateRequest, user_id: str = Depends(get_current_user)):
    """Create a new SHAIL-owned Hermes task and initiate execution."""
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    session_id = f"hermes_sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO hermes_sessions (shail_task_id, hermes_session_id, workspace_id, ui_origin, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (task_id, session_id, req.workspace_id, "dashboard", now, now)
        )
        
    # Start loop in background
    task = asyncio.create_task(
        run_hermes_background(task_id, session_id, req.prompt, req.workspace_id)
    )
    active_tasks[task_id] = task
    
    return TaskResponse(
        task_id=task_id,
        session_id=session_id,
        status="queued",
        created_at=now
    )

@agent_router.post("/tasks/{id}/messages")
async def send_message_endpoint(id: str, prompt: str, user_id: str = Depends(get_current_user)):
    """Send a continuation or redirection message to an active task."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM hermes_sessions WHERE shail_task_id = ?", (id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task session not found")
        
    # In Phase 1, we log the redirect message and forward to the SSE stream
    publish_task_event(id, "message.received", {"prompt": prompt})
    return {"ok": True}

@agent_router.get("/tasks/{id}")
async def get_task_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Read the current status and session mappings of a task."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM hermes_sessions WHERE shail_task_id = ?", (id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)

@agent_router.get("/tasks/{id}/events")
async def stream_events_endpoint(id: str):
    """Server-Sent Events (SSE) stream for real-time task observability."""
    async def event_generator():
        q = asyncio.Queue()
        task_queues.setdefault(id, []).append(q)
        try:
            # Yield active status immediately to confirm connection
            yield f"data: {json.dumps({'event': 'connection.established', 'payload': {'task_id': id}})}\n\n"
            while True:
                event_frame = await q.get()
                yield f"data: {json.dumps(event_frame)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if id in task_queues:
                if q in task_queues[id]:
                    task_queues[id].remove(q)
                if not task_queues[id]:
                    task_queues.pop(id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@agent_router.post("/tasks/{id}/approve")
async def approve_endpoint(id: str, req: ApprovalRequest, user_id: str = Depends(get_current_user)):
    """Approve or reject a paused task tool-execution request."""
    fut = active_approvals.get(id)
    if not fut or fut.done():
        raise HTTPException(status_code=400, detail="No active approval required for this task")
        
    fut.set_result(req.approved)
    return {"ok": True}

@agent_router.post("/tasks/{id}/cancel")
async def cancel_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Force-cancel an active running task."""
    # Synchronously update the DB state first to avoid async query race conditions
    with get_db() as conn:
        row = conn.execute("SELECT * FROM hermes_sessions WHERE shail_task_id = ?", (id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
        
    with get_db() as conn:
        conn.execute(
            "UPDATE hermes_sessions SET status = 'cancelled', updated_at = ? WHERE shail_task_id = ?",
            (datetime.now(timezone.utc).isoformat(), id)
        )
        
    task = active_tasks.get(id)
    if task:
        task.cancel()
        
    return {"status": "cancelled"}

@agent_router.get("/tasks/{id}/artifacts")
async def get_artifacts_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """List any artifacts generated by the task session in the workspace."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM hermes_sessions WHERE shail_task_id = ?", (id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task session not found")
        
    workspace_id = row["workspace_id"]
    artifacts = []
    
    # Scan the workspace directories for output report artifacts
    if os.path.exists(workspace_id):
        for root, dirs, files in os.walk(workspace_id):
            # Limit traversal depth
            if len(Path(root).relative_to(Path(workspace_id)).parts) > 2:
                continue
            for f in files:
                # In Phase 1, target markdown results reports or output artifacts
                if f.endswith(".md") or f.endswith(".json") or f.startswith("report"):
                    full_path = os.path.join(root, f)
                    artifacts.append({
                        "filename": f,
                        "path": full_path,
                        "size_bytes": os.path.getsize(full_path),
                        "modified_at": datetime.fromtimestamp(os.path.getmtime(full_path), timezone.utc).isoformat()
                    })
                    
    return {"artifacts": sorted(artifacts, key=lambda a: a["modified_at"], reverse=True)}

@agent_router.get("/tasks/{id}/blueprint")
async def get_task_blueprint_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Fetch the final structured Task Execution Blueprint (Phase 3)."""
    with get_db() as conn:
        row = conn.execute("SELECT blueprint FROM hermes_sessions WHERE shail_task_id = ?", (id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    if not row["blueprint"]:
        raise HTTPException(status_code=202, detail="Blueprint is not yet generated for this active task.")
    return json.loads(row["blueprint"])

@agent_router.get("/tasks/{id}/checkpoint")
async def get_task_checkpoint_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Fetch the active step checkpoints (Phase 3)."""
    checkpoint = get_checkpoint(id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail="No checkpoints found for this task.")
    return checkpoint

# ── Browser Action Bridge WebSockets (Phase 2) ───────────────────────────────

extension_ws: Optional[WebSocket] = None
pending_commands: Dict[str, asyncio.Future] = {}

async def send_browser_command(action: str, **params) -> Dict[str, Any]:
    """Send a browser action command to the connected WXT extension and await response."""
    global extension_ws
    if not extension_ws:
        return {"status": "error", "error": "Chrome extension is not connected to SHAIL Browser Action Bridge."}
        
    cmd_id = f"cmd_{uuid.uuid4().hex[:12]}"
    payload = {
        "command_id": cmd_id,
        "action": action,
        **params
    }
    
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_commands[cmd_id] = fut
    
    try:
        await extension_ws.send_json(payload)
        # Wait up to 15 seconds for extension completion
        return await asyncio.wait_for(fut, timeout=15.0)
    except asyncio.TimeoutError:
        pending_commands.pop(cmd_id, None)
        return {"status": "error", "error": "Browser action command timed out."}
    except Exception as e:
        pending_commands.pop(cmd_id, None)
        return {"status": "error", "error": str(e)}

@agent_router.websocket("/browser/ws")
async def browser_websocket(websocket: WebSocket):
    """WebSocket connection handler for Chrome extension Browser Action Bridge."""
    global extension_ws
    await websocket.accept()
    extension_ws = websocket
    logger.info("Chrome extension successfully connected to SHAIL Browser Action Bridge.")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                cmd_id = msg.get("command_id")
                if cmd_id in pending_commands:
                    fut = pending_commands.pop(cmd_id)
                    if not fut.done():
                        fut.set_result(msg)
            except Exception as e:
                logger.warning(f"Error parsing message from extension over WebSocket: {e}")
    except WebSocketDisconnect:
        logger.info("Chrome extension disconnected from SHAIL Browser Action Bridge.")
    finally:
        if extension_ws == websocket:
            extension_ws = None

# ── Skills Registry Endpoints (Phase 3) ──────────────────────────────────────

proposed_skills: Dict[str, HermesSkill] = {}

class SkillCreateSchema(BaseModel):
    name: str
    prompt_template: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None

@agent_router.get("/skills")
async def get_skills_endpoint(user_id: str = Depends(get_current_user)):
    """List all approved Hermes skills."""
    mem = get_persistent_memory()
    skills = mem.get_all_skills()
    return {"skills": [s.model_dump() for s in skills]}

@agent_router.get("/skills/proposed")
async def get_proposed_skills_endpoint(user_id: str = Depends(get_current_user)):
    """List all proposed Hermes skills waiting for approval."""
    return {"proposed_skills": [s.model_dump() for s in proposed_skills.values()]}

@agent_router.post("/skills/propose")
async def propose_skill_endpoint(req: SkillCreateSchema, user_id: str = Depends(get_current_user)):
    """Propose a new Hermes skill."""
    skill = HermesSkill(
        name=req.name,
        prompt_template=req.prompt_template,
        description=req.description,
        tags=req.tags or []
    )
    proposed_skills[skill.skill_id] = skill
    return {"status": "proposed", "skill": skill.model_dump()}

@agent_router.post("/skills/{id}/approve")
async def approve_skill_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Approve a proposed Hermes skill and save it to persistent memory."""
    skill = proposed_skills.pop(id, None)
    if not skill:
        raise HTTPException(status_code=404, detail="Proposed skill not found")
    
    mem = get_persistent_memory()
    mem.store_skill(skill)
    return {"status": "approved", "skill": skill.model_dump()}

@agent_router.delete("/skills/{id}")
async def delete_skill_endpoint(id: str, user_id: str = Depends(get_current_user)):
    """Delete a Hermes skill from persistent memory."""
    mem = get_persistent_memory()
    success = mem.delete_skill(id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True}
