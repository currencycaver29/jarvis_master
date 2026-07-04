import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shail.hermes.observability import get_hermes_observability, reset_hermes_observability

class TestHermesObservability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_hermes_observability()
        self.obs = get_hermes_observability()

    async def asyncTearDown(self):
        reset_hermes_observability()

    async def test_emit_event_calls_broadcast(self):
        """Test that emit_event calls broadcast_event on ws_manager."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_event = AsyncMock()
        self.obs._ws_manager = mock_ws_manager

        event_type = "test_event"
        event_data = {"key": "value"}

        await self.obs.emit_event(event_type, event_data)

        # Assert broadcast_event was called with the prefixed event type and formatted data
        mock_ws_manager.broadcast_event.assert_called_once_with(
            "hermes_test_event",
            {
                "source": "hermes",
                "hermes_event_type": "test_event",
                "key": "value"
            }
        )

    async def test_emit_event_sync(self):
        """Test that emit_event_sync schedules the emit_event task."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_event = AsyncMock()
        self.obs._ws_manager = mock_ws_manager

        event_type = "sync_event"
        event_data = {"foo": "bar"}

        self.obs.emit_event_sync(event_type, event_data)
        
        # Allow the task queue in the running loop to execute
        await asyncio.sleep(0.01)

        mock_ws_manager.broadcast_event.assert_called_once_with(
            "hermes_sync_event",
            {
                "source": "hermes",
                "hermes_event_type": "sync_event",
                "foo": "bar"
            }
        )

if __name__ == "__main__":
    unittest.main()
