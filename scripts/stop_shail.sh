#!/usr/bin/env bash
# stop_shail.sh — kill all SHAIL processes cleanly
set -e

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti ":$port" 2>/dev/null) || true
  if [ -n "$pids" ]; then
    echo "Stopping port $port (PID $pids)..."
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 1
    # Force-kill if still alive
    pids=$(lsof -ti ":$port" 2>/dev/null) || true
    [ -n "$pids" ] && echo "$pids" | xargs kill -KILL 2>/dev/null || true
  fi
}

echo "Stopping SHAIL..."
kill_port 8000   # FastAPI backend
kill_port 11434  # Ollama
kill_port 6379   # Redis (pro tier)
kill_port 8765   # CaptureService (pro tier)
kill_port 8766   # AccessibilityBridge (pro tier)

# Kill task worker by name
pkill -f "shail.workers.task_worker" 2>/dev/null || true

echo "Done. All SHAIL processes stopped."
