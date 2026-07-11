import asyncio
import json
import pytest
import sqlite3
import httpx
from datetime import datetime, timezone

from apps.shail.main import app
from apps.shail.db import get_db
from apps.shail.auth_store import init_auth_db, create_user, create_api_key
from apps.shail.blueprints import init_blueprint_db
from apps.shail.settings import get_settings
from shail.integrations.tools.context_tools import ContextToolsAdapter
from shail.integrations.tools.browser_tools import BrowserToolsAdapter, check_domain_policy

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate the database and set up mock workspace context."""
    db_file = tmp_path / "test_phase2.db"
    
    def fake_db():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        return conn
        
    monkeypatch.setattr("apps.shail.auth_store.get_db", fake_db)
    monkeypatch.setattr("apps.shail.agent_api.get_db", fake_db)
    monkeypatch.setattr("shail.integrations.tools.context_tools.get_db", fake_db)
    
    # Force settings path to match test database
    settings = get_settings()
    monkeypatch.setattr(settings, "sqlite_path", str(db_file))
    
    init_auth_db()
    init_blueprint_db()
    
    # Insert a dummy memory fact for relation graph tests
    conn = fake_db()
    with conn:
        conn.execute(
            "INSERT INTO memory_facts (fact_id, memory_id, entity, attribute, value, confidence, created_at) "
            "VALUES ('fact_123', 'mem_abc', 'Hermes', 'role', 'agent', 0.95, ?)",
            (datetime.now(timezone.utc).isoformat(),)
        )
        
    # Mock hybrid search to avoid dependency on Chroma/embeddings in test environment
    async def mock_hybrid_search(query, k=5):
        return [
            ("This is a mock memory matching: " + query, 0.85, {"source_url": "https://test.com/doc", "title": "Test Doc", "created_at": "2026-07-11T12:00:00Z"})
        ]
    monkeypatch.setattr("shail.integrations.tools.context_tools.hybrid_search", mock_hybrid_search)
    
    user = create_user("test_phase2@shail.com", "password123", "Phase2 Tester")
    api_key = create_api_key(user["id"], label="TestKey")
    
    return {"Authorization": f"Bearer {api_key}"}

# ── 1. Context Tools Unit Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_tools_search():
    adapter = ContextToolsAdapter()
    res = await adapter.search_memories("Gemma 3 integration", limit=2)
    assert res["query"] == "Gemma 3 integration"
    assert len(res["results"]) == 1
    assert res["results"][0]["title"] == "Test Doc"
    assert "mock memory" in res["results"][0]["content"]

def test_context_tools_graph(setup_test_db):
    adapter = ContextToolsAdapter()
    res = adapter.query_graph("Hermes")
    assert res["query"] == "Hermes"
    assert len(res["nodes"]) > 0
    assert any(node["label"] == "Hermes" for node in res["nodes"])

def test_context_tools_workspace():
    adapter = ContextToolsAdapter()
    res = adapter.get_active_workspace()
    assert "active_workspace" in res
    assert "scan_roots" in res

def test_context_tools_path_resolver():
    adapter = ContextToolsAdapter()
    resolved = adapter.resolve_path_pointer("src/file.ts")
    assert resolved.replace("\\", "/").endswith("src/file.ts")

# ── 2. Browser Action Blocklist Gating Tests ──────────────────────────────────

def test_browser_domain_policy():
    # Allowed domains
    check_domain_policy("https://google.com")
    check_domain_policy("https://github.com/currencycaver29/jarvis_master")
    check_domain_policy("https://localhost:3000/dashboard")
    
    # Denied domains should trigger ValueError
    with pytest.raises(ValueError) as exc:
        check_domain_policy("https://facebook.com/profile")
    assert "blocked by SHAIL security policy" in str(exc.value)
    
    with pytest.raises(ValueError):
        check_domain_policy("https://gmail.com")
        
    with pytest.raises(ValueError):
        check_domain_policy("https://paypal.com/checkout")

# ── 3. Browser Action Bridge WebSocket Tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_browser_action_bridge_direct():
    # Mock a websocket connection structure
    class MockWebSocket:
        def __init__(self):
            self.sent_messages = []
        async def send_json(self, data):
            self.sent_messages.append(data)
            
    mock_ws = MockWebSocket()
    
    from apps.shail import agent_api
    agent_api.extension_ws = mock_ws
    
    # Trigger send_browser_command in background
    cmd_task = asyncio.create_task(
        agent_api.send_browser_command("open_url", url="https://allowed.com")
    )
    
    # Yield control to let the command execute and send
    await asyncio.sleep(0.05)
    
    # Assert payload was routed and packaged correctly
    assert len(mock_ws.sent_messages) == 1
    sent_msg = mock_ws.sent_messages[0]
    assert sent_msg["action"] == "open_url"
    assert sent_msg["url"] == "https://allowed.com"
    
    # Simulate client responding by resolving the future
    cmd_id = sent_msg["command_id"]
    assert cmd_id in agent_api.pending_commands
    
    fut = agent_api.pending_commands.pop(cmd_id)
    fut.set_result({"status": "success", "tabId": 42})
    
    # Await task results
    res = await cmd_task
    assert res["status"] == "success"
    assert res["tabId"] == 42
    
    # Reset connection state
    agent_api.extension_ws = None
