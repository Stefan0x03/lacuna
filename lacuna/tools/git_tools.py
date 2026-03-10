from __future__ import annotations

import shlex

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool, ToolResult


class GitLogTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show git commit history for a repository, optionally filtered."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository."},
                "n": {"type": "integer", "description": "Number of commits (default 20)."},
                "file_path": {
                    "type": "string",
                    "description": "Filter commits touching this file.",
                },
                "since": {
                    "type": "string",
                    "description": "Show commits since date, e.g. '2024-01-01'.",
                },
                "author": {"type": "string", "description": "Filter by author name/email."},
            },
            "required": ["repo_path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            repo_path = input["repo_path"]
            n = input.get("n", 20)
            file_path = input.get("file_path")
            since = input.get("since")
            author = input.get("author")

            cmd_parts = [
                "git",
                "-C",
                shlex.quote(repo_path),
                "log",
                "--format=%H|%an|%ad|%s",
                "--date=short",
                "-n",
                str(n),
            ]
            if since:
                cmd_parts += [f"--since={shlex.quote(since)}"]
            if author:
                cmd_parts += [f"--author={shlex.quote(author)}"]
            if file_path:
                cmd_parts += ["--", shlex.quote(file_path)]

            result = self._sandbox.exec(" ".join(cmd_parts))
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr or result.stdout)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


class GitShowTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "git_show"

    @property
    def description(self) -> str:
        return "Show a commit diff or the contents of a file at a specific git ref."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository."},
                "ref": {"type": "string", "description": "Commit hash or ref to show."},
                "file_path": {
                    "type": "string",
                    "description": "Show this file at the given ref (optional).",
                },
            },
            "required": ["repo_path", "ref"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            repo_path = input["repo_path"]
            ref = input["ref"]
            file_path = input.get("file_path")

            target = f"{ref}:{file_path}" if file_path else ref
            cmd = f"git -C {shlex.quote(repo_path)} show {shlex.quote(target)}"

            result = self._sandbox.exec(cmd)
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr or result.stdout)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


class GitBlameTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "git_blame"

    @property
    def description(self) -> str:
        return "Show what revision and author last modified each line of a file."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository."},
                "file_path": {"type": "string", "description": "File to blame."},
                "start_line": {"type": "integer", "description": "First line of range."},
                "end_line": {"type": "integer", "description": "Last line of range."},
            },
            "required": ["repo_path", "file_path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            repo_path = input["repo_path"]
            file_path = input["file_path"]
            start_line = input.get("start_line")
            end_line = input.get("end_line")

            cmd_parts = ["git", "-C", shlex.quote(repo_path), "blame"]
            if start_line and end_line:
                cmd_parts += ["-L", f"{start_line},{end_line}"]
            cmd_parts += ["--", shlex.quote(file_path)]

            result = self._sandbox.exec(" ".join(cmd_parts))
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr or result.stdout)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
