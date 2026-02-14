from mcp.server.fastmcp import FastMCP

from sayou.config import settings
from sayou.core.workspace import AccessDeniedError, FileNotFoundError, WorkspaceService


def _identity() -> tuple[str, str, str]:
    """Read identity from settings (set via MCP config env vars)."""
    return settings.org_id, settings.user_id, settings.workspace_slug


def _format_read_result(result: dict) -> str:
    lines = [f"**{result['path']}** [v{result['version_number']} | {result['size_bytes']} bytes]"]
    if result.get("truncated"):
        lines.append("*(truncated to fit token budget)*")
    if result.get("frontmatter"):
        lines.append("")
        lines.append("**Frontmatter:**")
        for k, v in result["frontmatter"].items():
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append(result["content"])
    return "\n".join(lines)


def _format_list_result(result: dict) -> str:
    lines = [f"**{result['path']}** ({result['file_count']} files)"]
    if result["subfolders"]:
        lines.append("")
        lines.append("**Subfolders:**")
        for sf in result["subfolders"]:
            lines.append(f"  - {sf}")
    if result.get("index_content"):
        lines.append("")
        lines.append(result["index_content"])
    return "\n".join(lines)


def _format_search_result(result: dict) -> str:
    lines = [f"**{result['total']} results found**"]
    for item in result["results"]:
        fm_preview = ""
        if item.get("frontmatter"):
            pairs = [f"{k}={v}" for k, v in list(item["frontmatter"].items())[:3]]
            fm_preview = f" ({', '.join(pairs)})"
        lines.append(f"  - {item['path']}{fm_preview}")
    return "\n".join(lines)


def _format_history_result(result: dict) -> str:
    lines = [f"**{result['path']}** ({result['total']} versions)"]
    for v in result["versions"]:
        ts = v.get("created_at", "")
        lines.append(
            f"  v{v['version_number']}: {v['content_hash'][:12]}... "
            f"({v['size_bytes']} bytes) by {v['created_by']} at {ts}"
        )
    return "\n".join(lines)


def create_server() -> tuple[FastMCP, WorkspaceService]:
    server = FastMCP("sayou")
    ws = WorkspaceService()

    @server.tool(name="workspace_write")
    async def workspace_write(
        path: str, content: str, source: str | None = None
    ) -> str:
        """Write a file to the workspace. Creates the file if it doesn't exist, or creates a new version if it does. Content can include YAML frontmatter for structured metadata."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.write(org_id, user_id, workspace_slug, path, content, source)
            return (
                f"Written {result['path']} v{result['version_number']} "
                f"({result['size_bytes']} bytes, hash: {result['content_hash'][:12]}...)"
            )
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error writing file: {e}"

    @server.tool(name="workspace_read")
    async def workspace_read(
        path: str, token_budget: int = 4000, version: int | None = None
    ) -> str:
        """Read a file from the workspace. Returns the latest version content with frontmatter metadata. Use token_budget to control output size. Optionally specify a version number to read a specific historical version."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.read(
                org_id, user_id, workspace_slug, path, token_budget, version
            )
            return _format_read_result(result)
        except FileNotFoundError as e:
            return f"File not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error reading file: {e}"

    @server.tool(name="workspace_list")
    async def workspace_list(path: str = "/", recursive: bool = False) -> str:
        """List files and subfolders in a workspace folder. Returns an auto-generated index table with frontmatter columns."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.list_folder(org_id, user_id, workspace_slug, path, recursive)
            return _format_list_result(result)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error listing folder: {e}"

    @server.tool(name="workspace_search")
    async def workspace_search(
        query: str | None = None, filters: dict | None = None
    ) -> str:
        """Search files by frontmatter metadata filters and/or full-text query. Filters match exact frontmatter values. Query searches file paths and frontmatter text."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.search(org_id, user_id, workspace_slug, query, filters)
            return _format_search_result(result)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error searching: {e}"

    @server.tool(name="workspace_delete")
    async def workspace_delete(path: str) -> str:
        """Delete a file from the workspace (soft-delete). The file's version history is preserved."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.delete(org_id, user_id, workspace_slug, path)
            return f"Deleted {result['path']}"
        except FileNotFoundError as e:
            return f"File not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error deleting file: {e}"

    @server.tool(name="workspace_history")
    async def workspace_history(path: str, limit: int = 20) -> str:
        """Get version history for a file. Returns all versions with timestamps, sizes, and content hashes."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.history(org_id, user_id, workspace_slug, path, limit)
            return _format_history_result(result)
        except FileNotFoundError as e:
            return f"File not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error getting history: {e}"

    @server.tool(name="workspace_glob")
    async def workspace_glob(pattern: str) -> str:
        """Find files matching a glob pattern. Supports: ** (any path depth), * (any name), ? (single char). Examples: **/*.md, research/**, clients/*/profile.md"""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.glob_files(org_id, user_id, workspace_slug, pattern)
            if not result["files"]:
                return f"No files matching '{pattern}'"
            lines = [f"**{result['total']} files matching `{pattern}`**"]
            for f in result["files"]:
                fm_preview = ""
                if f.get("frontmatter"):
                    pairs = [f"{k}={v}" for k, v in list(f["frontmatter"].items())[:3]]
                    fm_preview = f" ({', '.join(pairs)})"
                lines.append(f"  - {f['path']}{fm_preview}")
            return "\n".join(lines)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error globbing: {e}"

    @server.tool(name="workspace_grep")
    async def workspace_grep(
        query: str, path_pattern: str | None = None, context_lines: int = 2
    ) -> str:
        """Search file contents for a text query. Returns matching lines with surrounding context. Optionally filter by glob path_pattern (e.g., **/*.md). Like grep but for workspace files."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.grep_files(
                org_id, user_id, workspace_slug, query, path_pattern, context_lines
            )
            if not result["results"]:
                return f"No matches for '{query}'"
            lines = [f"**{result['total_files']} files match '{query}'**"]
            for file_result in result["results"]:
                lines.append(f"\n**{file_result['path']}** ({file_result['match_count']} matches)")
                for m in file_result["matches"]:
                    lines.append(m["context"])
            return "\n".join(lines)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error grepping: {e}"

    return server, ws
