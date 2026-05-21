import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# PRE-IMPORT MOCKS
patch('shail.memory.vector_store.get_vector_store', return_value=MagicMock()).start()
patch('chromadb.PersistentClient', return_value=MagicMock()).start()

test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_data"))
os.makedirs(test_dir, exist_ok=True)

class MockSettings:
    rag_chroma_path = os.path.join(test_dir, "chroma")
    rag_vector_store = "chroma"
    rag_embedding_dim = 768
    rag_pg_dsn = ""
    ollama_base_url = "http://localhost:11434"

patch('apps.shail.settings.get_settings', return_value=MockSettings()).start()

from shail.hermes.sandbox import ToolSandbox
mock_sb_obj = MagicMock(spec=ToolSandbox)
mock_sb_obj.base_dir = os.path.join(test_dir, "sandbox")
patch('shail.hermes.sandbox.get_sandbox', return_value=mock_sb_obj).start()
patch('shail.hermes.sandbox._sandbox', mock_sb_obj).start()

from shail.hermes.config import HermesConfig
mock_config = HermesConfig()
mock_config.sandbox_dir = os.path.join(test_dir, "sandbox")
patch('shail.hermes.config.get_hermes_config', return_value=mock_config).start()

from shail.hermes.reflection import get_reflection
from shail.hermes.persistent_memory import PersistentMemory
from shail.hermes.types import ExecutionTrace, ExecutionStatus, HermesSkill
import uuid

class TestHermesRecursive(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Override PersistentMemory to not use ChromaDB natively for this test
        # We just want to test the reflection logic, not the actual embedding
        self.memory = PersistentMemory(storage_dir=os.path.join(test_dir, "mem"))
        self.memory.trace_collection = MagicMock()
        self.memory.skill_collection = MagicMock()
        
        # Patch the embedding functions to avoid network calls to Ollama
        patch('shail.hermes.persistent_memory.embed_texts', return_value=[[0.1]*768]).start()
        patch('shail.hermes.persistent_memory.embed_query', return_value=[0.1]*768).start()
        
        self.reflection = get_reflection(self.memory)

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
        
        self.memory.store_trace(trace)
        
        # Assert that upsert was called on the mock trace_collection
        self.memory.trace_collection.upsert.assert_called_once()

if __name__ == "__main__":
    unittest.main()
