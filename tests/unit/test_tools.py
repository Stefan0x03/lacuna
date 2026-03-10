from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lacuna.sandbox.manager import DockerSandbox, ExecResult
from lacuna.sandbox.staging import stage_target
from lacuna.tools.base import BaseTool, ToolResult


class _EchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes the input message."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }

    def run(self, input: dict) -> ToolResult:
        return ToolResult(content=input["message"])


def test_tool_result_success():
    r = ToolResult(content="hello")
    assert r.content == "hello"
    assert r.is_error is False


def test_tool_result_error():
    r = ToolResult(content="bad", is_error=True)
    assert r.is_error is True


def test_tool_result_to_api_dict_success():
    r = ToolResult(content="ok")
    d = r.to_api_dict("toolu_123")
    assert d == {"type": "tool_result", "tool_use_id": "toolu_123", "content": "ok"}


def test_tool_result_to_api_dict_error():
    r = ToolResult(content="fail", is_error=True)
    d = r.to_api_dict("toolu_456")
    assert d["is_error"] is True
    assert d["tool_use_id"] == "toolu_456"


def test_base_tool_to_api_dict():
    tool = _EchoTool()
    d = tool.to_api_dict()
    assert d["name"] == "echo"
    assert d["description"] == "Echoes the input message."
    assert "input_schema" in d
    assert d["input_schema"]["type"] == "object"


def test_base_tool_run():
    tool = _EchoTool()
    result = tool.run({"message": "hello"})
    assert isinstance(result, ToolResult)
    assert result.content == "hello"
    assert result.is_error is False


def test_base_tool_is_abstract():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ExecResult unit tests
# ---------------------------------------------------------------------------


def test_exec_result_fields():
    r = ExecResult(stdout="out", stderr="err", exit_code=0)
    assert r.stdout == "out"
    assert r.stderr == "err"
    assert r.exit_code == 0
    assert r.timed_out is False


def test_exec_result_timed_out():
    r = ExecResult(stdout="", stderr="", exit_code=1, timed_out=True)
    assert r.timed_out is True


# ---------------------------------------------------------------------------
# DockerSandbox unit tests (docker SDK fully mocked via sys.modules)
# ---------------------------------------------------------------------------


def _make_mock_docker_module() -> MagicMock:
    """Build a minimal fake 'docker' module."""
    mock_docker = MagicMock()
    mock_docker.__name__ = "docker"

    class _NotFound(Exception):
        pass

    mock_docker.errors = MagicMock()
    mock_docker.errors.NotFound = _NotFound
    return mock_docker


def test_docker_sandbox_start_creates_container(tmp_path: Path):
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.containers.get.side_effect = mock_docker.errors.NotFound("not found")

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        sandbox.start()

    mock_client.containers.run.assert_called_once()
    call_kwargs = mock_client.containers.run.call_args
    assert call_kwargs.kwargs["network_mode"] == "none"
    assert call_kwargs.kwargs["cap_drop"] == ["ALL"]
    assert call_kwargs.kwargs["detach"] is True
    assert call_kwargs.kwargs["tty"] is True


def test_docker_sandbox_exec_success(tmp_path: Path):
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    mock_container = MagicMock()
    mock_container.exec_run.return_value = (0, (b"hello\n", b""))
    mock_client.containers.get.return_value = mock_container

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        result = sandbox.exec("echo hello")

    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.timed_out is False


def test_docker_sandbox_exec_error_exit_code(tmp_path: Path):
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    mock_container = MagicMock()
    mock_container.exec_run.return_value = (1, (b"", b"error msg"))
    mock_client.containers.get.return_value = mock_container

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        result = sandbox.exec("false")

    assert result.exit_code == 1
    assert result.stderr == "error msg"
    assert result.timed_out is False


def test_docker_sandbox_is_running_true(tmp_path: Path):
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    mock_container = MagicMock()
    mock_container.status = "running"
    mock_client.containers.get.return_value = mock_container

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        assert sandbox.is_running() is True


def test_docker_sandbox_is_running_false(tmp_path: Path):
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.containers.get.side_effect = mock_docker.errors.NotFound("not found")

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        assert sandbox.is_running() is False


# ---------------------------------------------------------------------------
# stage_target unit tests
# ---------------------------------------------------------------------------


