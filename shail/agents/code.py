from typing import List, Tuple
from shail.core.types import Artifact
from shail.agents.base import AbstractAgent
from shail.tools.os import open_app, close_app, run_command
from shail.tools.files import write_text_file, read_text_file, list_files, delete_file, create_directory
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from apps.shail.settings import get_settings


class CodeAgent(AbstractAgent):
    name = "code"
    capabilities = ["codegen", "run", "os_control", "file_ops"]

    def __init__(self):
        settings = get_settings()
        self.llm = ChatOllama(
            model=settings.ollama_chat_model,
            temperature=0.7,
        )
        self.tools = [
            open_app,
            close_app,
            run_command,
            write_text_file,
            read_text_file,
            list_files,
            delete_file,
            create_directory,
        ]
        
        # Use new langchain 1.x create_agent API (LangGraph-based)
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt="""You are Shail's CodeAgent. Execute MULTIPLE tools in sequence to complete tasks.

CRITICAL: Never say "one statement at a time" - you CAN execute multiple tools."""
        )

    def plan(self, text: str) -> str:
        return f"Analyzing request: {text[:100]}... Will use appropriate tools to execute."

    def act(self, text: str) -> Tuple[str, List[Artifact]]:
        """Execute the request using LangChain agent with tool calling."""
        try:
            result = self.agent.invoke({"messages": [("user", text)]})
            output = result.get("messages", [])[-1].content if result.get("messages") else "Task completed"
            
            artifacts = []
            return output, artifacts
        except Exception as e:
            error_msg = f"CodeAgent execution error: {str(e)}"
            return error_msg, []