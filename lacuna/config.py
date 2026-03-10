from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SourceSpec:
    type: str  # "git" | "tarball" | "local"
    url: str = ""
    ref: str = ""
    path: str = ""


@dataclass
class TargetSpec:
    name: str
    version: str
    source: SourceSpec
    language: str  # "c" | "cpp"
    description: str = ""
    attack_surface_hint: str = ""
    build_hint: str = ""


@dataclass
class ScanConfig:
    target_spec: TargetSpec
    model: str = "claude-sonnet-4-6"
    max_iterations: int = 50
    max_tokens: int = 8192
    sandbox_name: str = "lacuna-sandbox"
    reports_dir: Path = field(default_factory=lambda: Path("reports"))
    workspace_dir: Path = field(default_factory=lambda: Path("workspace"))
    timeout_per_tool: int = 30
    verbose: bool = False


def load_target_spec(path: Path) -> TargetSpec:
    with path.open() as f:
        data = yaml.safe_load(f)

    source_data = data["source"]
    source = SourceSpec(
        type=source_data["type"],
        url=source_data.get("url", ""),
        ref=source_data.get("ref", ""),
        path=source_data.get("path", ""),
    )

    return TargetSpec(
        name=data["name"],
        version=str(data["version"]),
        source=source,
        language=data["language"],
        description=data.get("description", ""),
        attack_surface_hint=data.get("attack_surface_hint", ""),
        build_hint=data.get("build_hint", ""),
    )


def load_config(target_yaml: Path, **overrides: object) -> ScanConfig:
    target_spec = load_target_spec(target_yaml)

    model = str(overrides.get("model") or os.getenv("LACUNA_DEFAULT_MODEL") or "claude-sonnet-4-6")

    max_iterations_env = os.getenv("LACUNA_MAX_ITERATIONS")
    max_iterations = int(
        overrides.get("max_iterations") or (int(max_iterations_env) if max_iterations_env else 50)
    )

    reports_env = os.getenv("LACUNA_REPORTS_DIR")
    reports_dir = Path(
        str(overrides.get("reports_dir"))
        if overrides.get("reports_dir") is not None
        else (reports_env or "reports")
    )

    workspace_env = os.getenv("LACUNA_WORKSPACE_DIR")
    workspace_dir = Path(
        str(overrides.get("workspace_dir"))
        if overrides.get("workspace_dir") is not None
        else (workspace_env or "workspace")
    )

    return ScanConfig(
        target_spec=target_spec,
        model=model,
        max_iterations=max_iterations,
        max_tokens=int(overrides.get("max_tokens") or 8192),
        sandbox_name=str(overrides.get("sandbox_name") or "lacuna-sandbox"),
        reports_dir=reports_dir,
        workspace_dir=workspace_dir,
        timeout_per_tool=int(overrides.get("timeout_per_tool") or 30),
        verbose=bool(overrides.get("verbose", False)),
    )
