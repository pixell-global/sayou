from mcp.server.fastmcp import FastMCP

from sayou.config import settings
from sayou.core.workspace import (
    AccessDeniedError,
    FileExistsError,
    FileNotFoundError,
    WorkspaceService,
)


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
        path: str, content: str, source: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """Write a file to the workspace. Creates the file if it doesn't exist, or creates a new version if it does. Content can include YAML frontmatter for structured metadata. For binary files, pass base64-encoded content and set content_type (e.g., image/png)."""
        try:
            import base64 as b64
            org_id, user_id, workspace_slug = _identity()

            # If content_type indicates binary, decode from base64
            write_content: str | bytes = content
            if content_type and not content_type.startswith("text/") and content_type not in (
                "application/json", "application/xml", "application/yaml",
            ):
                try:
                    write_content = b64.b64decode(content)
                except Exception:
                    write_content = content  # fallback to string

            result = await ws.write(
                org_id, user_id, workspace_slug, path, write_content, source,
                content_type=content_type,
            )
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

    @server.tool(name="workspace_audit")
    async def workspace_audit(
        path: str | None = None,
        action: str | None = None,
        agent_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
    ) -> str:
        """Query the workspace mutation audit log. Filter by file path, action (write/delete), agent_id, or time range (ISO 8601). Returns recent mutations sorted newest-first."""
        try:
            from datetime import datetime

            org_id, user_id, workspace_slug = _identity()

            since_dt = datetime.fromisoformat(since) if since else None
            until_dt = datetime.fromisoformat(until) if until else None

            result = await ws.audit_log(
                org_id, user_id, workspace_slug,
                path=path, action=action, agent_id=agent_id,
                since=since_dt, until=until_dt, limit=limit,
            )
            if not result["entries"]:
                return "No audit log entries found"
            lines = [f"**{result['total']} audit entries**"]
            for e in result["entries"]:
                ts = e.get("created_at", "")
                agent = e.get("agent_id") or "unknown"
                lines.append(f"  [{ts}] {e['action'].upper()} {e['file_path']} by {agent}")
            return "\n".join(lines)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error querying audit log: {e}"

    @server.tool(name="workspace_move")
    async def workspace_move(source_path: str, dest_path: str) -> str:
        """Move a file to a new path within the workspace. Version history is preserved."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.move(
                org_id, user_id, workspace_slug, source_path, dest_path
            )
            return f"Moved {result['source']} → {result['destination']}"
        except FileNotFoundError as e:
            return f"Not found: {e}"
        except FileExistsError as e:
            return f"Already exists: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error moving: {e}"

    @server.tool(name="workspace_copy")
    async def workspace_copy(source_path: str, dest_path: str) -> str:
        """Copy a file to a new path within the workspace. Creates an independent copy."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.copy(
                org_id, user_id, workspace_slug, source_path, dest_path
            )
            return f"Copied {result['source']} → {result['destination']}"
        except FileNotFoundError as e:
            return f"Not found: {e}"
        except FileExistsError as e:
            return f"Already exists: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error copying: {e}"

    @server.tool(name="workspace_diff")
    async def workspace_diff(path: str, version_a: int, version_b: int) -> str:
        """Compare two versions of a file. Returns a unified diff showing additions (+) and removals (-) between the specified versions."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.diff(
                org_id, user_id, workspace_slug, path, version_a, version_b
            )
            if not result["has_changes"]:
                return f"No differences between v{version_a} and v{version_b} of {result['path']}"
            return f"**Diff: {result['path']} v{version_a} → v{version_b}**\n\n```diff\n{result['diff']}```"
        except FileNotFoundError as e:
            return f"Not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error diffing: {e}"

    @server.tool(name="workspace_read_section")
    async def workspace_read_section(
        path: str, line_start: int, line_end: int
    ) -> str:
        """Read a specific line range from a file (1-indexed, inclusive). Use after reading a summarized file to drill into specific sections."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.read_section(
                org_id, user_id, workspace_slug, path, line_start, line_end
            )
            header = (
                f"**{result['path']}** lines {result['line_start']}-{result['line_end']} "
                f"(of {result['total_lines']})"
            )
            return f"{header}\n\n{result['content']}"
        except FileNotFoundError as e:
            return f"Not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error reading section: {e}"

    @server.tool(name="workspace_kv_get")
    async def workspace_kv_get(key: str) -> str:
        """Get a value from the workspace key-value store."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.kv_get(org_id, user_id, workspace_slug, key)
            if not result["found"]:
                return f"Key not found: {key}"
            import json
            return f"**{key}** = {json.dumps(result['value'])}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error getting key: {e}"

    @server.tool(name="workspace_kv_set")
    async def workspace_kv_set(
        key: str, value: str, ttl_seconds: int | None = None
    ) -> str:
        """Set a value in the workspace key-value store. Value is stored as a JSON string. Optional TTL in seconds for auto-expiry."""
        try:
            import json
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed = value
            org_id, user_id, workspace_slug = _identity()
            result = await ws.kv_set(
                org_id, user_id, workspace_slug, key, parsed, ttl_seconds
            )
            ttl_info = f" (TTL: {ttl_seconds}s)" if ttl_seconds else ""
            return f"Set {key}{ttl_info}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error setting key: {e}"

    @server.tool(name="workspace_kv_delete")
    async def workspace_kv_delete(key: str) -> str:
        """Delete a key from the workspace key-value store."""
        try:
            org_id, user_id, workspace_slug = _identity()
            result = await ws.kv_delete(org_id, user_id, workspace_slug, key)
            if result["deleted"]:
                return f"Deleted {key}"
            return f"Key not found: {key}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error deleting key: {e}"

    @server.tool(name="workspace_kv_list")
    async def workspace_kv_list(prefix: str | None = None) -> str:
        """List keys in the workspace key-value store. Optionally filter by key prefix."""
        try:
            import json
            org_id, user_id, workspace_slug = _identity()
            result = await ws.kv_list(org_id, user_id, workspace_slug, prefix)
            if not result["items"]:
                prefix_msg = f" with prefix '{prefix}'" if prefix else ""
                return f"No keys found{prefix_msg}"
            lines = [f"**{result['total']} keys**"]
            for item in result["items"]:
                val_preview = json.dumps(item["value"])
                if len(val_preview) > 60:
                    val_preview = val_preview[:57] + "..."
                lines.append(f"  {item['key']} = {val_preview}")
            return "\n".join(lines)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error listing keys: {e}"

    return server, ws
