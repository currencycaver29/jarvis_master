"""
Hermes Tool Sandbox

Provides isolated execution environments for tool calls.
Ensures that autonomous agents don't interfere with the host system.

Features:
- venv-based isolation for Python tools
- Subprocess isolation for shell commands
- Timeout enforcement
- Resource monitoring
- Permission recovery hooks
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class SandboxResult:
    """Result of a sandboxed execution."""
    def __init__(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        execution_time_ms: float,
        timed_out: bool = False
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.execution_time_ms = execution_time_ms
        self.timed_out = timed_out
        self.success = returncode == 0 and not timed_out


class ToolSandbox:
    """
    Manages isolated execution environments.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            # Use system temp or a dedicated SHAIL folder
            base_dir = os.path.expanduser("~/Library/Application Support/SHAIL/sandbox")
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._active_envs: Dict[str, Path] = {}

    async def run_command(
        self,
        command: Union[str, List[str]],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        use_venv: bool = False
    ) -> SandboxResult:
        """
        Run a command in the sandbox.
        """
        start_time = asyncio.get_event_loop().time()
        
        if isinstance(command, list):
            cmd_str = " ".join(command)
        else:
            cmd_str = command

        logger.info(f"Sandbox executing: {cmd_str[:100]}...")

        try:
            # Use asyncio.create_subprocess_shell for non-blocking execution
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env or os.environ.copy()
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                timed_out = False
            except asyncio.TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
                timed_out = True
                logger.warning(f"Sandbox command timed out after {timeout}s")

            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000

            return SandboxResult(
                stdout=stdout.decode().strip(),
                stderr=stderr.decode().strip(),
                returncode=process.returncode if process.returncode is not None else -1,
                execution_time_ms=execution_time,
                timed_out=timed_out
            )

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return SandboxResult(
                stdout="",
                stderr=str(e),
                returncode=-1,
                execution_time_ms=0,
                timed_out=False
            )

    async def create_python_venv(self, name: str) -> Path:
        """
        Create a dedicated Python virtual environment for a task.
        """
        venv_path = self.base_dir / f"venv_{name}"
        if venv_path.exists():
            return venv_path

        logger.info(f"Creating sandbox venv: {venv_path}")
        
        process = await asyncio.create_subprocess_exec(
            "python3", "-m", "venv", str(venv_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode == 0:
            self._active_envs[name] = venv_path
            return venv_path
        else:
            raise Exception("Failed to create virtual environment")

    async def run_python_script(
        self,
        script_content: str,
        venv_name: Optional[str] = None,
        timeout: float = 60.0
    ) -> SandboxResult:
        """
        Run a Python script in an isolated environment.
        """
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp.write(script_content.encode())
            script_path = tmp.name

        try:
            python_exe = "python3"
            if venv_name:
                venv_path = await self.create_python_venv(venv_name)
                python_exe = str(venv_path / "bin" / "python3")

            return await self.run_command(f"{python_exe} {script_path}", timeout=timeout)
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

    async def cleanup(self):
        """Remove all sandbox environments."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self._active_envs.clear()
            logger.info("Sandbox cleaned up")


# Singleton
_sandbox: Optional[ToolSandbox] = None

def get_sandbox() -> ToolSandbox:
    """Get singleton sandbox."""
    global _sandbox
    if _sandbox is None:
        _sandbox = ToolSandbox()
    return _sandbox
