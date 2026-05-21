import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shail.hermes.integration import get_hermes_sail_integration
from shail.hermes.types import ExecutionStatus
from shail.hermes.persistent_memory import get_persistent_memory

class TestHermesIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.integration = get_hermes_sail_integration()
        await self.integration.initialize()
        self.memory = get_persistent_memory()

    async def test_vector_skill_storage(self):
        """Test if skills are stored in both JSON and VectorStore."""
        from shail.hermes.types import HermesSkill
        
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
        
        # Check Vector search (semantic)
        # Note: This requires Ollama to be running for embedding. 
        # If Ollama is down, it falls back to zero-vectors but should still "work" via keyword fallback.
        results = self.memory.search_skills("validation test")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].skill_id, test_skill.skill_id)

    async def test_sandbox_execution(self):
        """Test if sandbox executes commands and handles timeouts."""
        from shail.hermes.sandbox import get_sandbox
        sandbox = get_sandbox()
        
        # Simple echo
        result = await sandbox.run_command("echo 'hello hermes'")
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "hello hermes")
        
        # Timeout test
        result = await sandbox.run_command("sleep 5", timeout=1.0)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)

    async def test_multi_model_fallback_structure(self):
        """Test if adapter is correctly using the multi-model runtime."""
        adapter = self.integration.adapter
        from shail.hermes.multi_model import MultiModelClient
        self.assertIsInstance(adapter.model_client, MultiModelClient)

if __name__ == "__main__":
    unittest.main()