def test_stage_target_local(tmp_path: Path):
    from lacuna.config import SourceSpec, TargetSpec

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.c").write_text("int main(void){return 0;}")

    workspace = tmp_path / "workspace"
    spec = TargetSpec(
        name="mylib",
        version="1.0",
        source=SourceSpec(type="local", path=str(src)),
        language="c",
    )

    dst = stage_target(spec, workspace)

    assert dst == workspace / "mylib"
    assert dst.is_dir()
    assert (dst / "main.c").read_text() == "int main(void){return 0;}"


def test_stage_target_unsupported_type(tmp_path: Path):
    from lacuna.config import SourceSpec, TargetSpec

    spec = TargetSpec(
        name="mylib",
        version="1.0",
        source=SourceSpec(type="ftp", url="ftp://example.com/mylib.tar.gz"),
        language="c",
    )

    with pytest.raises(ValueError, match="unsupported source type"):
        stage_target(spec, tmp_path / "workspace")


# ===========================================================================
# Helpers shared by tool tests
# ===========================================================================


def _make_sandbox(exec_results: list[ExecResult], tmp_path: Path) -> DockerSandbox:
    """Return a DockerSandbox whose exec() returns items from exec_results in order."""
    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)

    sandbox.exec = MagicMock(side_effect=exec_results)  # type: ignore[method-assign]
    return sandbox


# ===========================================================================
# ThinkTool
# ===========================================================================


def test_think_returns_thought(tmp_path: Path):
    from lacuna.tools.think import ThinkTool

    tool = ThinkTool()
    result = tool.run({"thought": "I should check for buffer overflows."})
    assert result.is_error is False
    assert result.content == "I should check for buffer overflows."


# ===========================================================================
# BashTool
# ===========================================================================


def test_bash_success(tmp_path: Path):
    from lacuna.tools.shell import BashTool

    sb = _make_sandbox([ExecResult(stdout="hello\n", stderr="", exit_code=0)], tmp_path)
    tool = BashTool(sandbox=sb)
    result = tool.run({"command": "echo hello"})
    assert result.is_error is False
    assert "[exit_code: 0]" in result.content
    assert "hello" in result.content


def test_bash_timeout(tmp_path: Path):
    from lacuna.tools.shell import BashTool

    sb = _make_sandbox(
        [ExecResult(stdout="partial", stderr="", exit_code=1, timed_out=True)], tmp_path
    )
    tool = BashTool(sandbox=sb)
    result = tool.run({"command": "sleep 999"})
    assert result.is_error is True
    assert "timed out" in result.content.lower()
    assert "partial" in result.content


def test_bash_error_exit(tmp_path: Path):
    from lacuna.tools.shell import BashTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="command not found", exit_code=127)], tmp_path)
    tool = BashTool(sandbox=sb)
    result = tool.run({"command": "badcmd"})
    assert result.is_error is False  # non-zero exit is still returned, not an error
    assert "[exit_code: 127]" in result.content
    assert "command not found" in result.content


# ===========================================================================
# ReadFileTool
# ===========================================================================


def test_read_file_success(tmp_path: Path):
    from lacuna.tools.filesystem import ReadFileTool

    sb = _make_sandbox([ExecResult(stdout="file contents\n", stderr="", exit_code=0)], tmp_path)
    tool = ReadFileTool(sandbox=sb)
    result = tool.run({"path": "/workspace/foo.c"})
    assert result.is_error is False
    assert result.content == "file contents\n"
    cmd = sb.exec.call_args[0][0]
    assert "cat" in cmd
    assert "/workspace/foo.c" in cmd


def test_read_file_error(tmp_path: Path):
    from lacuna.tools.filesystem import ReadFileTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="No such file", exit_code=1)], tmp_path)
    tool = ReadFileTool(sandbox=sb)
    result = tool.run({"path": "/workspace/missing.c"})
    assert result.is_error is True
    assert "No such file" in result.content


# ===========================================================================
# WriteFileTool
# ===========================================================================


def test_write_file_success(tmp_path: Path):
    import base64

    from lacuna.tools.filesystem import WriteFileTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="", exit_code=0)], tmp_path)
    tool = WriteFileTool(sandbox=sb)
    result = tool.run({"path": "/workspace/out.c", "content": "int main(){}"})
    assert result.is_error is False
    assert "Written" in result.content

    cmd = sb.exec.call_args[0][0]
    expected_b64 = base64.b64encode(b"int main(){}").decode()
    assert expected_b64 in cmd


def test_write_file_error(tmp_path: Path):
    from lacuna.tools.filesystem import WriteFileTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="permission denied", exit_code=1)], tmp_path)
    tool = WriteFileTool(sandbox=sb)
    result = tool.run({"path": "/root/out.c", "content": "x"})
    assert result.is_error is True
    assert "permission denied" in result.content


