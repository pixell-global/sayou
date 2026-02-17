"""Workspace read executor."""

from __future__ import annotations

from typing import Any

from sayou.workspace import Workspace

from sayou.agent.tools.executors.base import BaseExecutor, ToolResult


class WorkspaceReadExecutor(BaseExecutor):
    """Read a file from the workspace."""

    def __init__(self, workspace: Workspace):
        self._ws = workspace

    @property
    def name(self) -> str:
        return "workspace_read"

    @property
    def description(self) -> str:
        return (
            "Read a file's content from the workspace. "
            "Returns the file content with YAML frontmatter metadata. "
            "Use token_budget to control output size for large files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "token_budget": {
                    "type": "integer",
                    "description": "Maximum tokens of content to return. Larger files are summarized.",
                    "default": 3000,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        token_budget = kwargs.get("token_budget", 3000)

        if not path:
            return ToolResult.error_result("Path is required.")

        try:
            result = await self._ws.read(path, token_budget=token_budget)
            content = result.get("content", "")
            frontmatter = result.get("frontmatter", {})

            output_parts = [f"**File:** {path}"]
            if frontmatter:
                fm_lines = [f"  {k}: {v}" for k, v in frontmatter.items()]
                output_parts.append("**Metadata:**\n" + "\n".join(fm_lines))
            output_parts.append(f"**Content:**\n{content}")

            return ToolResult.success_result("\n\n".join(output_parts))
        except Exception as e:
            return ToolResult.error_result(f"Failed to read {path}: {e}", recoverable=True)
