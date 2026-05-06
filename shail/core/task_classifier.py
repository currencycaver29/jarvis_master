"""Rule-based task classifier — routes user text to an agent slot."""

from __future__ import annotations

from typing import Literal

AgentSlot = Literal[
    "memory.save",
    "memory.search",
    "nav.assist",
    "action.execute",
    "vision.capture",
    "code.agent",
    "gemma.chat",
]

# Rules evaluated top-to-bottom. First match wins.
RULES: list[tuple[tuple[str, ...], AgentSlot]] = [
    (
        ("remember this", "save this", "store this", "keep this", "remember that"),
        "memory.save",
    ),
    (
        ("what did i", "recall ", "search memory", "find in memory", "from my memory", "what have i"),
        "memory.search",
    ),
    (
        ("how do i", "how to ", "where is ", "what is the way", "how can i", "where can i find"),
        "nav.assist",
    ),
    (
        ("open ", "launch ", "click ", "navigate to", "go to ", "switch to"),
        "action.execute",
    ),
    (
        ("screenshot", "what's on screen", "what is on screen", "see my screen", "capture screen"),
        "vision.capture",
    ),
    (
        ("write code", "debug ", "fix bug", "function ", "refactor ", "implement ", "build a script"),
        "code.agent",
    ),
]

# Model registry — swap models here without touching routing logic
# Sprint 6: chat + code use lightweight gemma3:4b-it-q4_K_M (~2.6 GB).
# Vision lazy-loads llava:7b only when Ghost Cursor invoked.
MODELS: dict[str, str] = {
    "gemma":  "gemma3:4b-it-q4_K_M",
    "code":   "gemma3:4b-it-q4_K_M",
    "vision": "llava:7b",
}


def classify(text: str) -> AgentSlot:
    """Return the agent slot for the given user text."""
    t = text.lower().strip()
    for keywords, slot in RULES:
        if any(k in t for k in keywords):
            return slot
    return "gemma.chat"