# ===========================================================================
# ListDirectoryTool
# ===========================================================================


def test_list_directory_success(tmp_path: Path):
    from lacuna.tools.filesystem import ListDirectoryTool

    listing = "d /workspace\nf /workspace/main.c\n"
    sb = _make_sandbox([ExecResult(stdout=listing, stderr="", exit_code=0)], tmp_path)
    tool = ListDirectoryTool(sandbox=sb)
    result = tool.run({"path": "/workspace"})
    assert result.is_error is False
    assert result.content == listing


def test_list_directory_error(tmp_path: Path):
    from lacuna.tools.filesystem import ListDirectoryTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="No such file", exit_code=1)], tmp_path)
    tool = ListDirectoryTool(sandbox=sb)
    result = tool.run({"path": "/nonexistent"})
    assert result.is_error is True
    assert "No such file" in result.content


# ===========================================================================
# SearchCodeTool
# ===========================================================================


def test_search_code_matches(tmp_path: Path):
    from lacuna.tools.search import SearchCodeTool

    output = "/workspace/foo.c:10:  strcpy(buf, src);\n"
    sb = _make_sandbox([ExecResult(stdout=output, stderr="", exit_code=0)], tmp_path)
    tool = SearchCodeTool(sandbox=sb)
    result = tool.run({"pattern": "strcpy", "path": "/workspace"})
    assert result.is_error is False
    assert "strcpy" in result.content


def test_search_code_no_matches(tmp_path: Path):
    from lacuna.tools.search import SearchCodeTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="", exit_code=1)], tmp_path)
    tool = SearchCodeTool(sandbox=sb)
    result = tool.run({"pattern": "strcpy", "path": "/workspace"})
    assert result.is_error is False
    assert "No matches" in result.content


def test_search_code_rg_error(tmp_path: Path):
    from lacuna.tools.search import SearchCodeTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="rg: invalid path", exit_code=2)], tmp_path)
    tool = SearchCodeTool(sandbox=sb)
    result = tool.run({"pattern": "strcpy", "path": "/bad"})
    assert result.is_error is True
    assert "invalid path" in result.content


# ===========================================================================
# GitLogTool
# ===========================================================================


def test_git_log_basic(tmp_path: Path):
    from lacuna.tools.git_tools import GitLogTool

    log_output = "abc123|Alice|2024-01-01|Fix buffer overflow\n"
    sb = _make_sandbox([ExecResult(stdout=log_output, stderr="", exit_code=0)], tmp_path)
    tool = GitLogTool(sandbox=sb)
    result = tool.run({"repo_path": "/workspace/libfoo"})
    assert result.is_error is False
    assert "abc123" in result.content
    cmd = sb.exec.call_args[0][0]
    assert "git_log" not in cmd
    assert "git" in cmd
    assert "/workspace/libfoo" in cmd


def test_git_log_with_optional_args(tmp_path: Path):
    from lacuna.tools.git_tools import GitLogTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="", exit_code=0)], tmp_path)
    tool = GitLogTool(sandbox=sb)
    result = tool.run(
        {
            "repo_path": "/workspace/libfoo",
            "n": 5,
            "since": "2024-01-01",
            "author": "Alice",
            "file_path": "src/buf.c",
        }
    )
    assert result.is_error is False
    cmd = sb.exec.call_args[0][0]
    assert "2024-01-01" in cmd
    assert "Alice" in cmd
    assert "src/buf.c" in cmd


# ===========================================================================
# GitShowTool
# ===========================================================================


def test_git_show_ref_only(tmp_path: Path):
    from lacuna.tools.git_tools import GitShowTool

    diff = "diff --git a/foo.c b/foo.c\n"
    sb = _make_sandbox([ExecResult(stdout=diff, stderr="", exit_code=0)], tmp_path)
    tool = GitShowTool(sandbox=sb)
    result = tool.run({"repo_path": "/workspace/libfoo", "ref": "abc123"})
    assert result.is_error is False
    assert "diff" in result.content
    cmd = sb.exec.call_args[0][0]
    assert "abc123" in cmd


