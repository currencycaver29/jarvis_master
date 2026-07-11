import asyncio
import json
import pytest
import httpx
import sqlite3
from datetime import datetime, timezone

from apps.shail.main import app
from apps.shail.db import get_db
from apps.shail.agent_api import is_command_safe, active_approvals, task_queues, stream_events_endpoint
from apps.shail.auth_store import init_auth_db, create_user, create_api_key

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate the auth/sessions DB for testing."""
    db_file = tmp_path / "test_auth.db"
    
    def fake_db():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        return conn
        
    monkeypatch.setattr("apps.shail.auth_store.get_db", fake_db)
    monkeypatch.setattr("apps.shail.agent_api.get_db", fake_db)
    
    init_auth_db()
    
    # Mock Hermes adapter execute to avoid hitting local Ollama during tests
    from shail.hermes.types import HermesResponse, ExecutionStatus
    async def mock_execute(self, task, context=None, enable_retry=True):
        return HermesResponse(
            request_id="mock_req",
            status=ExecutionStatus.COMPLETED,
            result="Mock completion successfully completed",
            error=None,
            execution_time_ms=10.0,
            retry_count=0
        )
    monkeypatch.setattr("shail.hermes.adapter.HermesAdapter.execute", mock_execute)
    
    user = create_user("test_hermes@shail.com", "password123", "Hermes Tester")
    api_key = create_api_key(user["id"], label="TestKey")
    
    return {"Authorization": f"Bearer {api_key}"}

# ── 1. Gated Command Allowlist Tests ──────────────────────────────────────────

def test_command_allowlist():
    assert is_command_safe("git status") is True
    assert is_command_safe("git diff") is True
    assert is_command_safe("pytest") is True
    assert is_command_safe("ls -la") is True
    
    assert is_command_safe("pip install watchdog") is False
    assert is_command_safe("rm -rf /") is False
    assert is_command_safe("python setup.py install") is False

# ── 2. Gateway API Endpoint Tests ─────────────────────────────────────────────

def test_create_and_fetch_task(setup_test_db):
    headers = setup_test_db
    
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "workspace_id": "C:/Users/surka/jarvis_master",
                "prompt": "Run a test suite command and show output.",
                "risk_policy": "request-review"
            }
            response = await client.post("/api/agent/tasks", json=payload, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert "session_id" in data
            
            task_id = data["task_id"]
            get_resp = await client.get(f"/api/agent/tasks/{task_id}", headers=headers)
            assert get_resp.status_code == 200
            task_data = get_resp.json()
            assert task_data["shail_task_id"] == task_id
            
    asyncio.run(run())

# ── 3. SSE Event Streaming & Connection Test ──────────────────────────────────

def test_event_stream_connection(setup_test_db):
    async def run():
        task_id = "test_sse_direct_123"
        response = await stream_events_endpoint(task_id)
        
        # Verify it returns a StreamingResponse in text/event-stream media format
        assert response.media_type == "text/event-stream"
        
        # Read the first event from the generator to confirm structure
        async for chunk in response.body_iterator:
            assert "connection.established" in chunk
            assert task_id in chunk
            break
            
    asyncio.run(run())

# ── 4. Task Cancellation Endpoint Test ────────────────────────────────────────

def test_task_cancellation(setup_test_db):
    headers = setup_test_db
    
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "workspace_id": "C:/Users/surka/jarvis_master",
                "prompt": "Long running test",
                "risk_policy": "request-review"
            }
            create_resp = await client.post("/api/agent/tasks", json=payload, headers=headers)
            task_id = create_resp.json()["task_id"]
            
            cancel_resp = await client.post(f"/api/agent/tasks/{task_id}/cancel", headers=headers)
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["status"] == "cancelled"
            
            get_resp = await client.get(f"/api/agent/tasks/{task_id}", headers=headers)
            assert get_resp.json()["status"] == "cancelled"
            
    asyncio.run(run())

# ── 5. Consent Approval Gating Test ───────────────────────────────────────────

def test_approval_gating(setup_test_db):
    headers = setup_test_db
    task_id = "task_test_approval"
    
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Set up future for approval
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            active_approvals[task_id] = fut
            
            # Trigger approval response endpoint concurrently
            async def simulate_user_approval():
                await asyncio.sleep(0.1)
                response = await client.post(
                    f"/api/agent/tasks/{task_id}/approve",
                    json={"approved": True},
                    headers=headers
                )
                assert response.status_code == 200
                assert response.json()["ok"] is True
                
            asyncio.create_task(simulate_user_approval())
            
            from apps.shail.agent_api import wait_for_approval
            result = await wait_for_approval(task_id)
            assert result is True
            
    asyncio.run(run())
