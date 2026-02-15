"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Workspace ────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str
    created_by: str
    created_at: datetime | None = None


# ── File ─────────────────────────────────────────────────────────

class FileWriteRequest(BaseModel):
    content: str
    source: str | None = None
    content_type: str = "text/markdown"


class FileWriteResponse(BaseModel):
    path: str
    version_number: int
    version_id: str
    size_bytes: int
    content_hash: str
    content_type: str = "text/markdown"


class FileReadResponse(BaseModel):
    path: str
    content: str
    content_type: str = "text/markdown"
    encoding: str | None = None
    version_number: int
    frontmatter: dict = {}
    size_bytes: int
    truncated: bool = False
    sections: list[dict] | None = None
    total_lines: int | None = None


class FileListItem(BaseModel):
    path: str
    filename: str
    version_count: int
    frontmatter: dict = {}


class FileListResponse(BaseModel):
    path: str
    files: list[FileListItem]
    subfolders: list[str]
    file_count: int


class FileMoveRequest(BaseModel):
    destination: str


class FileCopyRequest(BaseModel):
    destination: str


class VersionResponse(BaseModel):
    version_number: int
    version_id: str
    size_bytes: int
    content_hash: str
    created_by: str
    created_at: str | None = None


class HistoryResponse(BaseModel):
    path: str
    versions: list[VersionResponse]
    total: int


class DiffResponse(BaseModel):
    path: str
    version_a: int
    version_b: int
    diff: str
    has_changes: bool


# ── Search ───────────────────────────────────────────────────────

class SearchResult(BaseModel):
    path: str
    filename: str
    frontmatter: dict = {}


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int


# ── KV Store ─────────────────────────────────────────────────────

class KVSetRequest(BaseModel):
    value: object
    ttl_seconds: int | None = None


class KVGetResponse(BaseModel):
    key: str
    value: object | None = None
    found: bool
    ttl_seconds: int | None = None
    expires_at: str | None = None


class KVListItem(BaseModel):
    key: str
    value: object
    ttl_seconds: int | None = None
    expires_at: str | None = None


class KVListResponse(BaseModel):
    items: list[KVListItem]
    total: int


# ── Generic ──────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str


class DeleteResponse(BaseModel):
    path: str
    deleted: bool