def test_git_show_ref_with_file(tmp_path: Path):
    from lacuna.tools.git_tools import GitShowTool

    content = "int main(){}\n"
    sb = _make_sandbox([ExecResult(stdout=content, stderr="", exit_code=0)], tmp_path)
    tool = GitShowTool(sandbox=sb)
    result = tool.run(
        {"repo_path": "/workspace/libfoo", "ref": "abc123", "file_path": "src/main.c"}
    )
    assert result.is_error is False
    cmd = sb.exec.call_args[0][0]
    assert "abc123:src/main.c" in cmd


# ===========================================================================
# GitBlameTool
# ===========================================================================


def test_git_blame_no_range(tmp_path: Path):
    from lacuna.tools.git_tools import GitBlameTool

    blame = "abc123 (Alice 2024-01-01  1) int main(){}\n"
    sb = _make_sandbox([ExecResult(stdout=blame, stderr="", exit_code=0)], tmp_path)
    tool = GitBlameTool(sandbox=sb)
    result = tool.run({"repo_path": "/workspace/libfoo", "file_path": "main.c"})
    assert result.is_error is False
    cmd = sb.exec.call_args[0][0]
    assert "-L" not in cmd
    assert "main.c" in cmd


def test_git_blame_with_range(tmp_path: Path):
    from lacuna.tools.git_tools import GitBlameTool

    blame = "abc123 (Alice 2024-01-01  5) strcpy(buf, src);\n"
    sb = _make_sandbox([ExecResult(stdout=blame, stderr="", exit_code=0)], tmp_path)
    tool = GitBlameTool(sandbox=sb)
    result = tool.run(
        {"repo_path": "/workspace/libfoo", "file_path": "main.c", "start_line": 5, "end_line": 10}
    )
    assert result.is_error is False
    cmd = sb.exec.call_args[0][0]
    assert "-L" in cmd
    assert "5,10" in cmd


# ===========================================================================
# CompileTool
# ===========================================================================


def test_compile_success(tmp_path: Path):
    from lacuna.tools.fuzzing import CompileTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="", exit_code=0)], tmp_path)
    tool = CompileTool(sandbox=sb)
    result = tool.run({"source_path": "/workspace/fuzz.c", "output_path": "/workspace/fuzz"})
    assert result.is_error is False
    assert "Compilation successful" in result.content


def test_compile_sanitizer_flags(tmp_path: Path):
    from lacuna.tools.fuzzing import CompileTool

    sb = _make_sandbox([ExecResult(stdout="", stderr="", exit_code=0)], tmp_path)
    tool = CompileTool(sandbox=sb)
    result = tool.run(
        {
            "source_path": "/workspace/fuzz.c",
            "output_path": "/workspace/fuzz",
            "sanitizers": ["asan", "ubsan"],
        }
    )
    assert result.is_error is False
    cmd = sb.exec.call_args[0][0]
    assert "-fsanitize=address" in cmd
    assert "-fsanitize=undefined" in cmd


def test_compile_unknown_sanitizer(tmp_path: Path):
    from lacuna.tools.fuzzing import CompileTool

    sb = _make_sandbox([], tmp_path)
    tool = CompileTool(sandbox=sb)
    result = tool.run(
        {
            "source_path": "/workspace/fuzz.c",
            "output_path": "/workspace/fuzz",
            "sanitizers": ["bogus"],
        }
    )
    assert result.is_error is True
    assert "bogus" in result.content


# ===========================================================================
# RunFuzzerTool
# ===========================================================================


def test_run_fuzzer_afl_command_shape(tmp_path: Path):
    from lacuna.tools.fuzzing import RunFuzzerTool

    # exec is called three times: afl-fuzz run, fuzzer_stats cat, crash count find
    sb = _make_sandbox(
        [
            ExecResult(stdout="", stderr="", exit_code=0),
            ExecResult(stdout="execs_per_sec : 1234\npaths_total : 5\n", stderr="", exit_code=0),
            ExecResult(stdout="0\n", stderr="", exit_code=0),
        ],
        tmp_path,
    )
    tool = RunFuzzerTool(sandbox=sb)
    result = tool.run(
        {
            "fuzzer": "afl",
            "target_binary": "/workspace/fuzz",
            "corpus_dir": "/workspace/corpus",
            "output_dir": "/workspace/out",
            "duration": 60,
        }
    )
    assert result.is_error is False
    first_cmd = sb.exec.call_args_list[0][0][0]
    assert "afl-fuzz" in first_cmd
    assert "fuzzer: afl++" in result.content
    assert "duration_s: 60" in result.content
    assert "crashes:" in result.content
    assert "execs_per_sec:" in result.content
    assert "paths_total:" in result.content
    assert "output_dir:" in result.content


