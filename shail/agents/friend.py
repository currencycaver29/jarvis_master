"""
FriendAgent - Conversational AI assistant with desktop control capabilities.

FriendAgent is designed for hands-free computer interaction and natural conversation.
It combines conversational AI with desktop automation tools.
"""

from typing import List, Tuple
from shail.core.types import Artifact
from shail.agents.base import AbstractAgent
from shail.tools.desktop import (
    move_mouse, click_mouse, type_text, press_key, press_hotkey, scroll_mouse,
    get_mouse_position, get_screen_size, focus_window, get_window_position, list_open_windows
)
from shail.tools.os import open_app, close_app
from shail.tools.monitor import (
    get_active_window,
    get_running_apps,
    get_screen_info,
    wait_for_window
)
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from apps.shail.settings import get_settings


class FriendAgent(AbstractAgent):
    """
    FriendAgent - Your friendly AI companion with desktop control.
    
    FriendAgent combines:
    - Natural, conversational personality
    - Desktop automation (mouse, keyboard, windows)
    - Multi-step task execution
    - Hands-free computer control
    """
    name = "friend"
    capabilities = ["desktop_control", "conversation", "automation", "hands_free"]

    def __init__(self):
        settings = get_settings()
        self.llm = ChatOllama(
            model=settings.ollama_chat_model,
            temperature=0.8,
        )
        
        # Desktop control and OS tools
        self.tools = [
            # Mouse control
            move_mouse,
            click_mouse,
            scroll_mouse,
            get_mouse_position,
            # Keyboard control
            type_text,
            press_key,
            press_hotkey,
            # Window management
            focus_window,
            get_window_position,
            list_open_windows,
            get_screen_size,
            # App control
            open_app,
            close_app,
            # Real-time monitoring
            get_active_window,
            get_running_apps,
            get_screen_info,
            wait_for_window,
        ]
        
        # Use new langchain 1.x create_agent API (LangGraph-based)
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt="""You are Shail's FriendAgent - a friendly, conversational AI assistant with desktop control.

CRITICAL: Never say "one statement at a time" - you CAN execute multiple tools.

Control mouse, keyboard, windows, and applications. Execute as many tools as needed.
Personality: Friendly, helpful, conversational."""
        )

    def plan(self, text: str) -> str:
        return f"Analyzing request: {text[:100]}... Will help with desktop control and conversation."

    def act(self, text: str) -> Tuple[str, List[Artifact]]:
        """Execute the request using LangChain agent with desktop tools."""
        print(f"[DEBUG FriendAgent.act] Starting execution: {text[:50]}")
        try:
            result = self.agent.invoke({"messages": [("user", text)]})
            print(f"[DEBUG FriendAgent.act] Agent result: {result}")
            output = result.get("messages", [])[-1].content if result.get("messages") else "Task completed"
            
            artifacts = []
            return output, artifacts
        except Exception as e:
            print(f"[DEBUG FriendAgent.act] Exception caught: {type(e).__name__}: {e}")
            error_msg = f"FriendAgent execution error: {str(e)}"
            return error_msg, []