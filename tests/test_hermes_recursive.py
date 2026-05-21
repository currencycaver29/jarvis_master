import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shail.hermes.integration import reset_hermes_sail_integration
from shail.hermes.reflection import reset_reflection, get_reflection
from shail.hermes.persistent_memory import PersistentMemory, reset_persistent_memory
from shail.hermes.types import ExecutionTrace, ExecutionStatus, HermesSkill
import uuid

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

class TestHermesRecursive(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 1. Clean up singletons
        reset_hermes_sail_integration()
        
        # 2. Patch dependencies
        self.patchers = []
        self.patchers.append(patch('shail.memory.vector_store.get_vector_store', return_value=MagicMock()))
        self.patchers.append(patch('chromadb.PersistentClient', return_value=MagicMock()))
        self.patchers.append(patch('apps.shail.settings.get_settings', return_value=MockSettings()))
        self.patchers.append(patch('shail.hermes.persistent_memory.embed_texts', return_value=[[0.1]*768]))
        self.patchers.append(patch('shail.hermes.persistent_memory.embed_query', return_value=[0.1]*768))
        
        for p in self.patchers:
            p.start()

        # 3. Create instances for testing
        self.memory = PersistentMemory(storage_dir=os.path.join(test_dir, "mem"))
        self.memory.trace_collection = MagicMock()
        self.memory.skill_collection = MagicMock()
        
        # Use reset_reflection to ensure we get a fresh instance with our test memory
        self.reflection = reset_reflection(self.memory)

    async def asyncTearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        patch.stopall()
        reset_hermes_sail_integration()

    async def test_skill_refinement(self):
        """Verify that a failing trace refines its associated skill."""
        # Create a mock skill
        skill = HermesSkill(
            name="Test Skill",
            prompt_template="Original Template",
            description="Test"
        )
        self.memory.store_skill(skill)
        
        # Create a failing trace that used this skill
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            task="do something impossible",
            status=ExecutionStatus.FAILED,
            error="API Rate Limit Exceeded",
            skill_used=skill.skill_id
        )
        
        # Reflect on the failure
        result = self.reflection.reflect(trace)
        
        self.assertTrue(result["skill_refined"])
        
        # Check if the skill template was modified
        refined_skill = self.memory.get_skill(skill.skill_id)
        self.assertIn("AVOID PREVIOUS ERROR: API Rate Limit Exceeded", refined_skill.prompt_template)

    async def test_trace_ingestion(self):
        """Verify that successful traces are vectorized into the trace_collection."""
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            task="do something possible",
            status=ExecutionStatus.COMPLETED,
            result="Success!",
            execution_time_ms=100
        )
        
        # Directly inject mock into the private field to bypass ensure_vector_store
        mock_coll = MagicMock()
        self.memory._trace_collection = mock_coll
        self.memory._vector_store = MagicMock() # Ensure _ensure_vector_store skips
        
        self.memory.store_trace(trace)
        
        # Assert that upsert was called on our specific mock
        mock_coll.upsert.assert_called_once()

if __name__ == "__main__":
    unittest.main()
