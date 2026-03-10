from __future__ import annotations

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool, ToolResult


class BashTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox, timeout: int = 30) -> None:
        self._sandbox = sandbox
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Execute a shell command inside the sandbox container."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (overrides default).",
                },
            },
            "required": ["command"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            timeout = input.get("timeout", self._timeout)
            try:
                result = self._sandbox.exec(input["command"], timeout=timeout)
            except RuntimeError as e:
                return ToolResult(is_error=True, content=str(e))

            if result.timed_out:
                return ToolResult(
                    is_error=True,
                    content=(
                        f"Command timed out after {timeout}s.\nPartial stdout:\n{result.stdout}"
                    ),
                )

            parts = [f"[exit_code: {result.exit_code}]"]
            if result.stdout:
                parts.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                parts.append(f"STDERR:\n{result.stderr}")
            return ToolResult(content="\n".join(parts))
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
