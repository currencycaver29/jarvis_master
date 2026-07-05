"""
Hermes Observability

Handles event broadcasting and telemetry for Hermes.
Connects Hermes events to SHAIL's WebSocket server.
"""

import logging
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

class HermesObservability:
    """
    Manages Hermes events and broadcasting.
    """

    def __init__(self):
        self._ws_manager = None
        self._initialized = False

    def _get_ws_manager(self):
        if self._ws_manager is not None:
            return self._ws_manager
        
        try:
            from apps.shail.websocket_server import websocket_manager
            self._ws_manager = websocket_manager
            self._initialized = True
            return self._ws_manager
        except (ImportError, AttributeError):
            logger.debug("WebSocket manager not available for Hermes observability")
            return None

    async def emit_event(self, event_type: str, data: Dict[str, Any]):
        """
        Emit a Hermes event to the WebSocket server.
        """
        ws_manager = self._get_ws_manager()
        if not ws_manager:
            return

        # Prepare Hermes event
        hermes_data = {
            "source": "hermes",
            "hermes_event_type": event_type,
            **data
        }

        try:
            # Check if we're in an async context
            await ws_manager.broadcast_event(f"hermes_{event_type}", hermes_data)
        except Exception as e:
            logger.warning(f"Failed to emit Hermes event: {e}")

    def emit_event_sync(self, event_type: str, data: Dict[str, Any]):
        """Synchronous version of emit_event."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit_event(event_type, data))
        except RuntimeError:
            # No running loop, just ignore or run in a new one if critical
            pass


# Singleton
_observability: Optional[HermesObservability] = None

def get_hermes_observability() -> HermesObservability:
    """Get singleton observability."""
    global _observability
    if _observability is None:
        _observability = HermesObservability()
    return _observability


def reset_hermes_observability() -> HermesObservability:
    """Reset observability singleton (for testing)."""
    global _observability
    _observability = HermesObservability()
    return _observability
