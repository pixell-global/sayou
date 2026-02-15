import base64
import difflib
import json
from datetime import datetime

from sayou.catalog.database import get_db
from sayou.catalog.models import generate_uuid
from sayou.catalog.queries import (
    add_member,
    check_permission,
    create_file,
    create_version,
    duplicate_file,
    ensure_default_workspace,
    get_file_by_path,
    get_file_versions,
    get_index_cache,
    get_subfolder_stats,
    get_version_by_number,
    get_workspace_by_slug,
    kv_delete,
    kv_get,
    kv_list,
    kv_set,
    list_all_files,
    list_files_by_glob,
    list_files_in_folder,
    list_subfolders,
    log_mutation,
    query_mutation_log,
    search_files_by_frontmatter,
    search_files_content,
    search_files_fulltext,
    soft_delete_file,
    update_file_current_version,
    update_file_path,
    upsert_index_cache,
)
from sayou.core.frontmatter import parse_frontmatter
from sayou.core.index import generate_folder_index, generate_root_index
from sayou.core.summarize import summarize_content
from sayou.storage.s3 import StorageService


class AccessDeniedError(Exception):
    pass


class FileNotFoundError(Exception):
    pass


class FileExistsError(Exception):
    pass


class WorkspaceService:
    def __init__(self, storage: StorageService | None = None, _get_db=None):
        self.storage = storage or StorageService()
        self._custom_get_db = _get_db

    async def close(self):
        """Close underlying resources (S3 client, etc.)."""
        if self.storage is not None:
            await self.storage.close()

    async def _resolve_workspace(self, session, org_id: str, user_id: str, slug: str):
        """Get workspace, auto-create 'default' if needed."""
        if slug == "default":
            return await ensure_default_workspace(session, org_id, user_id)
        ws = await get_workspace_by_slug(session, org_id, slug)
        if ws is None:
            raise FileNotFoundError(f"Workspace '{slug}' not found")
        return ws

    async def _check_role(self, session, workspace_id: str, user_id: str, required: str):
        """Check permission or raise AccessDeniedError."""
        has_perm = await check_permission(session, workspace_id, user_id, required)
        if not has_perm:
            raise AccessDeniedError(
                f"User {user_id} lacks '{required}' permission on workspace"
            )

    @staticmethod
    def _extract_path_parts(path: str) -> tuple[str, str, str]:
        """Return (clean_path, folder_path, filename)."""
        clean = path.strip("/")
        parts = clean.rsplit("/", 1)
        if len(parts) == 1:
            return clean, "/", clean
        return clean, parts[0] + "/", parts[1]

    @staticmethod
    def _parent_folder(folder_path: str) -> str:
        """Return the parent folder path. '/' is its own parent."""
        if folder_path == "/":
            return "/"
        clean = folder_path.rstrip("/")
        parts = clean.rsplit("/", 1)
        if len(parts) == 1:
            return "/"
        return parts[0] + "/"

    async def _regenerate_index_chain(
        self, session, org_id: str, workspace_id: str, folder_path: str
    ):
        """Regenerate index for the given folder and all ancestors up to root."""
        current = folder_path
        visited = set()
        while current not in visited:
            visited.add(current)
            files = await list_files_in_folder(session, org_id, workspace_id, current)
            if current == "/":
                subfolder_stats = await get_subfolder_stats(
                    session, org_id, workspace_id, "/"
                )
                content = generate_root_index(subfolder_stats, files)
            else:
                content = generate_folder_index(current, files)
            await upsert_index_cache(
                session, org_id, workspace_id, current, content, len(files)
            )
            if current == "/":
                break
            current = self._parent_folder(current)

    @staticmethod
    def _is_text_content_type(content_type: str) -> bool:
        """Check if a content_type represents text (supports frontmatter parsing)."""
        return content_type.startswith("text/") or content_type in (
            "application/json", "application/xml", "application/yaml",
        )

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        """Guess content_type from filename extension."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        text_types = {
            "md": "text/markdown", "txt": "text/plain", "json": "application/json",
            "yaml": "application/yaml", "yml": "application/yaml",
            "xml": "application/xml", "html": "text/html", "css": "text/css",
            "js": "text/javascript", "ts": "text/typescript",
            "py": "text/x-python", "rs": "text/x-rust", "go": "text/x-go",
            "csv": "text/csv", "toml": "text/x-toml", "ini": "text/x-ini",
        }
        binary_types = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
            "pdf": "application/pdf", "zip": "application/zip",
            "tar": "application/x-tar", "gz": "application/gzip",
            "mp3": "audio/mpeg", "wav": "audio/wav",
            "mp4": "video/mp4", "webm": "video/webm",
        }
        return text_types.get(ext) or binary_types.get(ext) or "text/markdown"

    async def write(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        content: str | bytes,
        source: str | None = None,
        content_type: str | None = None,
    ) -> dict:
        """Write a file to the workspace. Accepts str for text or bytes for binary."""
        clean_path, folder_path, filename = self._extract_path_parts(path)

        # Determine content type
        if content_type is None:
            if isinstance(content, bytes):
                content_type = self._guess_content_type(filename)
            else:
                content_type = self._guess_content_type(filename)
        is_text = self._is_text_content_type(content_type)

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            # Parse frontmatter only for text content
            frontmatter = None
            body = None
            if is_text:
                text_content = content if isinstance(content, str) else content.decode("utf-8")
                frontmatter, body = parse_frontmatter(text_content)

            # Upload to storage
            version_id = generate_uuid()
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            else:
                content_bytes = content
            s3_key, s3_bucket, size_bytes, content_hash = await self.storage.upload_version(
                content_bytes, org_id, ws.id, version_id, content_type=content_type
            )

            # Get or create file record
            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                file = await create_file(
                    session, org_id, ws.id, clean_path, folder_path, filename,
                    content_type=content_type,
                    frontmatter=frontmatter or None,
                    content_text=body or None,
                )

            # Create version
            new_version_number = file.version_count + 1
            version = await create_version(
                session, file.id, new_version_number, s3_key, s3_bucket,
                size_bytes, content_hash, user_id,
            )

            # Update file pointer
            await update_file_current_version(
                session, file.id, version.id, new_version_number,
                frontmatter=frontmatter or None,
                content_text=body if is_text else None,
            )

            # Log mutation
            await log_mutation(
                session, org_id, ws.id, source, "write", clean_path, version.id
            )

            # Regenerate parent index
            await self._regenerate_index_chain(session, org_id, ws.id, folder_path)

        return {
            "path": clean_path,
            "version_number": new_version_number,
            "version_id": version.id,
            "size_bytes": size_bytes,
            "content_hash": content_hash,
            "content_type": content_type,
        }

    async def read(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        token_budget: int = 4000,
        version_number: int | None = None,
    ) -> dict:
        """Read a file from the workspace. Optionally read a specific version."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            # Get the requested version
            if version_number is not None:
                target = await get_version_by_number(session, file.id, version_number)
                if target is None:
                    raise FileNotFoundError(
                        f"Version {version_number} not found for: {clean_path}"
                    )
            else:
                versions = await get_file_versions(session, file.id, limit=1)
                if not versions:
                    raise FileNotFoundError(f"No versions found for: {clean_path}")
                target = versions[0]

            content_bytes = await self.storage.download_version(target.s3_key, target.s3_bucket)

            is_text = self._is_text_content_type(file.content_type)

            # Parse frontmatter for response
            frontmatter = {}
            if file.frontmatter:
                try:
                    frontmatter = json.loads(file.frontmatter)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Binary files: return base64-encoded content
            if not is_text:
                content_b64 = base64.b64encode(content_bytes).decode("ascii")
                return {
                    "path": clean_path,
                    "content": content_b64,
                    "content_type": file.content_type,
                    "encoding": "base64",
                    "version_number": target.version_number,
                    "frontmatter": frontmatter,
                    "size_bytes": target.size_bytes,
                    "truncated": False,
                }

            content = content_bytes.decode("utf-8")

            # Apply token budget
            char_budget = token_budget * 4
            truncated = False
            sections = None
            total_lines = None

            if len(content) > char_budget:
                # For very small budgets (< frontmatter size), fall back to simple truncation
                fm_size = len(json.dumps(frontmatter)) if frontmatter else 0
                if char_budget < fm_size + 100:
                    content = content[:char_budget]
                    truncated = True
                else:
                    summary_result = summarize_content(content, frontmatter, char_budget)
                    content = summary_result["summary"]
                    sections = summary_result["sections"]
                    total_lines = summary_result["total_lines"]
                    truncated = True

        result = {
            "path": clean_path,
            "content": content,
            "content_type": file.content_type,
            "version_number": target.version_number,
            "frontmatter": frontmatter,
            "size_bytes": target.size_bytes,
            "truncated": truncated,
        }
        if sections is not None:
            result["sections"] = sections
        if total_lines is not None:
            result["total_lines"] = total_lines
        return result

    async def list_folder(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str = "/",
        recursive: bool = False,
    ) -> dict:
        """List files and subfolders in a folder."""
        folder_path = path.strip("/") + "/" if path != "/" else "/"
        if folder_path == "//":
            folder_path = "/"

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            if recursive:
                prefix = None if folder_path == "/" else folder_path.rstrip("/")
                files = await list_all_files(session, org_id, ws.id, prefix)
            else:
                files = await list_files_in_folder(session, org_id, ws.id, folder_path)

            # Regenerate index on-demand
            index_content = generate_folder_index(folder_path, files)
            await upsert_index_cache(
                session, org_id, ws.id, folder_path, index_content, len(files)
            )

            subfolders = await list_subfolders(session, org_id, ws.id, folder_path)

            file_list = [
                {
                    "path": f.path,
                    "filename": f.filename,
                    "version_count": f.version_count,
                    "frontmatter": json.loads(f.frontmatter) if f.frontmatter else {},
                }
                for f in files
            ]

        return {
            "path": path,
            "files": file_list,
            "subfolders": subfolders,
            "index_content": index_content,
            "file_count": len(files),
        }

    async def search(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        query: str | None = None,
        filters: dict | None = None,
    ) -> dict:
        """Search files by frontmatter filters and/or full-text query."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            results = None

            if filters:
                fm_results = await search_files_by_frontmatter(
                    session, org_id, ws.id, filters
                )
                fm_ids = {f.id for f in fm_results}
                results = fm_results

            if query:
                ft_results = await search_files_fulltext(session, org_id, ws.id, query)
                if results is not None:
                    # Intersection
                    results = [f for f in ft_results if f.id in fm_ids]
                else:
                    results = ft_results

            if results is None:
                results = []

            result_list = [
                {
                    "path": f.path,
                    "filename": f.filename,
                    "frontmatter": json.loads(f.frontmatter) if f.frontmatter else {},
                }
                for f in results
            ]

        return {"results": result_list, "total": len(result_list)}

    async def glob_files(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        pattern: str,
    ) -> dict:
        """Find files matching a glob pattern."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            files = await list_files_by_glob(session, org_id, ws.id, pattern)

            file_list = [
                {
                    "path": f.path,
                    "filename": f.filename,
                    "version_count": f.version_count,
                    "frontmatter": json.loads(f.frontmatter) if f.frontmatter else {},
                }
                for f in files
            ]

        return {"pattern": pattern, "files": file_list, "total": len(file_list)}

    async def grep_files(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        query: str,
        path_pattern: str | None = None,
        context_lines: int = 2,
    ) -> dict:
        """Search file content for a query string, returning matching lines with context."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            files = await search_files_content(
                session, org_id, ws.id, query, path_pattern
            )

            matches = []
            for f in files:
                if not f.content_text:
                    continue
                lines = f.content_text.split("\n")
                query_lower = query.lower()
                matched_lines = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        # Gather context
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = []
                        for j in range(start, end):
                            marker = ">" if j == i else " "
                            context.append(f"{f.path}:{j + 1}:{marker} {lines[j]}")
                        matched_lines.append({
                            "line_number": i + 1,
                            "context": "\n".join(context),
                        })

                if matched_lines:
                    matches.append({
                        "path": f.path,
                        "matches": matched_lines,
                        "match_count": len(matched_lines),
                    })

        return {"query": query, "results": matches, "total_files": len(matches)}

    async def delete(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        source: str | None = None,
    ) -> dict:
        """Soft-delete a file."""
        clean_path = path.strip("/")
        _, folder_path, _ = self._extract_path_parts(path)

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            await soft_delete_file(session, file.id)
            await log_mutation(session, org_id, ws.id, source, "delete", clean_path)
            await self._regenerate_index_chain(session, org_id, ws.id, folder_path)

        return {"path": clean_path, "deleted": True}

    async def move(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        source_path: str,
        dest_path: str,
        source_agent: str | None = None,
    ) -> dict:
        """Move a file to a new path (catalog-only, no S3 operations)."""
        clean_src = source_path.strip("/")
        clean_dst = dest_path.strip("/")
        _, src_folder, _ = self._extract_path_parts(source_path)
        dst_clean, dst_folder, dst_filename = self._extract_path_parts(dest_path)

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            file = await get_file_by_path(session, org_id, ws.id, clean_src)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_src}")

            existing = await get_file_by_path(session, org_id, ws.id, clean_dst)
            if existing is not None:
                raise FileExistsError(f"Destination already exists: {clean_dst}")

            await update_file_path(session, file.id, dst_clean, dst_folder, dst_filename)
            await log_mutation(
                session, org_id, ws.id, source_agent, "move",
                f"{clean_src} -> {clean_dst}",
            )

            # Regenerate indexes for both old and new parent folders
            await self._regenerate_index_chain(session, org_id, ws.id, src_folder)
            if dst_folder != src_folder:
                await self._regenerate_index_chain(session, org_id, ws.id, dst_folder)

        return {"source": clean_src, "destination": clean_dst, "moved": True}

    async def copy(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        source_path: str,
        dest_path: str,
        source_agent: str | None = None,
    ) -> dict:
        """Copy a file to a new path. Creates new file record pointing to same S3 object."""
        clean_src = source_path.strip("/")
        clean_dst = dest_path.strip("/")
        _, dst_folder, dst_filename = self._extract_path_parts(dest_path)

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            file = await get_file_by_path(session, org_id, ws.id, clean_src)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_src}")

            existing = await get_file_by_path(session, org_id, ws.id, clean_dst)
            if existing is not None:
                raise FileExistsError(f"Destination already exists: {clean_dst}")

            new_file, new_version = await duplicate_file(
                session, file, clean_dst, dst_folder, dst_filename, user_id
            )
            await log_mutation(
                session, org_id, ws.id, source_agent, "copy",
                f"{clean_src} -> {clean_dst}",
                version_id=new_version.id if new_version else None,
            )

            await self._regenerate_index_chain(session, org_id, ws.id, dst_folder)

        return {"source": clean_src, "destination": clean_dst, "copied": True}

    async def history(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        limit: int = 20,
    ) -> dict:
        """Get version history for a file."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            versions = await get_file_versions(session, file.id, limit=limit)

            version_list = [
                {
                    "version_number": v.version_number,
                    "version_id": v.id,
                    "size_bytes": v.size_bytes,
                    "content_hash": v.content_hash,
                    "created_by": v.created_by,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions
            ]

        return {"path": clean_path, "versions": version_list, "total": len(version_list)}

    async def diff(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        version_a: int,
        version_b: int,
    ) -> dict:
        """Compare two versions of a file using unified diff."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            va = await get_version_by_number(session, file.id, version_a)
            if va is None:
                raise FileNotFoundError(
                    f"Version {version_a} not found for: {clean_path}"
                )
            vb = await get_version_by_number(session, file.id, version_b)
            if vb is None:
                raise FileNotFoundError(
                    f"Version {version_b} not found for: {clean_path}"
                )

            content_a = (await self.storage.download_version(va.s3_key, va.s3_bucket)).decode("utf-8")
            content_b = (await self.storage.download_version(vb.s3_key, vb.s3_bucket)).decode("utf-8")

        lines_a = content_a.splitlines(keepends=True)
        lines_b = content_b.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            lines_a, lines_b,
            fromfile=f"{clean_path} v{version_a}",
            tofile=f"{clean_path} v{version_b}",
        ))
        diff_text = "".join(diff_lines)

        return {
            "path": clean_path,
            "version_a": version_a,
            "version_b": version_b,
            "diff": diff_text,
            "has_changes": len(diff_lines) > 0,
        }

    async def audit_log(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        *,
        path: str | None = None,
        action: str | None = None,
        agent_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> dict:
        """Query the mutation audit log for the workspace."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            entries = await query_mutation_log(
                session,
                org_id,
                ws.id,
                file_path=path,
                action=action,
                agent_id=agent_id,
                since=since,
                until=until,
                limit=limit,
            )

            entry_list = [
                {
                    "action": e.action,
                    "file_path": e.file_path,
                    "agent_id": e.agent_id,
                    "version_id": e.version_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ]

        return {"entries": entry_list, "total": len(entry_list)}

    # ── KV Store ────────────────────────────────────────────────────

    async def kv_get(
        self, org_id: str, user_id: str, workspace_slug: str, key: str
    ) -> dict:
        """Get a KV entry."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")
            entry = await kv_get(session, org_id, ws.id, key)
            if entry is None:
                return {"key": key, "found": False}
            return {
                "key": entry.key,
                "value": json.loads(entry.value),
                "found": True,
                "ttl_seconds": entry.ttl_seconds,
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            }

    async def kv_set(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        key: str,
        value,
        ttl_seconds: int | None = None,
    ) -> dict:
        """Set a KV entry."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")
            value_str = json.dumps(value)
            entry = await kv_set(session, org_id, ws.id, key, value_str, ttl_seconds)
            return {
                "key": entry.key,
                "ttl_seconds": entry.ttl_seconds,
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
                "written": True,
            }

    async def kv_delete(
        self, org_id: str, user_id: str, workspace_slug: str, key: str
    ) -> dict:
        """Delete a KV entry."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")
            deleted = await kv_delete(session, org_id, ws.id, key)
            return {"key": key, "deleted": deleted}

    async def kv_list(
        self, org_id: str, user_id: str, workspace_slug: str, prefix: str | None = None
    ) -> dict:
        """List KV entries, optionally filtered by key prefix."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")
            entries = await kv_list(session, org_id, ws.id, prefix)
            items = [
                {
                    "key": e.key,
                    "value": json.loads(e.value),
                    "ttl_seconds": e.ttl_seconds,
                    "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                }
                for e in entries
            ]
            return {"items": items, "total": len(items)}

    # ── Context-aware Read ──────────────────────────────────────────

    async def read_section(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        line_start: int,
        line_end: int,
    ) -> dict:
        """Read a specific line range from a file (1-indexed, inclusive)."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            versions = await get_file_versions(session, file.id, limit=1)
            if not versions:
                raise FileNotFoundError(f"No versions found for: {clean_path}")
            target = versions[0]

            content_bytes = await self.storage.download_version(target.s3_key, target.s3_bucket)
            content = content_bytes.decode("utf-8")

        lines = content.split("\n")
        total_lines = len(lines)
        # Convert to 0-indexed
        start = max(0, line_start - 1)
        end = min(total_lines, line_end)
        section = "\n".join(lines[start:end])

        return {
            "path": clean_path,
            "line_start": line_start,
            "line_end": line_end,
            "total_lines": total_lines,
            "content": section,
        }
