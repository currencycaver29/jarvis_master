import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shail.hermes.integration import reset_hermes_sail_integration, get_hermes_sail_integration
from shail.hermes.types import ExecutionStatus, HermesSkill
from shail.hermes.persistent_memory import get_persistent_memory, reset_persistent_memory
from shail.hermes.sandbox import get_sandbox, reset_sandbox

test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_data"))
os.makedirs(test_dir, exist_ok=True)

class MockSettings:
    rag_chroma_path = os.path.join(test_dir, "chroma")
    rag_vector_store = "chroma"
    rag_embedding_dim = 768
    rag_pg_dsn = ""
    ollama_base_url = "http://localhost:11434"
    ollama_embed_model = "mxbai-embed-large"
    ollama_embed_dim = 768
    default_timeout_sec = 30.0

class TestHermesIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 1. Clean up singletons
        reset_hermes_sail_integration()
        reset_persistent_memory()
        reset_sandbox()
        
        # 2. Patch dependencies
        self.patchers = []
        self.patchers.append(patch('shail.memory.vector_store.get_vector_store', return_value=MagicMock()))
        self.patchers.append(patch('chromadb.PersistentClient', return_value=MagicMock()))
        self.patchers.append(patch('apps.shail.settings.get_settings', return_value=MockSettings()))
        
        # Patch embedding to avoid network calls
        self.patchers.append(patch('shail.hermes.persistent_memory.embed_texts', return_value=[[0.1]*768]))
        self.patchers.append(patch('shail.hermes.persistent_memory.embed_query', return_value=[0.1]*768))
        
        for p in self.patchers:
            p.start()
            
        self.integration = get_hermes_sail_integration()
        # Mock health check to be fast
        self.integration.adapter.model_client.health_check = MagicMock(return_value=asyncio.Future())
        self.integration.adapter.model_client.health_check.return_value.set_result(True)
        
        await self.integration.initialize()
        self.memory = get_persistent_memory()

    async def asyncTearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        patch.stopall()
        reset_hermes_sail_integration()

    async def test_vector_skill_storage(self):
        """Test if skills are stored in both JSON and VectorStore."""
        test_skill = HermesSkill(
            name="Test Skill",
            prompt_template="Test {task}",
            description="A test skill for validation",
            tags=["test", "unit"]
        )
        
        self.memory.store_skill(test_skill)
        
        # Check JSON storage
        skill_in_json = self.memory.get_skill(test_skill.skill_id)
        self.assertIsNotNone(skill_in_json)
        self.assertEqual(skill_in_json.name, "Test Skill")
        
        # Check Vector search (fallback to keyword in this mock environment is fine)
        results = self.memory.search_skills("validation test")
        self.assertTrue(len(results) > 0)
        # Verify the ID matches
        found_ids = [s.skill_id for s in results]
        self.assertIn(test_skill.skill_id, found_ids)

    async def test_sandbox_execution(self):
        """Test if sandbox executes commands and handles timeouts."""
        sandbox = get_sandbox()
        
        # Simple echo
        result = await sandbox.run_command("echo 'hello hermes'")
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "hello hermes")
        
        # Timeout test - using a very short timeout
        result = await sandbox.run_command("sleep 2", timeout=0.1)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)

    async def test_multi_model_fallback_structure(self):
        """Test if adapter is correctly using the multi-model runtime."""
        adapter = self.integration.adapter
        from shail.hermes.multi_model import MultiModelClient
        self.assertIsInstance(adapter.model_client, MultiModelClient)

if __name__ == "__main__":
    unittest.main()
