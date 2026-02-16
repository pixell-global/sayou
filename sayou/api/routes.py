"""FastAPI REST API routes for sayou.

All endpoints delegate to WorkspaceService — no business logic here.

IMPORTANT: Routes with `{path:path}` must be ordered carefully.
Specific action routes (history, diff, move, copy) are defined BEFORE
the generic file CRUD routes to prevent greedy path matching.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from sayou.api.auth import get_identity
from sayou.api.schemas import (
    DeleteResponse,
    DiffResponse,
    FileCopyRequest,
    FileListResponse,
    FileMoveRequest,
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
    HistoryResponse,
    KVGetResponse,
    KVListResponse,
    KVSetRequest,
    SearchResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from sayou.core.workspace import (
    AccessDeniedError,
    FileExistsError,
    FileNotFoundError,
    WorkspaceService,
)


def create_router(ws: WorkspaceService) -> APIRouter:
    """Create a fully configured router bound to the given WorkspaceService."""
    router = APIRouter(prefix="/api/v1")

    # ── Workspaces ───────────────────────────────────────────────

    @router.get("/workspaces", response_model=list[WorkspaceResponse])
    async def list_workspaces(identity: tuple = Depends(get_identity)):
        org_id, user_id = identity
        try:
            from sayou.catalog.database import get_db
            _db = ws._custom_get_db or get_db
            async with _db() as session:
                from sqlalchemy import select
                from sayou.catalog.models import SayouWorkspace
                result = await session.execute(
                    select(SayouWorkspace).where(SayouWorkspace.org_id == org_id)
                )
                workspaces = list(result.scalars().all())
                return [
                    WorkspaceResponse(
                        id=w.id, slug=w.slug, name=w.name,
                        created_by=w.created_by, created_at=w.created_at,
                    )
                    for w in workspaces
                ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
    async def create_workspace(body: WorkspaceCreate, identity: tuple = Depends(get_identity)):
        org_id, user_id = identity
        try:
            from sayou.catalog.database import get_db
            _db = ws._custom_get_db or get_db
            async with _db() as session:
                from sayou.catalog.queries import create_workspace as cw, add_member
                w = await cw(session, org_id, body.slug, body.name, user_id)
                await add_member(session, w.id, user_id, "admin")
                return WorkspaceResponse(
                    id=w.id, slug=w.slug, name=w.name,
                    created_by=w.created_by, created_at=w.created_at,
                )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── File list (no path param) ────────────────────────────────

    @router.get("/workspaces/{slug}/files", response_model=FileListResponse)
    async def list_files(
        slug: str,
        path: str = Query(default="/"),
        recursive: bool = Query(default=False),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.list_folder(org_id, user_id, slug, path, recursive=recursive)
            return FileListResponse(
                path=result["path"],
                files=result["files"],
                subfolders=result["subfolders"],
                file_count=result["file_count"],
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Search ───────────────────────────────────────────────────

    @router.get("/workspaces/{slug}/search", response_model=SearchResponse)
    async def search_files(
        slug: str,
        query: str | None = Query(default=None),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.search(org_id, user_id, slug, query=query)
            return SearchResponse(**result)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── KV Store (before file routes to avoid path conflicts) ────

    @router.get("/workspaces/{slug}/kv", response_model=KVListResponse)
    async def kv_list(
        slug: str,
        prefix: str | None = Query(default=None),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.kv_list(org_id, user_id, slug, prefix)
            return KVListResponse(**result)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.get("/workspaces/{slug}/kv/{key:path}", response_model=KVGetResponse)
    async def kv_get(
        slug: str, key: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            result = await ws.kv_get(org_id, user_id, slug, key)
            return KVGetResponse(**result)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.put("/workspaces/{slug}/kv/{key:path}")
    async def kv_set(
        slug: str,
        key: str,
        body: KVSetRequest,
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.kv_set(
                org_id, user_id, slug, key, body.value, body.ttl_seconds,
            )
            return result
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.delete("/workspaces/{slug}/kv/{key:path}")
    async def kv_delete(
        slug: str, key: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            result = await ws.kv_delete(org_id, user_id, slug, key)
            return result
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Schema & Auto-Metadata ──────────────────────────────────

    @router.get("/workspaces/{slug}/schema")
    async def get_schema(
        slug: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.get_schema(org_id, user_id, slug)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/schema/refresh")
    async def refresh_schema(
        slug: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.refresh_schema(org_id, user_id, slug)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/generate-metadata/{path:path}")
    async def generate_metadata(
        slug: str, path: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.generate_metadata(org_id, user_id, slug, path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/bulk-metadata")
    async def bulk_generate_metadata(
        slug: str,
        path_pattern: str | None = Query(default=None),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            return await ws.bulk_generate_metadata(
                org_id, user_id, slug, path_pattern=path_pattern,
            )
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Semantic Search ────────────────────────────────────────────

    @router.get("/workspaces/{slug}/semantic-search")
    async def semantic_search(
        slug: str,
        query: str = Query(...),
        top_k: int = Query(default=10),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            return await ws.semantic_search(
                org_id, user_id, slug, query, top_k=top_k,
            )
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/reindex-embeddings")
    async def reindex_embeddings(
        slug: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.reindex_embeddings(org_id, user_id, slug)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Links / Graph ──────────────────────────────────────────────

    @router.get("/workspaces/{slug}/graph")
    async def graph_summary(
        slug: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.graph_summary(org_id, user_id, slug)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/links")
    async def add_link(
        slug: str,
        body: dict,
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            return await ws.add_link(
                org_id, user_id, slug,
                body["source_path"], body["target_path"],
                link_type=body.get("link_type", "reference"),
                context=body.get("context"),
            )
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.delete("/workspaces/{slug}/links")
    async def remove_link(
        slug: str,
        source_path: str = Query(...),
        target_path: str = Query(...),
        link_type: str = Query(default="reference"),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            return await ws.remove_link(
                org_id, user_id, slug,
                source_path, target_path, link_type=link_type,
            )
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.get("/workspaces/{slug}/traverse/{path:path}")
    async def traverse_graph(
        slug: str,
        path: str,
        depth: int = Query(default=1),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            return await ws.traverse_graph(
                org_id, user_id, slug, path, depth=depth,
            )
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.get("/workspaces/{slug}/links/{path:path}")
    async def get_links(
        slug: str, path: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            return await ws.get_links(org_id, user_id, slug, path)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Chunks ────────────────────────────────────────────────────

    @router.get("/workspaces/{slug}/chunks/{path:path}")
    async def get_chunks(
        slug: str, path: str,
        chunk_index: int | None = Query(default=None),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            if chunk_index is not None:
                result = await ws.get_chunk(org_id, user_id, slug, path, chunk_index)
            else:
                result = await ws.get_chunks(org_id, user_id, slug, path)
            return result
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.get("/workspaces/{slug}/search-chunks")
    async def search_chunks(
        slug: str,
        query: str = Query(...),
        path_pattern: str | None = Query(default=None),
        limit: int = Query(default=20),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.search_chunks(
                org_id, user_id, slug, query,
                path_pattern=path_pattern, limit=limit,
            )
            return result
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── File action routes (MUST come before generic {path:path}) ──

    @router.get("/workspaces/{slug}/history/{path:path}", response_model=HistoryResponse)
    async def file_history(
        slug: str,
        path: str,
        limit: int = Query(default=20),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.history(org_id, user_id, slug, path, limit=limit)
            return HistoryResponse(**result)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.get("/workspaces/{slug}/diff/{path:path}", response_model=DiffResponse)
    async def file_diff(
        slug: str,
        path: str,
        version_a: int = Query(...),
        version_b: int = Query(...),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.diff(org_id, user_id, slug, path, version_a, version_b)
            return DiffResponse(**result)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/move/{path:path}")
    async def move_file(
        slug: str,
        path: str,
        body: FileMoveRequest,
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.move(org_id, user_id, slug, path, body.destination)
            return result
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/workspaces/{slug}/copy/{path:path}")
    async def copy_file(
        slug: str,
        path: str,
        body: FileCopyRequest,
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.copy(org_id, user_id, slug, path, body.destination)
            return result
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    # ── Generic file CRUD (catch-all, MUST be last) ──────────────

    @router.get("/workspaces/{slug}/files/{path:path}", response_model=FileReadResponse)
    async def read_file(
        slug: str,
        path: str,
        token_budget: int = Query(default=4000),
        version: int | None = Query(default=None),
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.read(
                org_id, user_id, slug, path,
                token_budget=token_budget, version_number=version,
            )
            return FileReadResponse(**result)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.put("/workspaces/{slug}/files/{path:path}", response_model=FileWriteResponse)
    async def write_file(
        slug: str,
        path: str,
        body: FileWriteRequest,
        identity: tuple = Depends(get_identity),
    ):
        org_id, user_id = identity
        try:
            result = await ws.write(
                org_id, user_id, slug, path, body.content, source=body.source,
                content_type=body.content_type,
            )
            return FileWriteResponse(**result)
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.delete("/workspaces/{slug}/files/{path:path}", response_model=DeleteResponse)
    async def delete_file(
        slug: str, path: str, identity: tuple = Depends(get_identity)
    ):
        org_id, user_id = identity
        try:
            result = await ws.delete(org_id, user_id, slug, path)
            return DeleteResponse(**result)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))

    return router
