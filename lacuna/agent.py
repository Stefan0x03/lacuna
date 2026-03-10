from __future__ import annotations

import sys
from dataclasses import dataclass

import anthropic

from lacuna.config import ScanConfig
from lacuna.context import trim_messages
from lacuna.prompts import build_initial_user_message, build_system_prompt
from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools import Finding, build_tool_registry
from lacuna.tools.base import ToolResult


@dataclass
class ScanResult:
    findings: list[Finding]
    messages: list[dict]
    input_tokens: int
    output_tokens: int
    iterations: int
    model: str


class VulnerabilityAgent:
    def __init__(self, config: ScanConfig, sandbox: DockerSandbox) -> None:
        self._config = config
        self._sandbox = sandbox
        self._client = anthropic.Anthropic()
        self._findings: list[Finding] = []
        self._tool_registry = build_tool_registry(
            sandbox=sandbox,
            findings=self._findings,
            timeout=config.timeout_per_tool,
        )

    def scan(self) -> ScanResult:
        """Run the vulnerability scan and return a ScanResult."""
        system = build_system_prompt(self._config.target_spec)
        workspace_path = f"/workspace/{self._config.target_spec.name}"

        messages: list[dict] = [
            {
                "role": "user",
                "content": build_initial_user_message(self._config.target_spec, workspace_path),
            }
        ]

        tool_defs = [tool.to_api_dict() for tool in self._tool_registry.values()]

        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0

        while iterations < self._config.max_iterations:
            iterations += 1

            messages = trim_messages(messages, max_input_tokens=180_000)

            try:
                response = self._client.messages.create(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    system=system,
                    messages=messages,
                    tools=tool_defs,
                )
            except anthropic.APIError as e:
                print(f"[lacuna] API error: {e}", file=sys.stderr)
                break

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            content_dicts = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": content_dicts})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                print(
                    f"[lacuna] Unexpected stop_reason: {response.stop_reason!r}",
                    file=sys.stderr,
                )
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if self._config.verbose:
                    print(f"\n[tool_use] {block.name}")
                    print(f"  input: {block.input}")
                tool = self._tool_registry.get(block.name)
                if tool is None:
                    result = ToolResult(is_error=True, content=f"Unknown tool: {block.name!r}")
                else:
                    result = tool.run(block.input)
                if self._config.verbose:
                    prefix = "ERROR: " if result.is_error else ""
                    print(f"[tool_result] {prefix}{result.content[:300]}")
                tool_results.append(result.to_api_dict(block.id))

            messages.append({"role": "user", "content": tool_results})

        return ScanResult(
            findings=self._findings,
            messages=messages,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            iterations=iterations,
            model=self._config.model,
        )
