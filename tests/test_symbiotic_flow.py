"""
Test script for Symbiotic Controller Flow
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append("/Users/reyhan/shail_master")

# Mocking external deps that might be broken in env
sys.modules["langchain_google_genai"] = MagicMock()

from shail.orchestration.master_planner import MasterPlanner
from shail.core.types import TaskRequest

class TestSymbioticFlow(unittest.TestCase):
    
    def setUp(self):
        self.patchers = []
        
        # 1. Patch settings
        p_settings = patch('apps.shail.settings.get_settings')
        mock_settings = p_settings.start()
        mock_settings.return_value.gemini_model = "fake-model"
        mock_settings.return_value.gemini_api_key = "fake-key"
        self.patchers.append(p_settings)
        
        # 2. Patch planner LLM
        p_llm = patch('shail.orchestration.master_planner.ChatOllama')
        mock_llm = p_llm.start()
        mock_llm.return_value.invoke.return_value.content = '{"agent": "code", "confidence": 0.8, "rationale": "Symbiotic Loop detected anomaly: Traceback"}'
        self.patchers.append(p_llm)
        
        # 3. Patch detective LLM
        p_det_llm = patch('shail.agents.detective_agent.ChatOllama')
        mock_det_llm = p_det_llm.start()
        mock_det_llm.return_value.invoke.return_value.content = '{"passed": true, "anomalies": [], "bug_narrative": "", "confidence": 1.0}'
        self.patchers.append(p_det_llm)
        
        self.planner = MasterPlanner()
        
        # Populate mock events in the buffer for testing
        from shail.core.types import AccessibilityEvent
        import time
        ev = AccessibilityEvent(
            ts=time.time(),
            app_name="Terminal",
            role="AXStaticText",
            label="Traceback",
            value="runtime error: TimeoutError",
            focused=True,
            metadata={}
        )
        self.planner.buffer.consent_granted = True
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self.planner.buffer.add_accessibility_event(ev))

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()

    def test_symbiotic_error_flow(self):
        """
        Test the flow: User Query -> Grounding -> Vision (Anomaly) -> Code Agent
        """
        print("\n--- Testing Symbiotic flow for 'Fix the error' ---")
        
        # 1. User Query
        req = TaskRequest(text="Can you fix the error I saw in the terminal?", mode="auto")
        
        # 2. Execute
        # This should trigger _execute_symbiotic_loop because of "error" and "saw"
        decision = self.planner.route_request(req)
        
        print(f"Decision: {decision}")
        
        # 3. Assertions
        # The mock buffer in buffer.py has a story about a "TimeoutError"
        # The VisionAgent should find it and flag it as an anomaly
        # The MasterPlanner should then route to 'code' with high confidence
        self.assertEqual(decision.agent, "code")
        self.assertGreater(decision.confidence, 0.9)
        self.assertIn("Symbiotic Loop detected anomaly", decision.rationale)
        # Check for Traceback as text might be truncated
        self.assertIn("Traceback", decision.rationale)

    def test_grounding_search(self):
        """Test that grounding agent actually finds the event in the buffer."""
        print("\n--- Testing Grounding Agent search ---")
        # Use "runtime error" to differentiate from "python search"
        result = self.planner.grounding_agent.find_event("runtime error")
        self.assertIsNotNone(result.segment)
        self.assertIn("runtime error", result.segment.story.lower())
        print(f"Found story: {result.segment.story}")


if __name__ == '__main__':
    unittest.main()
