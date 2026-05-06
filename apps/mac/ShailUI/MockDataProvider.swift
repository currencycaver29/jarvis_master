import Foundation

enum MockDataProvider {
#if DEBUG
    // Demo graph state — only available in debug/development builds.
    // Never ships to production. Use for SwiftUI previews and local testing.
    static let demoGraphState: GraphState = GraphState(from: [
        "task_description": "Demo: Analyze codebase and generate report",
        "current_step": 2,
        "status": "idle",
        "current_node": "execute_step",
        "nodes": ["master", "planner", "execute_step", "verifier"],
        "edges": [
            ["from": "master",       "to": "planner"],
            ["from": "planner",      "to": "execute_step"],
            ["from": "execute_step", "to": "verifier"],
            ["from": "verifier",     "to": "master"]
        ] as [[String: Any]],
        "plan_steps": [
            ["step_id": "step-1", "description": "Analyze repository structure",
             "step_type": "analysis", "executed": true, "success": true],
            ["step_id": "step-2", "description": "Identify key components",
             "step_type": "analysis", "executed": true, "success": true],
            ["step_id": "step-3", "description": "Generate summary report",
             "step_type": "action",   "executed": false]
        ] as [[String: Any]],
        "step_count": 3,
        "current_step_index": 2
    ])
#endif

    static let offlineReply = """
⚠️ SHAIL is offline — no backend detected.

I can't process your request right now. Here's how to get back online:

1. Run: bash ~/jarvis_master/start_shail.sh
2. Make sure Ollama is running: ollama serve
3. Make sure Gemma 4 is pulled: ollama pull gemma4:e4b

The Bird's Eye view on the right shows a demo of how SHAIL looks when live.
"""

    static func errorReply(for error: Error) -> String {
        let msg = error.localizedDescription
        if msg.contains("504") || msg.contains("timeout") || msg.contains("timed out") {
            return """
⚠️ SHAIL timed out — Gemma 4 took too long to respond.

Gemma 4 (gemma4:e4b) is a large model — first response may take 30–60 seconds.

1. Wait a moment and try again
2. Check Ollama: ollama ps (should show gemma4:e4b running)
3. Restart: menubar ⚡ → "Stop Services" then "Start Services"
"""
        }
        if msg.contains("404") || msg.contains("Not Found") {
            return """
⚠️ SHAIL backend not running or outdated.

The API server needs to be started:

1. Run: bash ~/jarvis_master/start_shail.sh
2. Or start manually: cd ~/jarvis_master/apps/shail && uvicorn main:app --port 8000
3. Check Ollama: ollama serve (in a separate terminal)
"""
        }
        if msg.contains("connection refused") || msg.contains("Could not connect") {
            return """
⚠️ Cannot reach SHAIL backend (connection refused).

Start the backend:

1. Run: bash ~/jarvis_master/start_shail.sh
2. Verify: curl http://localhost:8000/health
"""
        }
        return """
⚠️ Something went wrong with SHAIL (\(msg)).

To get back online:
1. Run: bash ~/jarvis_master/start_shail.sh
2. Check Ollama is running: ollama serve
3. Verify API: curl http://localhost:8000/health
"""
    }
}
