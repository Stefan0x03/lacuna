from __future__ import annotations

import base64
import shlex
from pathlib import Path

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file inside the sandbox."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "start_line": {"type": "integer", "description": "First line to read (1-based)."},
                "end_line": {"type": "integer", "description": "Last line to read (inclusive)."},
            },
            "required": ["path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            path = input["path"]
            start_line = input.get("start_line")
            end_line = input.get("end_line")
            if start_line and end_line:
                cmd = f"sed -n '{start_line},{end_line}p' -- {shlex.quote(path)}"
            else:
                cmd = f"cat -- {shlex.quote(path)}"
            result = self._sandbox.exec(cmd)
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr or result.stdout)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


class WriteFileTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file inside the sandbox."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to write."},
                "content": {"type": "string", "description": "File content to write."},
            },
            "required": ["path", "content"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            path = input["path"]
            content = input["content"]
            b64 = base64.b64encode(content.encode()).decode()
            parent = shlex.quote(str(Path(path).parent))
            dest = shlex.quote(path)
            cmd = f"mkdir -p {parent} && printf '%s' {shlex.quote(b64)} | base64 -d > {dest}"
            result = self._sandbox.exec(cmd)
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr)
            return ToolResult(content=f"Written {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


class ListDirectoryTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "List the directory tree inside the sandbox."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to list."},
                "depth": {"type": "integer", "description": "Max depth (default 3)."},
            },
            "required": ["path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            path = input["path"]
            depth = input.get("depth", 3)
            cmd = f"find {shlex.quote(path)} -maxdepth {depth} -printf '%y %p\n' | sort"
            result = self._sandbox.exec(cmd)
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
