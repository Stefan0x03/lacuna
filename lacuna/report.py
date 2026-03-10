from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from lacuna.tools.report_tool import VALID_SEVERITIES, Finding

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# Cost per 1M tokens: (input_cost, output_cost)
_COST_TABLE = [
    ("opus", 15.0, 75.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 0.25, 1.25),
]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    m = model.lower()
    for prefix, input_rate, output_rate in _COST_TABLE:
        if prefix in m:
            return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    return 0.0


def render_markdown(
    target_name: str,
    findings: list[Finding],
    model: str,
    input_tokens: int,
    output_tokens: int,
    iterations: int,
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cost = estimate_cost(model, input_tokens, output_tokens)

    lines = [
        f"# Lacuna Vulnerability Report — {target_name}",
        "",
        f"Generated: {ts}",
        "",
        f"Model: {model} | Iterations: {iterations} | "
        f"Tokens: {input_tokens:,} in / {output_tokens:,} out | "
        f"Est. cost: ${cost:.4f}",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    if not findings:
        lines.append("No vulnerabilities found.")
    else:
        lines.append(f"Total findings: {len(findings)}")
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        for sev in ("critical", "high", "medium", "low", "info"):
            if counts.get(sev, 0):
                lines.append(f"- {sev.capitalize()}: {counts[sev]}")
        lines.append("")
        lines.append("## Findings")
        lines.append("")
        sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
        for finding in sorted_findings:
            lines.append(f"### [{finding.severity.upper()}] {finding.title}")
            lines.append("")
            if finding.cwe:
                lines.append(f"**CWE**: {finding.cwe}")
                lines.append("")
            if finding.location:
                lines.append(f"**Location**: {finding.location}")
                lines.append("")
            lines.append(finding.description)
            if finding.recommendation:
                lines.append("")
                lines.append(f"**Recommendation**: {finding.recommendation}")
            lines.append("")

    return "\n".join(lines)


def make_stem(target_name: str, ts: str | None = None) -> str:
    if ts is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{target_name}_{ts}"


def write_report(
    target_name: str,
    findings: list[Finding],
    model: str,
    input_tokens: int,
    output_tokens: int,
    iterations: int,
    reports_dir: Path,
    *,
    stem: str | None = None,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    if stem is None:
        stem = make_stem(target_name)
    path = reports_dir / f"{stem}.md"
    if path.exists():
        path = reports_dir / f"{stem}_1.md"
    content = render_markdown(target_name, findings, model, input_tokens, output_tokens, iterations)
    path.write_text(content, encoding="utf-8")
    return path


def write_messages_json(
    messages: list[dict],
    reports_dir: Path,
    stem: str,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{stem}_messages.json"
    path.write_text(json.dumps(messages, indent=2, default=str), encoding="utf-8")
    return path


def extract_findings_from_messages(messages: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name") != "emit_finding":
                continue
            inp = block.get("input", {})
            severity = inp.get("severity", "").lower()
            if severity not in VALID_SEVERITIES:
                continue
            findings.append(
                Finding(
                    title=inp.get("title", ""),
                    severity=severity,
                    description=inp.get("description", ""),
                    location=inp.get("location", ""),
                    recommendation=inp.get("recommendation", ""),
                    cwe=inp.get("cwe", ""),
                )
            )
    return findings
