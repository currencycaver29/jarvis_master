import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# PRE-IMPORT MOCKS - HEAVY ONES
patch('shail.memory.vector_store.get_vector_store', return_value=MagicMock()).start()
patch('chromadb.PersistentClient', return_value=MagicMock()).start()

# FORCE SAFE DIRECTORIES BEFORE ANY IMPORTS
test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_data"))
os.makedirs(test_dir, exist_ok=True)

class MockSettings:
    rag_chroma_path = os.path.join(test_dir, "chroma")
    rag_vector_store = "chroma"
    rag_embedding_dim = 768
    rag_pg_dsn = ""
    ollama_base_url = "http://localhost:11434"

patch('apps.shail.settings.get_settings', return_value=MockSettings()).start()

# Mock get_sandbox GLOBAL to prevent the mkdir in __init__ from ever firing
from shail.hermes.sandbox import ToolSandbox
mock_sb_obj = MagicMock(spec=ToolSandbox)
mock_sb_obj.base_dir = os.path.join(test_dir, "sandbox")
patch('shail.hermes.sandbox.get_sandbox', return_value=mock_sb_obj).start()
patch('shail.hermes.sandbox._sandbox', mock_sb_obj).start()

# Mock get_hermes_config
from shail.hermes.config import HermesConfig
mock_config = HermesConfig()
mock_config.sandbox_dir = os.path.join(test_dir, "sandbox")
patch('shail.hermes.config.get_hermes_config', return_value=mock_config).start()

# Now import the rest
from shail.hermes.integration import get_hermes_sail_integration
from shail.hermes.adapter import HermesAdapter

class TestHermesIntegrationMocked(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Patch adapter creation to use mocked memory
        self.mock_mem = MagicMock()
        patch('shail.hermes.adapter.get_persistent_memory', return_value=self.mock_mem).start()
        
        self.integration = get_hermes_sail_integration()

    async def test_logic_injection(self):
        """Verify that the integration is initialized with the mocked sandbox."""
        self.assertEqual(self.integration.adapter.sandbox, mock_sb_obj)

    async def test_retry_logic(self):
        """Test the exponential backoff calculation."""
        from shail.hermes.types import RetryPolicy, RetryStrategy
        
        adapter = self.integration.adapter
        policy = RetryPolicy(strategy=RetryStrategy.EXPONENTIAL, base_delay_ms=100)
        
        self.assertEqual(adapter._calculate_delay(policy, 1), 100)
        self.assertEqual(adapter._calculate_delay(policy, 2), 200)
        self.assertEqual(adapter._calculate_delay(policy, 3), 400)

if __name__ == "__main__":
    unittest.main()
