"""Workspace list executor."""

from __future__ import annotations

from typing import Any

from sayou.workspace import Workspace

from sayou.agent.tools.executors.base import BaseExecutor, ToolResult


class WorkspaceListExecutor(BaseExecutor):
    """List files and folders in the workspace."""

    def __init__(self, workspace: Workspace):
        self._ws = workspace

    @property
    def name(self) -> str:
        return "workspace_list"

    @property
    def description(self) -> str:
        return (
            "List files and subfolders in a workspace directory. "
            "Returns file names, types, and frontmatter metadata summary."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list. Defaults to root.",
                    "default": "/",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list recursively.",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "/")
        recursive = kwargs.get("recursive", False)

        try:
            result = await self._ws.list(path, recursive=recursive)
            content = result.get("content", "")

            if not content or content.strip() == "":
                return ToolResult.success_result(f"Directory '{path}' is empty.")

            return ToolResult.success_result(f"Contents of {path}:\n\n{content}")
        except Exception as e:
            return ToolResult.error_result(f"Failed to list {path}: {e}", recoverable=True)
