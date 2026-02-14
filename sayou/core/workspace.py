import json

from sayou.catalog.database import get_db
from sayou.catalog.models import generate_uuid
from sayou.catalog.queries import (
    add_member,
    check_permission,
    create_file,
    create_version,
    ensure_default_workspace,
    get_file_by_path,
    get_file_versions,
    get_index_cache,
    get_version_by_number,
    get_workspace_by_slug,
    list_all_files,
    list_files_by_glob,
    list_files_in_folder,
    list_subfolders,
    log_mutation,
    search_files_by_frontmatter,
    search_files_content,
    search_files_fulltext,
    soft_delete_file,
    update_file_current_version,
    upsert_index_cache,
)
from sayou.core.frontmatter import parse_frontmatter
from sayou.core.index import generate_folder_index
from sayou.storage.s3 import StorageService


class AccessDeniedError(Exception):
    pass


class FileNotFoundError(Exception):
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

    async def _regenerate_parent_index(
        self, session, org_id: str, workspace_id: str, folder_path: str
    ):
        """Regenerate index for the given folder."""
        files = await list_files_in_folder(session, org_id, workspace_id, folder_path)
        content = generate_folder_index(folder_path, files)
        await upsert_index_cache(session, org_id, workspace_id, folder_path, content, len(files))

    async def write(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        content: str,
        source: str | None = None,
    ) -> dict:
        """Write a file to the workspace."""
        clean_path, folder_path, filename = self._extract_path_parts(path)

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            # Parse frontmatter
            frontmatter, body = parse_frontmatter(content)

            # Upload to S3
            version_id = generate_uuid()
            content_bytes = content.encode("utf-8")
            s3_key, s3_bucket, size_bytes, content_hash = await self.storage.upload_version(
                content_bytes, org_id, ws.id, version_id
            )

            # Get or create file record
            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                file = await create_file(
                    session, org_id, ws.id, clean_path, folder_path, filename,
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
                content_text=body or None,
            )

            # Log mutation
            await log_mutation(
                session, org_id, ws.id, source, "write", clean_path, version.id
            )

            # Regenerate parent index
            await self._regenerate_parent_index(session, org_id, ws.id, folder_path)

        return {
            "path": clean_path,
            "version_number": new_version_number,
            "version_id": version.id,
            "size_bytes": size_bytes,
            "content_hash": content_hash,
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
            content = content_bytes.decode("utf-8")

            # Truncate if exceeds budget
            char_budget = token_budget * 4
            truncated = False
            if len(content) > char_budget:
                content = content[:char_budget]
                truncated = True

            # Parse frontmatter for response
            frontmatter = {}
            if file.frontmatter:
                try:
                    frontmatter = json.loads(file.frontmatter)
                except (json.JSONDecodeError, TypeError):
                    pass

        return {
            "path": clean_path,
            "content": content,
            "version_number": target.version_number,
            "frontmatter": frontmatter,
            "size_bytes": target.size_bytes,
            "truncated": truncated,
        }

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
            await self._regenerate_parent_index(session, org_id, ws.id, folder_path)

        return {"path": clean_path, "deleted": True}

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
