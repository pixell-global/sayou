"""Public Python API for sayou workspaces."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sayou.catalog.models import Base
from sayou.core.workspace import WorkspaceService
from sayou.storage.local import LocalStorage
from sayou.storage.s3 import StorageService


class Workspace:
    """High-level Python interface for sayou workspaces.

    Binds identity (org, user, workspace) once at construction time.
    All methods delegate to WorkspaceService with pre-bound values.

    Usage::

        async with Workspace() as ws:
            await ws.write("hello.md", "# Hello")
            result = await ws.read("hello.md")
    """

    def __init__(
        self,
        slug: str = "default",
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        database_url: str | None = None,
        s3_bucket: str | None = None,
        s3_region: str | None = None,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
        s3_endpoint_url: str | None = None,
        storage_path: str | None = None,
        source: str | None = None,
    ):
        self._slug = slug
        self._org_id = org_id or os.environ.get("SAYOU_ORG_ID") or "local"
        self._user_id = user_id or os.environ.get("SAYOU_USER_ID") or "default-user"
        from sayou.config import _SAYOU_HOME
        self._database_url = (
            database_url
            or os.environ.get("SAYOU_DATABASE_URL")
            or f"sqlite+aiosqlite:///{_SAYOU_HOME / 'sayou.db'}"
        )
        self._s3_bucket = s3_bucket
        self._s3_region = s3_region
        self._s3_access_key_id = s3_access_key_id
        self._s3_secret_access_key = s3_secret_access_key
        self._s3_endpoint_url = s3_endpoint_url
        self._storage_path = storage_path
        self._source = source

        # Initialized in open()
        self._engine = None
        self._session_factory = None
        self._storage = None
        self._service: WorkspaceService | None = None
        self._opened = False

    async def open(self) -> Workspace:
        """Initialize database engine, storage backend, and workspace service."""
        if self._opened:
            return self

        # Create engine
        is_sqlite = self._database_url.startswith("sqlite")
        engine_kwargs = {}
        if is_sqlite:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = StaticPool
            # Auto-create directory for SQLite databases
            from sayou.catalog.database import _ensure_sqlite_dir
            _ensure_sqlite_dir(self._database_url)

        self._engine = create_async_engine(self._database_url, **engine_kwargs)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # Auto-create tables for SQLite
        if is_sqlite:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Create FTS5 virtual tables and triggers
            from sayou.catalog.fts import create_fts_tables
            await create_fts_tables(self._engine, self._database_url)

        # Select storage backend
        has_s3 = bool(self._s3_access_key_id and self._s3_secret_access_key)
        if has_s3:
            self._storage = StorageService(
                bucket=self._s3_bucket,
                region=self._s3_region,
                endpoint_url=self._s3_endpoint_url,
                access_key_id=self._s3_access_key_id,
                secret_access_key=self._s3_secret_access_key,
            )
        else:
            self._storage = LocalStorage(
                base_path=self._storage_path or "~/.sayou/storage"
            )

        self._service = WorkspaceService(
            storage=self._storage, _get_db=self._get_db
        )
        self._opened = True
        return self

    async def close(self) -> None:
        """Dispose engine and close storage."""
        if self._service:
            await self._service.close()
            self._service = None
        if self._engine:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None
        self._storage = None
        self._opened = False

    @asynccontextmanager
    async def _get_db(self):
        """Instance-scoped session factory as async context manager."""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def _ensure_open(self):
        """Lazy init: call open() on first use if not already opened."""
        if not self._opened:
            await self.open()

    async def __aenter__(self) -> Workspace:
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ── Public methods ──────────────────────────────────────────────

    async def write(
        self, path: str, content: str | bytes, *,
        source: str | None = None, content_type: str | None = None,
    ) -> dict:
        """Write a file to the workspace. Pass bytes for binary content."""
        await self._ensure_open()
        return await self._service.write(
            self._org_id, self._user_id, self._slug, path, content,
            source=source or self._source,
            content_type=content_type,
        )

    async def read(
        self, path: str, *, token_budget: int = 4000, version: int | None = None
    ) -> dict:
        """Read a file from the workspace."""
        await self._ensure_open()
        return await self._service.read(
            self._org_id, self._user_id, self._slug, path,
            token_budget=token_budget, version_number=version,
        )

    async def list(self, path: str = "/", *, recursive: bool = False) -> dict:
        """List files and subfolders in a folder."""
        await self._ensure_open()
        return await self._service.list_folder(
            self._org_id, self._user_id, self._slug, path, recursive=recursive,
        )

    async def glob(self, pattern: str) -> dict:
        """Find files matching a glob pattern."""
        await self._ensure_open()
        return await self._service.glob_files(
            self._org_id, self._user_id, self._slug, pattern,
        )

    async def grep(
        self, query: str, *, path_pattern: str | None = None, context_lines: int = 2
    ) -> dict:
        """Search file content for a query string."""
        await self._ensure_open()
        return await self._service.grep_files(
            self._org_id, self._user_id, self._slug, query,
            path_pattern=path_pattern, context_lines=context_lines,
        )

    async def search(
        self, *, query: str | None = None, filters: dict | None = None
    ) -> dict:
        """Search files by frontmatter filters and/or full-text query."""
        await self._ensure_open()
        return await self._service.search(
            self._org_id, self._user_id, self._slug,
            query=query, filters=filters,
        )

    async def delete(self, path: str, *, source: str | None = None) -> dict:
        """Soft-delete a file."""
        await self._ensure_open()
        return await self._service.delete(
            self._org_id, self._user_id, self._slug, path,
            source=source or self._source,
        )

    async def history(self, path: str, *, limit: int = 20) -> dict:
        """Get version history for a file."""
        await self._ensure_open()
        return await self._service.history(
            self._org_id, self._user_id, self._slug, path, limit=limit,
        )

    async def audit(
        self,
        *,
        path: str | None = None,
        action: str | None = None,
        agent_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> dict:
        """Query the mutation audit log for the workspace."""
        await self._ensure_open()
        return await self._service.audit_log(
            self._org_id, self._user_id, self._slug,
            path=path, action=action, agent_id=agent_id,
            since=since, until=until, limit=limit,
        )

    async def move(
        self, source_path: str, dest_path: str, *, source: str | None = None
    ) -> dict:
        """Move a file to a new path."""
        await self._ensure_open()
        return await self._service.move(
            self._org_id, self._user_id, self._slug, source_path, dest_path,
            source_agent=source or self._source,
        )

    async def copy(
        self, source_path: str, dest_path: str, *, source: str | None = None
    ) -> dict:
        """Copy a file to a new path."""
        await self._ensure_open()
        return await self._service.copy(
            self._org_id, self._user_id, self._slug, source_path, dest_path,
            source_agent=source or self._source,
        )

    async def diff(self, path: str, version_a: int, version_b: int) -> dict:
        """Compare two versions of a file."""
        await self._ensure_open()
        return await self._service.diff(
            self._org_id, self._user_id, self._slug, path, version_a, version_b,
        )

    async def read_section(
        self, path: str, *, line_start: int, line_end: int
    ) -> dict:
        """Read a specific line range from a file."""
        await self._ensure_open()
        return await self._service.read_section(
            self._org_id, self._user_id, self._slug, path, line_start, line_end,
        )

    # ── Context ────────────────────────────────────────────────────

    async def get_context(self) -> dict:
        """Get workspace context for session start: preferences, recent files, activity."""
        await self._ensure_open()
        return await self._service.get_context(
            self._org_id, self._user_id, self._slug,
        )

    # ── Schema & Auto-Metadata ────────────────────────────────────

    async def schema(self) -> dict:
        """Discover frontmatter schema across all files."""
        await self._ensure_open()
        return await self._service.get_schema(
            self._org_id, self._user_id, self._slug,
        )

    async def refresh_schema(self) -> dict:
        """Refresh the cached schema."""
        await self._ensure_open()
        return await self._service.refresh_schema(
            self._org_id, self._user_id, self._slug,
        )

    async def generate_metadata(self, path: str) -> dict:
        """Generate _auto_ metadata for a single file via LLM."""
        await self._ensure_open()
        return await self._service.generate_metadata(
            self._org_id, self._user_id, self._slug, path,
        )

    async def bulk_generate_metadata(
        self, *, path_pattern: str | None = None
    ) -> dict:
        """Bulk generate _auto_ metadata for all files or matching pattern."""
        await self._ensure_open()
        return await self._service.bulk_generate_metadata(
            self._org_id, self._user_id, self._slug,
            path_pattern=path_pattern,
        )

    # ── Semantic Search ────────────────────────────────────────────

    async def semantic_search(self, query: str, *, top_k: int = 10) -> dict:
        """Search files by meaning using vector embeddings."""
        await self._ensure_open()
        return await self._service.semantic_search(
            self._org_id, self._user_id, self._slug, query, top_k=top_k,
        )

    async def reindex_embeddings(self) -> dict:
        """Recompute embeddings for all files."""
        await self._ensure_open()
        return await self._service.reindex_embeddings(
            self._org_id, self._user_id, self._slug,
        )

    # ── Links / Knowledge Graph ────────────────────────────────────

    async def links(self, path: str) -> dict:
        """Get outgoing and incoming links for a file."""
        await self._ensure_open()
        return await self._service.get_links(
            self._org_id, self._user_id, self._slug, path,
        )

    async def add_link(
        self, source_path: str, target_path: str, *,
        link_type: str = "reference", context: str | None = None,
    ) -> dict:
        """Manually add a link between two files."""
        await self._ensure_open()
        return await self._service.add_link(
            self._org_id, self._user_id, self._slug,
            source_path, target_path, link_type=link_type, context=context,
        )

    async def remove_link(
        self, source_path: str, target_path: str, *,
        link_type: str = "reference",
    ) -> dict:
        """Remove a specific link."""
        await self._ensure_open()
        return await self._service.remove_link(
            self._org_id, self._user_id, self._slug,
            source_path, target_path, link_type=link_type,
        )

    async def traverse(self, path: str, *, depth: int = 1) -> dict:
        """BFS graph traversal from a starting path."""
        await self._ensure_open()
        return await self._service.traverse_graph(
            self._org_id, self._user_id, self._slug, path, depth=depth,
        )

    async def graph(self) -> dict:
        """Get workspace-level graph statistics."""
        await self._ensure_open()
        return await self._service.graph_summary(
            self._org_id, self._user_id, self._slug,
        )

    # ── Chunks ──────────────────────────────────────────────────────

    async def chunks(self, path: str) -> dict:
        """Get chunk outline for a file."""
        await self._ensure_open()
        return await self._service.get_chunks(
            self._org_id, self._user_id, self._slug, path,
        )

    async def chunk(self, path: str, chunk_index: int) -> dict:
        """Read a specific chunk by index."""
        await self._ensure_open()
        return await self._service.get_chunk(
            self._org_id, self._user_id, self._slug, path, chunk_index,
        )

    async def search_chunks(
        self, query: str, *, path_pattern: str | None = None, limit: int = 20
    ) -> dict:
        """Search chunks by content."""
        await self._ensure_open()
        return await self._service.search_chunks(
            self._org_id, self._user_id, self._slug, query,
            path_pattern=path_pattern, limit=limit,
        )

    # ── KV Store ──────────────────────────────────────────────────

    async def kv_get(self, key: str) -> dict:
        """Get a value from the KV store."""
        await self._ensure_open()
        return await self._service.kv_get(
            self._org_id, self._user_id, self._slug, key,
        )

    async def kv_set(self, key: str, value, *, ttl_seconds: int | None = None) -> dict:
        """Set a value in the KV store."""
        await self._ensure_open()
        return await self._service.kv_set(
            self._org_id, self._user_id, self._slug, key, value, ttl_seconds,
        )

    async def kv_delete(self, key: str) -> dict:
        """Delete a key from the KV store."""
        await self._ensure_open()
        return await self._service.kv_delete(
            self._org_id, self._user_id, self._slug, key,
        )

    async def kv_list(self, *, prefix: str | None = None) -> dict:
        """List keys in the KV store."""
        await self._ensure_open()
        return await self._service.kv_list(
            self._org_id, self._user_id, self._slug, prefix,
        )
