from __future__ import annotations

import json
import re

from lacuna.report import (
    estimate_cost,
    extract_findings_from_messages,
    make_stem,
    render_markdown,
    write_messages_json,
    write_report,
)
from lacuna.tools.report_tool import Finding


def _make_finding(**kwargs) -> Finding:
    defaults = {"title": "Test Bug", "severity": "high", "description": "A bug."}
    defaults.update(kwargs)
    return Finding(**defaults)


# --- render_markdown ---


def test_render_markdown_with_findings():
    f = _make_finding(title="Stack Overflow", severity="critical", description="Bad stack op.")
    out = render_markdown("mylib", [f], "claude-sonnet-4-6", 1000, 500, 3)
    assert "### [CRITICAL] Stack Overflow" in out
    assert "Bad stack op." in out
    assert "CRITICAL" in out


def test_render_markdown_no_findings():
    out = render_markdown("mylib", [], "claude-sonnet-4-6", 0, 0, 1)
    assert "No vulnerabilities found." in out


def test_render_markdown_severity_sort():
    low = _make_finding(title="Low Bug", severity="low", description="Minor issue.")
    critical = _make_finding(title="Critical Bug", severity="critical", description="Severe.")
    out = render_markdown("mylib", [low, critical], "claude-sonnet-4-6", 1000, 500, 5)
    assert out.index("Critical Bug") < out.index("Low Bug")


def test_render_markdown_optional_fields():
    # CWE and recommendation appear when set
    f = _make_finding(cwe="CWE-122", recommendation="Use safe functions.")
    out = render_markdown("mylib", [f], "claude-sonnet-4-6", 1000, 500, 1)
    assert "CWE-122" in out
    assert "Use safe functions." in out

    # Absent when empty
    f2 = _make_finding()
    out2 = render_markdown("mylib", [f2], "claude-sonnet-4-6", 1000, 500, 1)
    assert "CWE" not in out2
    assert "Recommendation" not in out2


def test_render_markdown_cost_line():
    out = render_markdown("mylib", [], "claude-sonnet-4-6", 1000, 500, 1)
    assert "Est. cost" in out


# --- write_report ---


def test_write_report_creates_file(tmp_path):
    f = _make_finding()
    path = write_report("mylib", [f], "claude-sonnet-4-6", 100, 50, 1, tmp_path, stem="test_stem")
    assert path.exists()
    assert path.read_text()


def test_write_report_no_overwrite(tmp_path):
    f = _make_finding()
    path1 = write_report("mylib", [f], "claude-sonnet-4-6", 100, 50, 1, tmp_path, stem="same_stem")
    path2 = write_report("mylib", [f], "claude-sonnet-4-6", 100, 50, 1, tmp_path, stem="same_stem")
    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_write_report_creates_reports_dir(tmp_path):
    new_dir = tmp_path / "new_reports"
    assert not new_dir.exists()
    write_report("mylib", [], "claude-sonnet-4-6", 0, 0, 0, new_dir, stem="stem")
    assert new_dir.exists()


# --- write_messages_json ---


def test_write_messages_json_creates_file(tmp_path):
    messages = [{"role": "user", "content": "hello"}]
    path = write_messages_json(messages, tmp_path, "test_stem")
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded == messages


def test_write_messages_json_filename(tmp_path):
    path = write_messages_json([], tmp_path, "my_stem")
    assert path.name.endswith("_messages.json")


# --- extract_findings_from_messages ---


def _make_messages_with_finding(**kwargs) -> list[dict]:
    inp = {"title": "Overflow", "severity": "high", "description": "Bad.", **kwargs}
    return [
        {"role": "user", "content": "scan this"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "emit_finding", "input": inp}],
        },
    ]


def test_extract_findings_from_messages_basic():
    messages = _make_messages_with_finding()
    findings = extract_findings_from_messages(messages)
    assert len(findings) == 1
    assert findings[0].title == "Overflow"
    assert findings[0].severity == "high"
    assert findings[0].description == "Bad."


def test_extract_findings_from_messages_invalid_severity():
    messages = _make_messages_with_finding(severity="bogus")
    findings = extract_findings_from_messages(messages)
    assert findings == []


# --- estimate_cost ---


def test_estimate_cost_sonnet():
    cost = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost > 0.0


def test_estimate_cost_unknown_model():
    cost = estimate_cost("some-unknown-model-xyz", 1_000_000, 1_000_000)
    assert cost == 0.0


# --- make_stem ---


def test_make_stem_format():
    stem = make_stem("mylib")
    assert re.match(r"^mylib_\d{8}_\d{6}$", stem)
