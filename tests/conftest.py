from __future__ import annotations

from pathlib import Path

import pytest

from lacuna.config import ScanConfig, SourceSpec, TargetSpec
from lacuna.context import TOOL_RESULT_KEEP_CHARS


@pytest.fixture
def minimal_target_spec() -> TargetSpec:
    return TargetSpec(
        name="test-lib",
        version="1.0.0",
        source=SourceSpec(type="local", path="/tmp/test-lib"),
        language="c",
    )


@pytest.fixture
def minimal_scan_config(tmp_path: Path, minimal_target_spec: TargetSpec) -> ScanConfig:
    return ScanConfig(
        target_spec=minimal_target_spec,
        model="claude-haiku-4-5-20251001",
        max_iterations=10,
        max_tokens=4096,
        sandbox_name="lacuna-sandbox",
        reports_dir=tmp_path,
        timeout_per_tool=30,
    )


@pytest.fixture
def sample_messages() -> list[dict]:
    long_content = "A" * (TOOL_RESULT_KEEP_CHARS + 1000)
    return [
        {
            "role": "user",
            "content": "Analyze this C library for vulnerabilities.",
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I'll start by exploring the codebase."},
                {
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "list_directory",
                    "input": {"path": "/workspace"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": long_content,
                },
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me read the main source file."},
                {
                    "type": "tool_use",
                    "id": "toolu_002",
                    "name": "read_file",
                    "input": {"path": "/workspace/src/main.c"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_002",
                    "content": "int main(void) { return 0; }",
                },
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looks clean. Let me check git history."},
                {
                    "type": "tool_use",
                    "id": "toolu_003",
                    "name": "git_log",
                    "input": {"path": "/workspace"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_003",
                    "content": "commit abc123\nAuthor: Dev\nDate: 2024-01-01\n\n    Initial commit",
                },
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "No suspicious commits. Scan complete."},
            ],
        },
    ]
