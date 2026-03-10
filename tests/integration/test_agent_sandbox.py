from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from lacuna.sandbox.manager import DockerSandbox


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _image_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.images.get("lacuna-sandbox")
        return True
    except Exception:
        return False


_skip_no_docker = pytest.mark.skipif(not _docker_available(), reason="Docker not available")
_skip_no_image = pytest.mark.skipif(
    not (_docker_available() and _image_available()),
    reason="Docker not available or lacuna-sandbox image not built",
)
_skip_no_api_key = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
_skip_agent = pytest.mark.skipif(
    not (_docker_available() and _image_available() and os.getenv("ANTHROPIC_API_KEY")),
    reason="Docker, lacuna-sandbox image, and ANTHROPIC_API_KEY all required",
)


@_skip_no_image
def test_sandbox_start_stop(tmp_path):
    sandbox = DockerSandbox("lacuna-sandbox-test", tmp_path)
    try:
        sandbox.start()
        assert sandbox.is_running() is True
    finally:
        sandbox.stop()
    assert sandbox.is_running() is False


@_skip_no_image
def test_sandbox_exec_echo(tmp_path):
    sandbox = DockerSandbox("lacuna-sandbox-test", tmp_path)
    sandbox.start()
    try:
        result = sandbox.exec("echo hello")
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0
        assert result.timed_out is False
    finally:
        sandbox.stop()


@_skip_no_image
def test_sandbox_exec_nonzero_exit(tmp_path):
    sandbox = DockerSandbox("lacuna-sandbox-test", tmp_path)
    sandbox.start()
    try:
        result = sandbox.exec("exit 42")
        assert result.exit_code == 42
    finally:
        sandbox.stop()


@_skip_no_image
def test_sandbox_exec_timeout(tmp_path):
    sandbox = DockerSandbox("lacuna-sandbox-test", tmp_path)
    sandbox.start()
    try:
        result = sandbox.exec("sleep 60", timeout=1)
        assert result.timed_out is True
    finally:
        sandbox.stop()


@_skip_no_image
def test_sandbox_network_disabled(tmp_path):
    sandbox = DockerSandbox("lacuna-sandbox-test", tmp_path)
    sandbox.start()
    try:
        # curl is installed; with network_mode=none the kernel returns ENETUNREACH
        # immediately (no timeout needed) and curl exits non-zero
        result = sandbox.exec("curl -s --connect-timeout 1 http://example.com")
        assert result.exit_code != 0
    finally:
        sandbox.stop()


# ---------------------------------------------------------------------------
# Agent integration tests — session-scoped fixture runs one real scan
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def agent_scan_result(tmp_path_factory):
    """Run one real scan and share results across all agent integration tests."""
    if not (_docker_available() and _image_available() and os.getenv("ANTHROPIC_API_KEY")):
        pytest.skip("Docker, lacuna-sandbox image, and ANTHROPIC_API_KEY all required")

    reports_dir = tmp_path_factory.mktemp("reports")
    workspace_dir = tmp_path_factory.mktemp("workspace")

    # Copy tiny source into the session-scoped workspace
    src = Path("workspace_src/tiny")
    dst = workspace_dir / "tiny"
    shutil.copytree(src, dst)

    from lacuna.agent import VulnerabilityAgent
    from lacuna.config import load_config
    from lacuna.report import make_stem, write_messages_json, write_report
    from lacuna.sandbox.manager import DockerSandbox

    target_yaml = Path("targets/test_tiny.yaml")
    config = load_config(
        target_yaml,
        model="claude-haiku-4-5-20251001",
        max_iterations=10,
        reports_dir=reports_dir,
        workspace_dir=workspace_dir,
    )

    sandbox = DockerSandbox(config.sandbox_name, config.workspace_dir)
    sandbox.start()
    try:
        result = VulnerabilityAgent(config, sandbox).scan()
    finally:
        sandbox.stop()

    stem = make_stem(config.target_spec.name)
    report_path = write_report(
        config.target_spec.name,
        result.findings,
        result.model,
        result.input_tokens,
        result.output_tokens,
        result.iterations,
        reports_dir,
        stem=stem,
    )
    json_path = write_messages_json(result.messages, reports_dir, stem)

    return {
        "result": result,
        "report_path": report_path,
        "json_path": json_path,
        "reports_dir": reports_dir,
        "stem": stem,
    }


@_skip_agent
def test_agent_scan_completes(agent_scan_result):
    scan_data = agent_scan_result
    assert scan_data["result"].iterations >= 1
    assert scan_data["result"].input_tokens > 0
    assert isinstance(scan_data["result"].messages, list)
    assert len(scan_data["result"].messages) > 0


@_skip_agent
def test_agent_writes_report(agent_scan_result):
    scan_data = agent_scan_result
    assert scan_data["report_path"].exists()
    assert scan_data["report_path"].stat().st_size > 0
    assert scan_data["json_path"].exists()
    assert isinstance(json.loads(scan_data["json_path"].read_text()), list)


@_skip_agent
def test_agent_report_rerender(agent_scan_result):
    scan_data = agent_scan_result
    from click.testing import CliRunner

    from lacuna.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["report", scan_data["stem"], "--reports-dir", str(scan_data["reports_dir"])],
        env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "")},
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    # A second .md file should now exist (the re-rendered one)
    md_files = list(scan_data["reports_dir"].glob("*.md"))
    assert len(md_files) >= 2


@_skip_agent
def test_agent_clean(agent_scan_result):
    # agent_scan_result is listed to ensure the scan fixture ran first,
    # populating workspace/ so that clean has something to clear.
    _ = agent_scan_result

    from click.testing import CliRunner

    from lacuna.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["clean"], catch_exceptions=False)
    assert result.exit_code == 0

    workspace = Path("workspace")
    remaining = [p for p in workspace.iterdir() if p.name != ".gitkeep"]
    assert remaining == []
