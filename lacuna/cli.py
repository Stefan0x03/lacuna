from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

import click

from lacuna.agent import VulnerabilityAgent
from lacuna.config import load_config
from lacuna.report import (
    estimate_cost,
    extract_findings_from_messages,
    make_stem,
    write_messages_json,
    write_report,
)
from lacuna.sandbox.manager import DockerSandbox
from lacuna.sandbox.staging import stage_target


@click.group()
def cli() -> None:
    """Lacuna — agentic C/C++ vulnerability scanner."""


@cli.command()
@click.argument("target_yaml", type=click.Path(exists=True, path_type=Path))
@click.option("--model", default=None, help="Model override.")
@click.option("--max-iterations", default=None, type=int)
@click.option("--full-run", is_flag=True, help="Use claude-opus-4-6.")
@click.option("--verbose", is_flag=True)
def scan(
    target_yaml: Path,
    model: str | None,
    max_iterations: int | None,
    full_run: bool,
    verbose: bool,
) -> None:
    """Run a vulnerability scan."""
    if full_run:
        model = "claude-opus-4-6"

    overrides: dict = {"verbose": verbose}
    if model is not None:
        overrides["model"] = model
    if max_iterations is not None:
        overrides["max_iterations"] = max_iterations

    try:
        config = load_config(target_yaml, **overrides)
        click.echo(
            f"[lacuna] Scanning {config.target_spec.name} "
            f"{config.target_spec.version} with {config.model}"
        )

        workspace_path = stage_target(config.target_spec, config.workspace_dir)
        click.echo(f"[lacuna] Source staged at {workspace_path}")

        sandbox = DockerSandbox(config.sandbox_name, config.workspace_dir)
        sandbox.start()
        click.echo("[lacuna] Sandbox started.")

        result = VulnerabilityAgent(config, sandbox).scan()

        stem = make_stem(config.target_spec.name)
        report_path = write_report(
            config.target_spec.name,
            result.findings,
            result.model,
            result.input_tokens,
            result.output_tokens,
            result.iterations,
            config.reports_dir,
            stem=stem,
        )
        json_path = write_messages_json(result.messages, config.reports_dir, stem)

        click.echo("[lacuna] Scan complete.")
        click.echo(f"[lacuna] Findings   : {len(result.findings)}")
        click.echo(f"[lacuna] Iterations : {result.iterations}")
        click.echo(
            f"[lacuna] Tokens     : {result.input_tokens:,} in / {result.output_tokens:,} out"
        )
        click.echo(
            f"[lacuna] Est. cost  : ${estimate_cost(result.model, result.input_tokens, result.output_tokens):.4f}"
        )
        click.echo(f"[lacuna] Report     : {report_path}")
        click.echo(f"[lacuna] Messages   : {json_path}")

    except Exception as e:
        click.echo(f"[lacuna] ERROR: {e}", err=True)
        sys.exit(1)


@cli.command()
def clean() -> None:
    """Stop sandbox, remove container, clear workspace/."""
    try:
        sandbox = DockerSandbox("lacuna-sandbox", Path("workspace"))
        sandbox.stop()
        workspace = Path("workspace")
        for item in workspace.iterdir():
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        click.echo("[lacuna] Sandbox stopped and workspace cleared.")
    except Exception as e:
        click.echo(f"[lacuna] ERROR: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("scan_id")
@click.option(
    "--reports-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Directory containing reports (default: $LACUNA_REPORTS_DIR or ./reports).",
)
def report(scan_id: str, reports_dir: Path | None) -> None:
    """Re-render a Markdown report from a saved messages JSON."""
    reports_env = os.getenv("LACUNA_REPORTS_DIR")
    effective_reports_dir = reports_dir or (Path(reports_env) if reports_env else Path("reports"))

    messages_path = effective_reports_dir / f"{scan_id}_messages.json"
    if not messages_path.exists():
        click.echo(f"[lacuna] Not found: {messages_path}", err=True)
        sys.exit(1)

    messages = json.loads(messages_path.read_text())

    m = re.match(r"^(.+)_\d{8}_\d{6}$", scan_id)
    target_name = m.group(1) if m else scan_id

    findings = extract_findings_from_messages(messages)
    iterations = sum(1 for msg in messages if msg.get("role") == "assistant")
    stem = make_stem(target_name)
    report_path = write_report(
        target_name,
        findings,
        "unknown",
        0,
        0,
        iterations,
        effective_reports_dir,
        stem=stem,
    )
    click.echo(f"[lacuna] Re-rendered report: {report_path}")
