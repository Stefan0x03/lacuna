from __future__ import annotations

import shlex

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool, ToolResult


class SearchCodeTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return "Search for a pattern in the codebase using ripgrep."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex or literal pattern."},
                "path": {"type": "string", "description": "Directory or file to search."},
                "glob": {"type": "string", "description": "File glob filter (e.g. '*.c')."},
                "max_results": {
                    "type": "integer",
                    "description": "Max number of matches (default 50).",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context around each match (default 0).",
                },
            },
            "required": ["pattern", "path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            pattern = input["pattern"]
            path = input["path"]
            glob = input.get("glob")
            max_results = input.get("max_results", 50)
            context_lines = input.get("context_lines", 0)

            cmd_parts = ["rg", "--no-heading", "-n"]
            if context_lines:
                cmd_parts += ["-C", str(context_lines)]
            if glob:
                cmd_parts += ["--glob", shlex.quote(glob)]
            cmd_parts += ["-m", str(max_results)]
            cmd_parts += ["--", shlex.quote(pattern), shlex.quote(path)]
            cmd = " ".join(cmd_parts)

            result = self._sandbox.exec(cmd)
            if result.exit_code == 0:
                return ToolResult(content=result.stdout)
            if result.exit_code == 1:
                return ToolResult(content="No matches found.")
            return ToolResult(is_error=True, content=result.stderr)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
