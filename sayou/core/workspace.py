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
    get_file_by_path_including_deleted,
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
    search_files_fts,
    search_files_fulltext,
    search_files_mysql_fts,
    soft_delete_file,
    update_file_current_version,
    update_file_path,
    upsert_index_cache,
)
from sayou.catalog.queries_schema import (
    delete_schema,
    get_schema,
    upsert_schema_field,
)
from sayou.catalog.queries_embeddings import (
    delete_embeddings_for_file,
    get_all_embeddings,
    get_embedding_for_file,
    upsert_embedding,
)
from sayou.catalog.queries_links import (
    delete_auto_links_for_source,
    delete_link as delete_link_query,
    delete_links_for_source,
    get_graph_summary,
    get_links_from,
    get_links_to,
    get_neighbors,
    update_links_on_move,
    upsert_link,
)
from sayou.catalog.queries_chunks import (
    delete_chunks_for_file,
    get_chunk_by_index,
    get_chunks_for_file,
    replace_chunks_for_file,
    search_chunks as search_chunks_query,
    search_chunks_fts as search_chunks_fts_query,
    search_chunks_mysql_fts as search_chunks_mysql_fts_query,
)
from sayou.core.auto_metadata import (
    NullMetadataProvider,
    merge_auto_metadata,
)
from sayou.core.chunking import get_chunker
from sayou.core.embeddings import (
    NullEmbeddingProvider,
    content_hash as compute_content_hash,
    cosine_similarity,
    get_embedding_provider,
    pack_embedding,
    prepare_embedding_input,
    unpack_embedding,
)
from sayou.core.frontmatter import parse_frontmatter
from sayou.core.links import extract_links_from_frontmatter, extract_links_from_markdown, resolve_relative_path
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
    def __init__(
        self,
        storage: StorageService | None = None,
        _get_db=None,
        embedding_provider=None,
        metadata_provider=None,
        auto_metadata_enabled: bool = False,
    ):
        self.storage = storage or StorageService()
        self._custom_get_db = _get_db
        self._embedding_provider = embedding_provider
        self._metadata_provider = metadata_provider
        self._auto_metadata_enabled = auto_metadata_enabled

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

            # Get or create file record (check for soft-deleted files first)
            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                # Check if a soft-deleted file exists at this path
                deleted_file = await get_file_by_path_including_deleted(
                    session, org_id, ws.id, clean_path
                )
                if deleted_file is not None:
                    # Restore the soft-deleted file
                    deleted_file.deleted_at = None
                    deleted_file.content_type = content_type
                    if frontmatter:
                        deleted_file.frontmatter = json.dumps(frontmatter)
                    if body is not None:
                        deleted_file.content_text = body
                    await session.flush()
                    file = deleted_file
                else:
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

            # Auto-chunk text content
            if is_text and body:
                chunker = get_chunker(content_type)
                chunk_results = chunker.chunk(body)
                if chunk_results:
                    chunk_dicts = [
                        {
                            "chunk_index": c.chunk_index,
                            "heading": c.heading,
                            "heading_level": c.heading_level,
                            "content": c.content,
                            "line_start": c.line_start,
                            "line_end": c.line_end,
                            "char_count": c.char_count,
                            "token_estimate": c.token_estimate,
                            "content_hash": c.content_hash,
                        }
                        for c in chunk_results
                    ]
                    await replace_chunks_for_file(
                        session, org_id, ws.id, file.id, version.id, chunk_dicts
                    )

            # Auto-detect links from content and frontmatter
            if is_text:
                await delete_auto_links_for_source(session, org_id, ws.id, clean_path)
                all_links = []
                if body:
                    all_links.extend(extract_links_from_markdown(body))
                if frontmatter:
                    all_links.extend(extract_links_from_frontmatter(frontmatter))
                for link_info in all_links:
                    target = resolve_relative_path(
                        clean_path, link_info["target_path"]
                    )
                    await upsert_link(
                        session, org_id, ws.id,
                        source_path=clean_path,
                        target_path=target,
                        link_type=link_info["link_type"],
                        auto_detected=True,
                        context=link_info.get("context"),
                        created_by=source or user_id,
                    )

            # Compute embedding if provider configured
            if is_text and self._embedding_provider and not isinstance(
                self._embedding_provider, NullEmbeddingProvider
            ):
                try:
                    embed_input = prepare_embedding_input(frontmatter, body or "")
                    c_hash = compute_content_hash(embed_input)
                    # Check if content changed (skip re-embed)
                    existing_emb = await get_embedding_for_file(
                        session, file.id,
                        self._embedding_provider.provider_name,
                        self._embedding_provider.model_name,
                    )
                    if not existing_emb or existing_emb.content_hash != c_hash:
                        vector = await self._embedding_provider.embed(embed_input)
                        if vector:
                            await upsert_embedding(
                                session, org_id, ws.id, file.id, version.id,
                                provider=self._embedding_provider.provider_name,
                                model=self._embedding_provider.model_name,
                                dimensions=self._embedding_provider.dimensions,
                                embedding=pack_embedding(vector),
                                content_hash=c_hash,
                            )
                except Exception:
                    pass  # Embedding failure never blocks writes

            # Auto-metadata generation (non-blocking)
            if (
                is_text and body
                and self._auto_metadata_enabled
                and self._metadata_provider
                and not isinstance(self._metadata_provider, NullMetadataProvider)
            ):
                try:
                    # Get existing schema for consistency
                    schema_entries = await get_schema(session, org_id, ws.id)
                    schema_dicts = [
                        {
                            "field_name": s.field_name,
                            "sample_values": json.loads(s.sample_values) if s.sample_values else [],
                        }
                        for s in schema_entries
                    ]
                    auto_meta = await self._metadata_provider.generate(
                        body, existing_schema=schema_dicts
                    )
                    if auto_meta:
                        merged = merge_auto_metadata(frontmatter or {}, auto_meta)
                        await update_file_current_version(
                            session, file.id, version.id, new_version_number,
                            frontmatter=merged,
                        )
                except Exception:
                    pass  # Auto-metadata failure never blocks writes

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
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
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
                # Try ranked full-text search, fall back to LIKE
                # SQLite FTS5 → MySQL FULLTEXT → LIKE
                try:
                    ft_results = await search_files_fts(session, org_id, ws.id, query)
                except Exception:
                    try:
                        ft_results = await search_files_mysql_fts(session, org_id, ws.id, query)
                    except Exception:
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
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
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
            await delete_chunks_for_file(session, file.id)
            await delete_embeddings_for_file(session, file.id)
            await delete_links_for_source(session, org_id, ws.id, clean_path)
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
            await update_links_on_move(session, org_id, ws.id, clean_src, clean_dst)
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

    # ── Chunks ─────────────────────────────────────────────────────

    async def get_chunks(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
    ) -> dict:
        """Get chunk outline for a file."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            chunks = await get_chunks_for_file(session, file.id)

            chunk_list = [
                {
                    "chunk_index": c.chunk_index,
                    "heading": c.heading,
                    "heading_level": c.heading_level,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "char_count": c.char_count,
                    "token_estimate": c.token_estimate,
                }
                for c in chunks
            ]

        return {"path": clean_path, "chunks": chunk_list, "total": len(chunk_list)}

    async def get_chunk(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        chunk_index: int,
    ) -> dict:
        """Read a specific chunk by index."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            chunk = await get_chunk_by_index(session, file.id, chunk_index)
            if chunk is None:
                raise FileNotFoundError(
                    f"Chunk {chunk_index} not found for: {clean_path}"
                )

        return {
            "path": clean_path,
            "chunk_index": chunk.chunk_index,
            "heading": chunk.heading,
            "heading_level": chunk.heading_level,
            "content": chunk.content,
            "line_start": chunk.line_start,
            "line_end": chunk.line_end,
            "char_count": chunk.char_count,
            "token_estimate": chunk.token_estimate,
        }

    async def search_chunks(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        query: str,
        path_pattern: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search chunks by content."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            # Try ranked full-text search, fall back to LIKE
            # SQLite FTS5 → MySQL FULLTEXT → LIKE
            try:
                results = await search_chunks_fts_query(
                    session, org_id, ws.id, query,
                    path_pattern=path_pattern, limit=limit,
                )
            except Exception:
                try:
                    results = await search_chunks_mysql_fts_query(
                        session, org_id, ws.id, query,
                        path_pattern=path_pattern, limit=limit,
                    )
                except Exception:
                    results = await search_chunks_query(
                        session, org_id, ws.id, query,
                        path_pattern=path_pattern, limit=limit,
                    )

            result_list = [
                {
                    "path": r["path"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk"].chunk_index,
                    "heading": r["chunk"].heading,
                    "line_start": r["chunk"].line_start,
                    "line_end": r["chunk"].line_end,
                    "token_estimate": r["chunk"].token_estimate,
                    "content_preview": r["chunk"].content[:200],
                }
                for r in results
            ]

        return {"query": query, "results": result_list, "total": len(result_list)}

    # ── Semantic Search ─────────────────────────────────────────────

    async def semantic_search(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        query: str,
        top_k: int = 10,
    ) -> dict:
        """Search files by meaning using vector embeddings.

        Falls back to text search if no embedding provider configured.
        """
        if not self._embedding_provider or isinstance(
            self._embedding_provider, NullEmbeddingProvider
        ):
            # Fallback to fulltext search
            return await self.search(
                org_id, user_id, workspace_slug, query=query
            )

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            # Embed the query
            query_vector = await self._embedding_provider.embed(query)
            if not query_vector:
                return {"results": [], "total": 0, "fallback": True}

            # Get all embeddings for this workspace
            embeddings = await get_all_embeddings(
                session, org_id, ws.id,
                provider=self._embedding_provider.provider_name,
                model=self._embedding_provider.model_name,
            )

            if not embeddings:
                return {"results": [], "total": 0, "fallback": False}

            # Compute similarities
            scored = []
            file_ids = {e.file_id for e in embeddings}
            # Batch fetch file info
            from sqlalchemy import select as sa_select
            from sayou.catalog.models import SayouFile
            file_result = await session.execute(
                sa_select(SayouFile).where(
                    SayouFile.id.in_(file_ids),
                    SayouFile.deleted_at.is_(None),
                )
            )
            file_map = {f.id: f for f in file_result.scalars().all()}

            for emb in embeddings:
                file = file_map.get(emb.file_id)
                if not file:
                    continue
                stored_vector = unpack_embedding(emb.embedding)
                score = cosine_similarity(query_vector, stored_vector)
                scored.append({
                    "path": file.path,
                    "filename": file.filename,
                    "score": round(score, 4),
                    "frontmatter": {},
                })
                if file.frontmatter:
                    try:
                        scored[-1]["frontmatter"] = json.loads(file.frontmatter)
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Sort by score descending
            scored.sort(key=lambda x: x["score"], reverse=True)
            top_results = scored[:top_k]

        return {
            "query": query,
            "results": top_results,
            "total": len(top_results),
            "fallback": False,
        }

    async def reindex_embeddings(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
    ) -> dict:
        """Recompute embeddings for all files in the workspace."""
        if not self._embedding_provider or isinstance(
            self._embedding_provider, NullEmbeddingProvider
        ):
            return {"reindexed": 0, "error": "No embedding provider configured"}

        _db = self._custom_get_db or get_db
        reindexed = 0
        skipped = 0
        errors = 0

        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            from sayou.catalog.queries import list_all_files
            files = await list_all_files(session, org_id, ws.id)

            for file in files:
                if not self._is_text_content_type(file.content_type):
                    skipped += 1
                    continue

                try:
                    fm = {}
                    if file.frontmatter:
                        try:
                            fm = json.loads(file.frontmatter)
                        except (json.JSONDecodeError, TypeError):
                            pass

                    embed_input = prepare_embedding_input(fm, file.content_text or "")
                    c_hash = compute_content_hash(embed_input)

                    # Check if already up to date
                    existing = await get_embedding_for_file(
                        session, file.id,
                        self._embedding_provider.provider_name,
                        self._embedding_provider.model_name,
                    )
                    if existing and existing.content_hash == c_hash:
                        skipped += 1
                        continue

                    vector = await self._embedding_provider.embed(embed_input)
                    if vector:
                        await upsert_embedding(
                            session, org_id, ws.id, file.id,
                            file.current_version_id or "",
                            provider=self._embedding_provider.provider_name,
                            model=self._embedding_provider.model_name,
                            dimensions=self._embedding_provider.dimensions,
                            embedding=pack_embedding(vector),
                            content_hash=c_hash,
                        )
                        reindexed += 1
                except Exception:
                    errors += 1

        return {"reindexed": reindexed, "skipped": skipped, "errors": errors}

    # ── Schema & Auto-Metadata ─────────────────────────────────────

    async def get_schema(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
    ) -> dict:
        """Discover frontmatter schema: field names, types, occurrences."""
        from sayou.core.schema_discovery import discover_schema

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            # Scan all files for frontmatter
            from sayou.catalog.queries import list_all_files
            files = await list_all_files(session, org_id, ws.id)
            frontmatters = []
            for f in files:
                if f.frontmatter:
                    try:
                        frontmatters.append(json.loads(f.frontmatter))
                    except (json.JSONDecodeError, TypeError):
                        pass

            schema = discover_schema(frontmatters)

            # Cache in DB
            await delete_schema(session, org_id, ws.id)
            for field in schema:
                await upsert_schema_field(
                    session, org_id, ws.id,
                    field_name=field["field_name"],
                    field_type=field["field_type"],
                    occurrence_count=field["occurrence_count"],
                    sample_values=field["sample_values"],
                    is_auto=field["is_auto"],
                )

        return {
            "fields": schema,
            "total_fields": len(schema),
            "total_files_scanned": len(frontmatters),
        }

    async def refresh_schema(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
    ) -> dict:
        """Refresh the cached schema (alias for get_schema)."""
        return await self.get_schema(org_id, user_id, workspace_slug)

    async def generate_metadata(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
    ) -> dict:
        """Generate _auto_ metadata for a single file via LLM."""
        if not self._metadata_provider or isinstance(
            self._metadata_provider, NullMetadataProvider
        ):
            return {"path": path, "error": "No metadata provider configured"}

        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            file = await get_file_by_path(session, org_id, ws.id, clean_path)
            if file is None:
                raise FileNotFoundError(f"File not found: {clean_path}")

            if not file.content_text:
                return {"path": clean_path, "generated": {}}

            # Get schema for consistency
            schema_entries = await get_schema(session, org_id, ws.id)
            schema_dicts = [
                {
                    "field_name": s.field_name,
                    "sample_values": json.loads(s.sample_values) if s.sample_values else [],
                }
                for s in schema_entries
            ]

            auto_meta = await self._metadata_provider.generate(
                file.content_text, existing_schema=schema_dicts
            )

            if auto_meta:
                existing_fm = {}
                if file.frontmatter:
                    try:
                        existing_fm = json.loads(file.frontmatter)
                    except (json.JSONDecodeError, TypeError):
                        pass
                merged = merge_auto_metadata(existing_fm, auto_meta)
                await update_file_current_version(
                    session, file.id, file.current_version_id,
                    file.version_count, frontmatter=merged,
                )

        return {"path": clean_path, "generated": auto_meta}

    async def bulk_generate_metadata(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path_pattern: str | None = None,
    ) -> dict:
        """Bulk generate _auto_ metadata for all files or matching pattern."""
        if not self._metadata_provider or isinstance(
            self._metadata_provider, NullMetadataProvider
        ):
            return {"generated": 0, "error": "No metadata provider configured"}

        _db = self._custom_get_db or get_db
        generated = 0
        skipped = 0
        errors = 0

        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            from sayou.catalog.queries import list_all_files, list_files_by_glob
            if path_pattern:
                files = await list_files_by_glob(session, org_id, ws.id, path_pattern)
            else:
                files = await list_all_files(session, org_id, ws.id)

            # Get schema once for all files
            schema_entries = await get_schema(session, org_id, ws.id)
            schema_dicts = [
                {
                    "field_name": s.field_name,
                    "sample_values": json.loads(s.sample_values) if s.sample_values else [],
                }
                for s in schema_entries
            ]

            for file in files:
                if not self._is_text_content_type(file.content_type):
                    skipped += 1
                    continue
                if not file.content_text:
                    skipped += 1
                    continue

                try:
                    auto_meta = await self._metadata_provider.generate(
                        file.content_text, existing_schema=schema_dicts
                    )
                    if auto_meta:
                        existing_fm = {}
                        if file.frontmatter:
                            try:
                                existing_fm = json.loads(file.frontmatter)
                            except (json.JSONDecodeError, TypeError):
                                pass
                        merged = merge_auto_metadata(existing_fm, auto_meta)
                        await update_file_current_version(
                            session, file.id, file.current_version_id,
                            file.version_count, frontmatter=merged,
                        )
                        generated += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1

        return {"generated": generated, "skipped": skipped, "errors": errors}

    # ── Links / Knowledge Graph ──────────────────────────────────────

    async def get_links(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
    ) -> dict:
        """Get outgoing and incoming links for a file."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            outgoing = await get_links_from(session, org_id, ws.id, clean_path)
            incoming = await get_links_to(session, org_id, ws.id, clean_path)

            def _link_dict(link):
                return {
                    "source_path": link.source_path,
                    "target_path": link.target_path,
                    "link_type": link.link_type,
                    "auto_detected": link.auto_detected,
                    "context": link.context,
                    "created_by": link.created_by,
                }

        return {
            "path": clean_path,
            "outgoing": [_link_dict(l) for l in outgoing],
            "incoming": [_link_dict(l) for l in incoming],
        }

    async def add_link(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        source_path: str,
        target_path: str,
        link_type: str = "reference",
        context: str | None = None,
    ) -> dict:
        """Manually add a link between two files."""
        clean_src = source_path.strip("/")
        clean_tgt = target_path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            link = await upsert_link(
                session, org_id, ws.id,
                source_path=clean_src,
                target_path=clean_tgt,
                link_type=link_type,
                auto_detected=False,
                context=context,
                created_by=user_id,
            )

        return {
            "source_path": link.source_path,
            "target_path": link.target_path,
            "link_type": link.link_type,
            "created": True,
        }

    async def remove_link(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        source_path: str,
        target_path: str,
        link_type: str = "reference",
    ) -> dict:
        """Remove a specific link."""
        clean_src = source_path.strip("/")
        clean_tgt = target_path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "writer")

            deleted = await delete_link_query(
                session, org_id, ws.id, clean_src, clean_tgt, link_type
            )

        return {
            "source_path": clean_src,
            "target_path": clean_tgt,
            "link_type": link_type,
            "deleted": deleted,
        }

    async def traverse_graph(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
        path: str,
        depth: int = 1,
    ) -> dict:
        """BFS graph traversal from a starting path."""
        clean_path = path.strip("/")

        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            result = await get_neighbors(
                session, org_id, ws.id, clean_path, depth=depth
            )

        return {
            "start": clean_path,
            "depth": depth,
            "nodes": sorted(result["nodes"]),
            "edges": result["edges"],
            "node_count": len(result["nodes"]),
            "edge_count": len(result["edges"]),
        }

    async def graph_summary(
        self,
        org_id: str,
        user_id: str,
        workspace_slug: str,
    ) -> dict:
        """Get workspace-level graph statistics."""
        _db = self._custom_get_db or get_db
        async with _db() as session:
            ws = await self._resolve_workspace(session, org_id, user_id, workspace_slug)
            await self._check_role(session, ws.id, user_id, "reader")

            return await get_graph_summary(session, org_id, ws.id)

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
