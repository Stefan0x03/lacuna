from __future__ import annotations

from dataclasses import dataclass

from lacuna.tools.base import BaseTool, ToolResult

VALID_SEVERITIES: frozenset[str] = frozenset({"critical", "high", "medium", "low", "info"})


@dataclass
class Finding:
    title: str
    severity: str
    description: str
    location: str = ""
    recommendation: str = ""
    cwe: str = ""


class EmitFindingTool(BaseTool):
    def __init__(self, findings: list[Finding]) -> None:
        self._findings = findings

    @property
    def name(self) -> str:
        return "emit_finding"

    @property
    def description(self) -> str:
        return "Record a structured vulnerability finding in the scan report."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title of the finding."},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                    "description": "Severity level.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the vulnerability.",
                },
                "location": {
                    "type": "string",
                    "description": "File path and/or line number where the issue occurs.",
                },
                "recommendation": {
                    "type": "string",
                    "description": "Suggested fix or mitigation.",
                },
                "cwe": {
                    "type": "string",
                    "description": "CWE identifier, e.g. CWE-122.",
                },
            },
            "required": ["title", "severity", "description"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            severity = input["severity"].lower()
            if severity not in VALID_SEVERITIES:
                return ToolResult(
                    is_error=True,
                    content=(
                        f"Invalid severity {severity!r}. "
                        f"Must be one of: {', '.join(sorted(VALID_SEVERITIES))}"
                    ),
                )
            finding = Finding(
                title=input["title"],
                severity=severity,
                description=input["description"],
                location=input.get("location", ""),
                recommendation=input.get("recommendation", ""),
                cwe=input.get("cwe", ""),
            )
            self._findings.append(finding)
            return ToolResult(content=f"Finding recorded: [{severity.upper()}] {finding.title}")
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
