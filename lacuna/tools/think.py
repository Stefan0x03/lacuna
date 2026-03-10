from __future__ import annotations

from lacuna.tools.base import BaseTool, ToolResult


class ThinkTool(BaseTool):
    @property
    def name(self) -> str:
        return "think"

    @property
    def description(self) -> str:
        return (
            "Internal reasoning scratchpad. Use this to think through a problem "
            "before acting. Has no side effects."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Your internal reasoning."},
            },
            "required": ["thought"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            return ToolResult(content=input["thought"])
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))
