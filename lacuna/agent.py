from __future__ import annotations

import sys
import time
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


def _budget_text(remaining: int, max_iterations: int) -> str:
    if remaining <= max(10, max_iterations // 5):
        urgency = (
            " Prioritise calling `emit_finding` for any confirmed vulnerabilities"
            " and then `end_turn`. Do not start new investigations."
        )
    elif remaining <= max_iterations // 2:
        urgency = (
            " Prioritise breadth over depth —"
            " avoid spending multiple iterations on a single function or hypothesis."
        )
    else:
        urgency = ""
    return f"[System: {remaining} of {max_iterations} iterations remaining.{urgency}]"


# How many times the agent loop itself retries after a rate-limit before giving up.
# Each wait doubles: 60s → 120s → 240s (capped at 600s).
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BASE_WAIT = 60  # seconds


class VulnerabilityAgent:
    def __init__(self, config: ScanConfig, sandbox: DockerSandbox) -> None:
        self._config = config
        self._sandbox = sandbox
        # max_retries=2 (SDK default): handles genuine transient blips (<1s).
        # We do NOT rely on the SDK for sustained rate limits because the SDK's
        # _calculate_retry_timeout caps retry-after at 60s — any Retry-After
        # header longer than 60s is silently ignored and the SDK falls back to
        # its 8s max exponential backoff, exhausting retries in ~15s total.
        # Agent-level retries below handle sustained org-level limits correctly.
        self._client = anthropic.Anthropic(max_retries=2)
        self._findings: list[Finding] = []
        self._tool_registry = build_tool_registry(
            sandbox=sandbox,
            findings=self._findings,
            timeout=config.timeout_per_tool,
        )

    def _call_api(
        self,
        messages: list[dict],
        system: str,
        tool_defs: list[dict],
    ) -> anthropic.types.Message:
        """Call the API with agent-level rate-limit retry (long waits, respects Retry-After)."""
        wait = _RATE_LIMIT_BASE_WAIT
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                return self._client.messages.create(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    system=system,
                    messages=messages,
                    tools=tool_defs,
                )
            except anthropic.RateLimitError as e:
                if attempt >= _RATE_LIMIT_RETRIES:
                    raise
                # Respect Retry-After without the SDK's 60s cap.
                try:
                    resp = getattr(e, "response", None)
                    if resp is not None:
                        header = resp.headers.get("retry-after") or resp.headers.get(
                            "retry-after-ms"
                        )
                        if header:
                            parsed = float(header)
                            # retry-after-ms is in milliseconds
                            if resp.headers.get("retry-after-ms"):
                                parsed /= 1000
                            wait = max(parsed, _RATE_LIMIT_BASE_WAIT)
                except (TypeError, ValueError):
                    pass
                wait = min(wait, 600)  # never wait more than 10 minutes
                print(
                    f"[lacuna] Rate limited — waiting {wait:.0f}s "
                    f"(attempt {attempt + 1}/{_RATE_LIMIT_RETRIES})...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                wait = min(wait * 2, 600)

        raise RuntimeError("unreachable")  # loop always returns or raises

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
            if iterations > 0 and self._config.inter_turn_delay > 0:
                time.sleep(self._config.inter_turn_delay)

            iterations += 1

            messages = trim_messages(messages, max_input_tokens=180_000)

            try:
                response = self._call_api(messages, system, tool_defs)
            except anthropic.RateLimitError as e:
                print(
                    f"[lacuna] Rate limit: all {_RATE_LIMIT_RETRIES} waits exhausted: {e}",
                    file=sys.stderr,
                )
                break
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

            if self._config.budget_awareness:
                remaining = self._config.max_iterations - iterations
                if remaining > 0:
                    tool_results.append(
                        {
                            "type": "text",
                            "text": _budget_text(remaining, self._config.max_iterations),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        return ScanResult(
            findings=self._findings,
            messages=messages,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            iterations=iterations,
            model=self._config.model,
        )
