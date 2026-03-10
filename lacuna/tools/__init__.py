from __future__ import annotations

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool
from lacuna.tools.filesystem import ListDirectoryTool, ReadFileTool, WriteFileTool
from lacuna.tools.fuzzing import CompileTool, ReadCrashTool, RunFuzzerTool
from lacuna.tools.git_tools import GitBlameTool, GitLogTool, GitShowTool
from lacuna.tools.report_tool import EmitFindingTool, Finding
from lacuna.tools.search import SearchCodeTool
from lacuna.tools.shell import BashTool
from lacuna.tools.think import ThinkTool

__all__ = ["build_tool_registry", "tool_definitions", "Finding"]


def build_tool_registry(
    sandbox: DockerSandbox,
    findings: list[Finding],
    timeout: int = 30,
) -> dict[str, BaseTool]:
    tools: list[BaseTool] = [
        ThinkTool(),
        BashTool(sandbox=sandbox, timeout=timeout),
        ReadFileTool(sandbox=sandbox),
        WriteFileTool(sandbox=sandbox),
        ListDirectoryTool(sandbox=sandbox),
        SearchCodeTool(sandbox=sandbox),
        GitLogTool(sandbox=sandbox),
        GitShowTool(sandbox=sandbox),
        GitBlameTool(sandbox=sandbox),
        CompileTool(sandbox=sandbox),
        RunFuzzerTool(sandbox=sandbox),
        ReadCrashTool(sandbox=sandbox),
        EmitFindingTool(findings=findings),
    ]
    return {tool.name: tool for tool in tools}


def tool_definitions(
    sandbox: DockerSandbox,
    findings: list[Finding],
    timeout: int = 30,
) -> list[dict]:
    return [t.to_api_dict() for t in build_tool_registry(sandbox, findings, timeout).values()]
