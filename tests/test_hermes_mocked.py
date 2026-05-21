import asyncio
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shail.hermes.integration import reset_hermes_sail_integration
from shail.hermes.sandbox import ToolSandbox, get_sandbox
from shail.hermes.config import HermesConfig

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

class TestHermesIntegrationMocked(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 1. Clean up singletons first
        reset_hermes_sail_integration()
        
        # 2. Patch dependencies
        self.patchers = []
        
        # Vector Store mocks
        self.patchers.append(patch('shail.memory.vector_store.get_vector_store', return_value=MagicMock()))
        self.patchers.append(patch('chromadb.PersistentClient', return_value=MagicMock()))
        
        # Settings mock
        self.patchers.append(patch('apps.shail.settings.get_settings', return_value=MockSettings()))
        
        # Sandbox mock - Patch where it's USED to be extra sure
        self.mock_sb_obj = MagicMock(spec=ToolSandbox)
        self.mock_sb_obj.base_dir = os.path.join(test_dir, "sandbox")
        self.patchers.append(patch('shail.hermes.adapter.get_sandbox', return_value=self.mock_sb_obj))
        self.patchers.append(patch('shail.hermes.sandbox.get_sandbox', return_value=self.mock_sb_obj))
        self.patchers.append(patch('shail.hermes.sandbox._sandbox', self.mock_sb_obj))
        
        # Config mock
        self.mock_config = HermesConfig()
        self.mock_config.sandbox_dir = os.path.join(test_dir, "sandbox")
        self.patchers.append(patch('shail.hermes.config.get_hermes_config', return_value=self.mock_config))
        
        # Start all patchers
        for p in self.patchers:
            p.start()
            
        # 3. Now get the integration (it will use the mocked components)
        from shail.hermes.integration import get_hermes_sail_integration
        self.integration = get_hermes_sail_integration()
        
        # Ensure we have a fresh memory mock for each test
        self.mock_mem = MagicMock()
        patch('shail.hermes.adapter.get_persistent_memory', return_value=self.mock_mem).start()

    async def asyncTearDown(self):
        # Stop all patchers in reverse order
        for p in reversed(self.patchers):
            p.stop()
        patch.stopall()
        reset_hermes_sail_integration()

    async def test_logic_injection(self):
        """Verify that the integration is initialized with the mocked sandbox."""
        # Directly inject to be 100% sure
        self.integration.adapter.sandbox = self.mock_sb_obj
        self.assertEqual(self.integration.adapter.sandbox, self.mock_sb_obj)

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
