"""Tavily web search executor."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sayou.agent.tools.executors.base import BaseExecutor, ToolResult

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class WebSearchExecutor(BaseExecutor):
    """Search the web using Tavily API."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. Returns titles, URLs, and content "
            "excerpts. For thorough research or comparisons, call this tool MULTIPLE times "
            "with different queries to cover different angles."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific — include names, years, product names.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-10).",
                    "default": 5,
                },
                "search_depth": {
                    "type": "string",
                    "description": "'basic' (fast) or 'advanced' (thorough, better for factual queries).",
                    "enum": ["basic", "advanced"],
                    "default": "advanced",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = min(kwargs.get("max_results", 5), 10)
        search_depth = kwargs.get("search_depth", "advanced")

        if not query:
            return ToolResult.error_result("Query is required.")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    TAVILY_SEARCH_URL,
                    json={
                        "api_key": self._api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": search_depth,
                        "include_answer": True,
                        "include_raw_content": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            if not results:
                return ToolResult.success_result(f"No web results found for: {query}")

            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                content = r.get("content", "")
                # Keep generous snippets so the LLM can extract specific facts
                if len(content) > 800:
                    content = content[:800] + "..."
                lines.append(f"**{i}. {title}**\nURL: {url}\n{content}")

            output = f"Results for: \"{query}\"\n\n" + "\n\n---\n\n".join(lines)

            answer = data.get("answer")
            if answer:
                output = f"Quick answer: {answer}\n\n" + output

            return ToolResult.success_result(output)

        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily API error: {e.response.status_code} {e.response.text}")
            return ToolResult.error_result(
                f"Web search failed (HTTP {e.response.status_code})", recoverable=True
            )
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return ToolResult.error_result(f"Web search failed: {e}", recoverable=True)
