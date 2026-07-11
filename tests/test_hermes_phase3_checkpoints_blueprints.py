import asyncio
import json
import pytest
import sqlite3
import httpx
from datetime import datetime, timezone

from apps.shail.main import app
from apps.shail.db import get_db
from apps.shail.auth_store import init_auth_db, create_user, create_api_key
from apps.shail.agent_api import get_checkpoint, save_checkpoint, generate_and_save_blueprint, run_hermes_background

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate the database and set up workspace context."""
    db_file = tmp_path / "test_phase3.db"
    
    def fake_db():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        return conn
        
    monkeypatch.setattr("apps.shail.auth_store.get_db", fake_db)
    monkeypatch.setattr("apps.shail.agent_api.get_db", fake_db)
    
    # Mock settings database path
    from apps.shail.settings import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "sqlite_path", str(db_file))
    
    init_auth_db()
    
    # Pre-register a test session
    conn = fake_db()
    with conn:
        conn.execute(
            "INSERT INTO hermes_sessions (shail_task_id, hermes_session_id, workspace_id, ui_origin, status, created_at, updated_at) "
            "VALUES ('task_123', 'sess_abc', 'C:/Users/surka/jarvis_master', 'dashboard', 'queued', ?, ?)",
            (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
        
    # Mock Hermes adapter execute to prevent calling external LLMs during test runs
    from shail.hermes.types import HermesResponse, ExecutionStatus
    async def mock_execute(self, task, context=None, enable_retry=True):
        return HermesResponse(
            request_id="mock_req",
            status=ExecutionStatus.COMPLETED,
            result="Completed test successfully",
            error=None
        )
    monkeypatch.setattr("shail.hermes.adapter.HermesAdapter.execute", mock_execute)
    
    user = create_user("test_phase3@shail.com", "password123", "Phase3 Tester")
    api_key = create_api_key(user["id"], label="TestKey")
    
    return {"Authorization": f"Bearer {api_key}"}

# ── 1. Checkpoint Unit Tests ──────────────────────────────────────────────────

def test_checkpoint_store_and_retrieve(setup_test_db):
    task_id = "task_123"
    
    # Save a mock checkpoint
    mock_data = {
        "steps": [
            {"command": "git status", "success": True, "timestamp": "2026-07-11T12:00:00Z"}
        ],
        "plan": ["Run git status"]
    }
    save_checkpoint(task_id, mock_data)
    
    # Retrieve and verify
    retrieved = get_checkpoint(task_id)
    assert retrieved is not None
    assert retrieved["plan"] == ["Run git status"]
    assert len(retrieved["steps"]) == 1
    assert retrieved["steps"][0]["command"] == "git status"

# ── 2. Blueprint Generator Unit Tests ─────────────────────────────────────────

def test_blueprint_generation(setup_test_db):
    task_id = "task_123"
    prompt = "Create a git inspection blueprint report."
    
    # Save dummy checkpoints first to gather tools/failures
    save_checkpoint(task_id, {
        "steps": [
            {"command": "pytest", "use_python": False, "success": True, "stderr": ""},
            {"command": "mock_script.py", "use_python": True, "success": False, "stderr": "ImportError: no module named mock"}
        ]
    })
    
    # Generate blueprint
    blueprint = generate_and_save_blueprint(task_id, prompt, "Test run result", "completed")
    
    assert blueprint["task_id"] == task_id
    assert blueprint["objective"] == prompt
    assert blueprint["status"] == "completed"
    assert "run_python" in blueprint["tools_used"]
    assert "run_command" in blueprint["tools_used"]
    assert len(blueprint["failures"]) == 1
    assert "ImportError" in blueprint["failures"][0]
    assert blueprint["final_result"] == "Test run result"

# ── 3. Checkpoint Recovery Integration Test ───────────────────────────────────

def test_checkpoint_recovery_trigger(setup_test_db):
    task_id = "task_123"
    
    # Pre-populate checkpoint
    save_checkpoint(task_id, {
        "steps": [{"command": "git status", "success": True}],
        "plan": ["Next step"]
    })
    
    # Run loop and check recovery
    async def run():
        await run_hermes_background(task_id, "sess_abc", "Run checks", "C:/Users/surka/jarvis_master")
        # Assert blueprint exists after recovery completion
        checkpoint = get_checkpoint(task_id)
        assert checkpoint is not None
        assert len(checkpoint["steps"]) == 1
        
    asyncio.run(run())

# ── 4. Blueprint & Checkpoint Endpoints Tests ─────────────────────────────────

def test_phase3_endpoints(setup_test_db):
    headers = setup_test_db
    task_id = "task_123"
    
    # Create checkpoints and blueprint
    save_checkpoint(task_id, {
        "steps": [{"command": "git log", "success": True}]
    })
    generate_and_save_blueprint(task_id, "Inspect commits", "Completed successfully", "completed")
    
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Query Checkpoint endpoint
            chk_resp = await client.get(f"/api/agent/tasks/{task_id}/checkpoint", headers=headers)
            assert chk_resp.status_code == 200
            chk_data = chk_resp.json()
            assert "steps" in chk_data
            
            # Query Blueprint endpoint
            bp_resp = await client.get(f"/api/agent/tasks/{task_id}/blueprint", headers=headers)
            assert bp_resp.status_code == 200
            bp_data = bp_resp.json()
            assert bp_data["status"] == "completed"
            assert bp_data["final_result"] == "Completed successfully"
            
    asyncio.run(run())

# ── 5. Skills Registry Endpoints Tests ────────────────────────────────────────

def test_skills_registry_workflow(setup_test_db):
    headers = setup_test_db
    
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Propose a skill
            payload = {
                "name": "Test Python Analyzer",
                "prompt_template": "Analyze syntax of {task}",
                "description": "Custom parser skill",
                "tags": ["python", "testing"]
            }
            prop_resp = await client.post("/api/agent/skills/propose", json=payload, headers=headers)
            assert prop_resp.status_code == 200
            prop_data = prop_resp.json()
            assert prop_data["status"] == "proposed"
            skill_id = prop_data["skill"]["skill_id"]
            
            # 2. Get proposed skills list
            list_prop_resp = await client.get("/api/agent/skills/proposed", headers=headers)
            assert list_prop_resp.status_code == 200
            assert len(list_prop_resp.json()["proposed_skills"]) == 1
            
            # 3. Approve the proposed skill
            appr_resp = await client.post(f"/api/agent/skills/{skill_id}/approve", headers=headers)
            assert appr_resp.status_code == 200
            assert appr_resp.json()["status"] == "approved"
            
            # 4. Get active skills list and verify it is stored
            list_skills_resp = await client.get("/api/agent/skills", headers=headers)
            assert list_skills_resp.status_code == 200
            assert any(s["skill_id"] == skill_id for s in list_skills_resp.json()["skills"])
            
            # 5. Delete the skill
            del_resp = await client.delete(f"/api/agent/skills/{skill_id}", headers=headers)
            assert del_resp.status_code == 200
            assert del_resp.json()["ok"] is True
            
    asyncio.run(run())