def test_run_fuzzer_libfuzzer_command_shape(tmp_path: Path):
    from lacuna.tools.fuzzing import RunFuzzerTool

    libfuzzer_output = "stat::number_of_executed_units: 99999\nstat::execs_per_sec: 2000\n"
    sb = _make_sandbox(
        [
            ExecResult(stdout=libfuzzer_output, stderr="", exit_code=0),
            ExecResult(stdout="0\n", stderr="", exit_code=0),
        ],
        tmp_path,
    )
    tool = RunFuzzerTool(sandbox=sb)
    result = tool.run(
        {
            "fuzzer": "libfuzzer",
            "target_binary": "/workspace/fuzz",
            "corpus_dir": "/workspace/corpus",
            "output_dir": "/workspace/out",
            "duration": 60,
        }
    )
    assert result.is_error is False
    first_cmd = sb.exec.call_args_list[0][0][0]
    assert "/workspace/fuzz" in first_cmd
    assert "-max_total_time=60" in first_cmd
    assert "fuzzer: libfuzzer" in result.content
    assert "duration_s: 60" in result.content
    assert "crashes:" in result.content
    assert "execs_per_sec:" in result.content
    assert "paths_total:" in result.content
    assert "output_dir:" in result.content


# ===========================================================================
# ReadCrashTool
# ===========================================================================


def test_read_crash_command_shape(tmp_path: Path):
    import shlex

    from lacuna.tools.fuzzing import ReadCrashTool

    crash_output = "File: /workspace/out/crash-abc\nSize: 4 bytes (showing first 4)\n"
    sb = _make_sandbox([ExecResult(stdout=crash_output, stderr="", exit_code=0)], tmp_path)
    tool = ReadCrashTool(sandbox=sb)
    crash_path = "/workspace/out/crash-abc"
    result = tool.run({"crash_path": crash_path})
    assert result.is_error is False

    cmd = sb.exec.call_args[0][0]
    assert "python3 -c" in cmd
    # crash_path must appear as a separate quoted argument, not embedded in the script
    assert shlex.quote(crash_path) in cmd


# ===========================================================================
# EmitFindingTool
# ===========================================================================


def test_emit_finding_appended_to_list(tmp_path: Path):
    from lacuna.tools.report_tool import EmitFindingTool, Finding

    findings: list[Finding] = []
    tool = EmitFindingTool(findings=findings)
    result = tool.run(
        {
            "title": "Buffer Overflow",
            "severity": "high",
            "description": "Unchecked strcpy call.",
        }
    )
    assert result.is_error is False
    assert len(findings) == 1
    assert findings[0].title == "Buffer Overflow"
    assert "HIGH" in result.content


def test_emit_finding_all_fields_stored(tmp_path: Path):
    from lacuna.tools.report_tool import EmitFindingTool, Finding

    findings: list[Finding] = []
    tool = EmitFindingTool(findings=findings)
    tool.run(
        {
            "title": "Use After Free",
            "severity": "critical",
            "description": "UAF in free_node().",
            "location": "src/tree.c:42",
            "recommendation": "Use a safe allocator.",
            "cwe": "CWE-416",
        }
    )
    f = findings[0]
    assert f.severity == "critical"
    assert f.location == "src/tree.c:42"
    assert f.recommendation == "Use a safe allocator."
    assert f.cwe == "CWE-416"


def test_emit_finding_invalid_severity(tmp_path: Path):
    from lacuna.tools.report_tool import EmitFindingTool, Finding

    findings: list[Finding] = []
    tool = EmitFindingTool(findings=findings)
    result = tool.run({"title": "X", "severity": "extreme", "description": "Bad."})
    assert result.is_error is True
    assert "extreme" in result.content
    assert len(findings) == 0


# ===========================================================================
# build_tool_registry / tool_definitions
# ===========================================================================


def test_build_tool_registry_13_tools(tmp_path: Path):
    from lacuna.tools import Finding, build_tool_registry, tool_definitions
    from lacuna.tools.report_tool import Finding

    mock_docker = _make_mock_docker_module()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    with patch.dict(sys.modules, {"docker": mock_docker, "docker.errors": mock_docker.errors}):
        sandbox = DockerSandbox("lacuna-sandbox", tmp_path)
        findings: list[Finding] = []
        registry = build_tool_registry(sandbox=sandbox, findings=findings)
        defs = tool_definitions(sandbox=sandbox, findings=findings)

    assert len(registry) == 13
    assert len(defs) == 13
    for d in defs:
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d
