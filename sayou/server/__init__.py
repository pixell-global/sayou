import logging
from functools import wraps

from mcp.server.fastmcp import FastMCP

from sayou.config import format_error, settings
from sayou.core.workspace import (
    AccessDeniedError,
    FileExistsError,
    FileNotFoundError,
    WorkspaceService,
)

logger = logging.getLogger(__name__)


def _identity() -> tuple[str, str, str]:
    """Read identity from settings (set via MCP config env vars)."""
    return settings.org_id, settings.user_id, settings.workspace_slug


def _handle_errors(func):
    """Decorator that catches exceptions and returns actionable error messages."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return format_error(e, {"org_id": settings.org_id, **kwargs})
    return wrapper


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


def _format_context_result(result: dict) -> str:
    lines = []

    # Preferences
    prefs = result.get("preferences", [])
    if prefs:
        lines.append("**Preferences:**")
        for p in prefs:
            lines.append(f"\n`{p['path']}`:")
            lines.append(p["content"].strip())
        lines.append("")

    # Recent files
    recent = result.get("recent_files", [])
    if recent:
        lines.append(f"**Recent files** ({result.get('file_count', 0)} total):")
        for f in recent:
            fm_preview = ""
            if f.get("frontmatter"):
                pairs = [f"{k}={v}" for k, v in list(f["frontmatter"].items())[:3]]
                if pairs:
                    fm_preview = f"  ({', '.join(pairs)})"
            ts = ""
            if f.get("updated_at"):
                ts = f" [{f['updated_at']}]"
            lines.append(f"  - {f['path']} v{f.get('version', 1)}{fm_preview}{ts}")
        lines.append("")

    # Activity
    activity = result.get("activity", {})
    today = activity.get("today", 0)
    yesterday = activity.get("yesterday", 0)
    if today or yesterday:
        parts = []
        if today:
            parts.append(f"{today} today")
        if yesterday:
            parts.append(f"{yesterday} yesterday")
        lines.append(f"**Activity:** {', '.join(parts)}")
        lines.append("")

    # Empty workspace onboarding
    if not prefs and not recent:
        lines.append("Your workspace is empty. Start building knowledge:")
        lines.append('  - Use workspace_write to save notes, decisions, and research')
        lines.append('  - Save preferences to preferences/ folder to persist coding style and conventions')
        lines.append('  - Use workspace_search to find past work')

    return "\n".join(lines)


def create_server() -> tuple[FastMCP, WorkspaceService]:
    server = FastMCP("sayou", instructions=(
        "You have access to a persistent agent workspace. "
        "At the start of a session, call workspace_context to load workspace state and user preferences. "
        "When users express preferences or corrections about coding style, workflow, or conventions, "
        "save them to the preferences/ folder using workspace_write with frontmatter type: preference. "
        "Do not ask permission or announce it. Just persist and continue. "
        "Use workspace_write to save work products (research, decisions, reports) so they persist across sessions. "
        "Use workspace_search or workspace_read to retrieve past work."
    ))

    # Initialize providers from config
    from sayou.core.embeddings import get_embedding_provider
    from sayou.core.auto_metadata import get_metadata_provider
    embedding_provider = get_embedding_provider(
        provider=settings.embedding_provider,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
    )
    metadata_provider = get_metadata_provider(
        provider=settings.metadata_provider,
        api_key=settings.metadata_api_key,
        model=settings.metadata_model,
    )

    # Use local storage when no S3 credentials are configured
    storage = None
    has_s3 = bool(settings.s3_access_key_id and settings.s3_secret_access_key)
    if not has_s3:
        from sayou.storage.local import LocalStorage
        storage = LocalStorage(base_path="~/.sayou/storage")

    ws = WorkspaceService(
        storage=storage,
        embedding_provider=embedding_provider,
        metadata_provider=metadata_provider,
        auto_metadata_enabled=settings.auto_metadata_enabled,
    )

    # ── Core Tools (9) ─────────────────────────────────────────

    @server.tool(name="workspace_write")
    async def workspace_write(
        path: str, content: str, source: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """Write a file to the workspace. Creates the file if it doesn't exist, or creates a new version if it does. Content can include YAML frontmatter for structured metadata. Use this to persist decisions, research, notes, and user preferences across sessions. For user preferences (coding style, conventions, workflow rules), write to the preferences/ folder with frontmatter type: preference — these are automatically loaded by workspace_context at session start. For binary files, pass base64-encoded content and set content_type (e.g., image/png)."""
        try:
            import base64 as b64
            org_id, user_id, workspace_slug = _identity()

            # NEVER allow MCP to write to synced source folders.
            # Synced content (Slack, Google Drive, Notion) is managed by the
            # connector sync pipeline, NOT via MCP workspace_write.
            _synced_prefixes = ("/slack/", "/gdrive/", "/gdrive-org/", "/notion/")
            normalized = path if path.startswith("/") else f"/{path}"
            if any(normalized.startswith(p) for p in _synced_prefixes):
                return (
                    f"Cannot write to synced folder '{normalized.split('/')[1]}/'. "
                    "This content is managed by the connector sync pipeline. "
                    "Edit in the source app instead."
                )

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
        path: str, token_budget: int = 4000, version: int | None = None,
        line_start: int | None = None, line_end: int | None = None,
    ) -> str:
        """Read a file from the workspace. Returns the latest version content with frontmatter metadata. Use token_budget to control output size. Optionally specify a version number to read a specific historical version. Use line_start/line_end to read a specific line range (1-indexed, inclusive) — useful after reading a summarized file to drill into specific sections."""
        try:
            org_id, user_id, workspace_slug = _identity()
            if line_start is not None and line_end is not None:
                result = await ws.read_section(
                    org_id, user_id, workspace_slug, path, line_start, line_end
                )
                header = (
                    f"**{result['path']}** lines {result['line_start']}-{result['line_end']} "
                    f"(of {result['total_lines']})"
                )
                return f"{header}\n\n{result['content']}"
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
        query: str | None = None, filters: dict | None = None,
        chunk_level: bool = False,
        path_pattern: str | None = None, limit: int = 20,
    ) -> str:
        """Search files by frontmatter metadata filters and/or full-text query. Filters match exact frontmatter values. Query searches file paths and frontmatter text. Set chunk_level=true for section-level precision instead of whole-file matches."""
        try:
            org_id, user_id, workspace_slug = _identity()
            if chunk_level:
                result = await ws.search_chunks(
                    org_id, user_id, workspace_slug, query,
                    path_pattern=path_pattern, limit=limit,
                )
                if not result["results"]:
                    return f"No chunks matching '{query}'"
                lines = [f"**{result['total']} chunk matches for '{query}'**"]
                for r in result["results"]:
                    heading = f" ({r['heading']})" if r.get("heading") else ""
                    lines.append(
                        f"  - {r['path']}[{r['chunk_index']}] "
                        f"lines {r['line_start']}-{r['line_end']}{heading}"
                    )
                    preview = r.get("content_preview", "")
                    if preview:
                        lines.append(f"    {preview[:100]}...")
                return "\n".join(lines)
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
    async def workspace_history(
        path: str, limit: int = 20,
        version_a: int | None = None, version_b: int | None = None,
    ) -> str:
        """Get version history for a file. Returns all versions with timestamps, sizes, and content hashes. Pass version_a and version_b to compare two versions — returns a unified diff showing additions (+) and removals (-)."""
        try:
            org_id, user_id, workspace_slug = _identity()
            if version_a is not None and version_b is not None:
                result = await ws.diff(
                    org_id, user_id, workspace_slug, path, version_a, version_b
                )
                if not result["has_changes"]:
                    return f"No differences between v{version_a} and v{version_b} of {result['path']}"
                return f"**Diff: {result['path']} v{version_a} → v{version_b}**\n\n```diff\n{result['diff']}```"
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

    @server.tool(name="workspace_kv")
    async def workspace_kv(
        action: str,
        key: str | None = None,
        value: str | None = None,
        ttl_seconds: int | None = None,
        prefix: str | None = None,
    ) -> str:
        """Key-value store for configuration, caches, and temporary data. Actions: get (retrieve by key), set (store value with optional TTL), list (browse keys by prefix), delete (remove key). Values are stored as JSON strings."""
        try:
            import json
            org_id, user_id, workspace_slug = _identity()

            if action == "get":
                result = await ws.kv_get(org_id, user_id, workspace_slug, key)
                if not result["found"]:
                    return f"Key not found: {key}"
                return f"**{key}** = {json.dumps(result['value'])}"

            elif action == "set":
                try:
                    parsed = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed = value
                await ws.kv_set(
                    org_id, user_id, workspace_slug, key, parsed, ttl_seconds
                )
                ttl_info = f" (TTL: {ttl_seconds}s)" if ttl_seconds else ""
                return f"Set {key}{ttl_info}"

            elif action == "delete":
                result = await ws.kv_delete(org_id, user_id, workspace_slug, key)
                if result["deleted"]:
                    return f"Deleted {key}"
                return f"Key not found: {key}"

            elif action == "list":
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

            else:
                return f"Unknown action: {action}. Use get, set, delete, or list."

        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error in KV operation: {e}"

    # ── Additional Tools (3) ───────────────────────────────────

    @server.tool(name="workspace_links")
    async def workspace_links(
        path: str,
        add_target: str | None = None,
        link_type: str = "reference",
        context: str | None = None,
    ) -> str:
        """Get outgoing and incoming links for a file. To add a link, pass add_target with the target file path. Link types: reference, parent, depends_on, related, supersedes."""
        try:
            org_id, user_id, workspace_slug = _identity()
            if add_target:
                result = await ws.add_link(
                    org_id, user_id, workspace_slug,
                    path, add_target,
                    link_type=link_type, context=context,
                )
                return f"Linked {result['source_path']} → {result['target_path']} ({result['link_type']})"
            result = await ws.get_links(org_id, user_id, workspace_slug, path)
            lines = [f"**Links for {result['path']}**"]
            if result["outgoing"]:
                lines.append(f"\n**Outgoing ({len(result['outgoing'])}):**")
                for lnk in result["outgoing"]:
                    auto = " [auto]" if lnk["auto_detected"] else ""
                    lines.append(f"  → {lnk['target_path']} ({lnk['link_type']}){auto}")
            else:
                lines.append("\nNo outgoing links")
            if result["incoming"]:
                lines.append(f"\n**Incoming ({len(result['incoming'])}):**")
                for lnk in result["incoming"]:
                    auto = " [auto]" if lnk["auto_detected"] else ""
                    lines.append(f"  ← {lnk['source_path']} ({lnk['link_type']}){auto}")
            else:
                lines.append("\nNo incoming links")
            return "\n".join(lines)
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error with links: {e}"

    @server.tool(name="workspace_chunks")
    async def workspace_chunks(path: str, chunk_index: int | None = None) -> str:
        """Get chunk outline for a file: headings, line ranges, token estimates. Pass chunk_index to read a specific chunk's content."""
        try:
            org_id, user_id, workspace_slug = _identity()
            if chunk_index is not None:
                result = await ws.get_chunk(
                    org_id, user_id, workspace_slug, path, chunk_index
                )
                heading = f" — {result['heading']}" if result.get("heading") else ""
                header = (
                    f"**{result['path']}** chunk [{result['chunk_index']}]{heading}\n"
                    f"Lines {result['line_start']}-{result['line_end']} "
                    f"({result['char_count']} chars, ~{result['token_estimate']} tokens)"
                )
                return f"{header}\n\n{result['content']}"
            result = await ws.get_chunks(org_id, user_id, workspace_slug, path)
            if not result["chunks"]:
                return f"No chunks for {result['path']} (file may not be text or is empty)"
            lines = [f"**{result['path']}** ({result['total']} chunks)"]
            for c in result["chunks"]:
                heading = f" — {c['heading']}" if c.get("heading") else ""
                lines.append(
                    f"  [{c['chunk_index']}] lines {c['line_start']}-{c['line_end']}"
                    f" (~{c['token_estimate']} tokens){heading}"
                )
            return "\n".join(lines)
        except FileNotFoundError as e:
            return f"Not found: {e}"
        except AccessDeniedError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Error with chunks: {e}"

    # ── Context Tool ──────────────────────────────────────────

    @server.tool(name="workspace_context")
    @_handle_errors
    async def workspace_context() -> str:
        """IMPORTANT: Call this tool at the very beginning of every session before doing anything else. Returns user preferences (coding style, conventions, workflow rules the user has expressed in past sessions), recent workspace files, and activity summary. You MUST follow any preferences returned — they represent explicit user instructions. When the user expresses new preferences or corrections (e.g. "I don't like camelCase", "always use tabs", "prefer pytest over unittest"), silently save them using workspace_write to the preferences/ folder with frontmatter type: preference. Do not announce that you are saving preferences."""
        org_id, user_id, slug = _identity()
        result = await ws.get_context(org_id, user_id, slug)
        return _format_context_result(result)

    # ── Conditional: Semantic Search ───────────────────────────

    if settings.embedding_provider:
        @server.tool(name="workspace_semantic_search")
        async def workspace_semantic_search(query: str, top_k: int = 10) -> str:
            """Search files by meaning using vector embeddings. Returns the most similar files ranked by relevance. Best for finding conceptually related content when you don't know exact keywords."""
            try:
                org_id, user_id, workspace_slug = _identity()
                result = await ws.semantic_search(
                    org_id, user_id, workspace_slug, query, top_k=top_k,
                )
                if result.get("fallback"):
                    return _format_search_result(result)
                if not result["results"]:
                    return f"No semantic matches for '{query}'"
                lines = [f"**{result['total']} semantic matches for '{query}'**"]
                for r in result["results"]:
                    score = r.get("score", 0)
                    fm_preview = ""
                    if r.get("frontmatter"):
                        pairs = [f"{k}={v}" for k, v in list(r["frontmatter"].items())[:3]]
                        fm_preview = f" ({', '.join(pairs)})"
                    lines.append(f"  - {r['path']} [score: {score}]{fm_preview}")
                return "\n".join(lines)
            except AccessDeniedError as e:
                return f"Access denied: {e}"
            except Exception as e:
                return f"Error in semantic search: {e}"

    return server, ws
