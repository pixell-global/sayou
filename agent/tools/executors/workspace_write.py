"""Workspace write executor."""

from __future__ import annotations

from typing import Any

from sayou.workspace import Workspace

from sayou.agent.tools.executors.base import BaseExecutor, ToolResult


class WorkspaceWriteExecutor(BaseExecutor):
    """Write a structured file to the workspace."""

    def __init__(self, workspace: Workspace):
        self._ws = workspace

    @property
    def name(self) -> str:
        return "workspace_write"

    @property
    def description(self) -> str:
        return (
            "Write a file to the workspace. Content should include YAML frontmatter "
            "for metadata (date, topics, people, tags, source) followed by markdown content "
            "organized under section headings. Creates the file if it doesn't exist, "
            "or creates a new version if it does."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path (e.g. 'observations/2024-01-15-tokyo-trip.md').",
                },
                "content": {
                    "type": "string",
                    "description": "File content with YAML frontmatter and markdown body.",
                },
                "source": {
                    "type": "string",
                    "description": "Source identifier (e.g. 'chat', 'session', 'import').",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        source = kwargs.get("source")

        if not path:
            return ToolResult.error_result("Path is required.")
        if not content:
            return ToolResult.error_result("Content is required.")

        try:
            ws_kwargs: dict[str, Any] = {"path": path, "content": content}
            if source:
                ws_kwargs["source"] = source
            await self._ws.write(**ws_kwargs)
            return ToolResult.success_result(f"Successfully wrote file: {path}")
        except Exception as e:
            return ToolResult.error_result(f"Failed to write {path}: {e}", recoverable=True)
