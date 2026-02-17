"""Workspace search executor."""

from __future__ import annotations

from typing import Any

from sayou.workspace import Workspace

from sayou.agent.tools.executors.base import BaseExecutor, ToolResult


class WorkspaceSearchExecutor(BaseExecutor):
    """Search workspace files by content and metadata."""

    def __init__(self, workspace: Workspace):
        self._ws = workspace

    @property
    def name(self) -> str:
        return "workspace_search"

    @property
    def description(self) -> str:
        return (
            "Search workspace files by text query and/or frontmatter metadata filters. "
            "Returns matching file paths with relevance snippets. "
            "Use filters to narrow by source, tags, date, etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text query to search for in file contents and metadata.",
                },
                "filters": {
                    "type": "object",
                    "description": "Frontmatter metadata filters (e.g. {\"source\": \"chat\", \"tags\": \"travel\"}).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query")
        filters = kwargs.get("filters")
        limit = kwargs.get("limit", 5)

        try:
            results = await self._ws.search(query=query, filters=filters)
            items = results.get("results", [])[:limit]

            if not items:
                return ToolResult.success_result("No matching files found.")

            lines = []
            for item in items:
                path = item.get("path", "")
                snippet = item.get("snippet", "")
                score = item.get("score", "")
                line = f"- **{path}**"
                if score:
                    line += f" (score: {score:.2f})" if isinstance(score, float) else f" (score: {score})"
                if snippet:
                    line += f"\n  {snippet[:200]}"
                lines.append(line)

            return ToolResult.success_result(
                f"Found {len(items)} result(s):\n\n" + "\n\n".join(lines)
            )
        except Exception as e:
            return ToolResult.error_result(f"Search failed: {e}", recoverable=True)
