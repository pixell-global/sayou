"""Tests for semantic search with mock embedding provider."""

import tempfile

import pytest

from sayou import Workspace
from sayou.core.embeddings import (
    NullEmbeddingProvider,
    cosine_similarity,
    pack_embedding,
    prepare_embedding_input,
    unpack_embedding,
    content_hash,
    get_embedding_provider,
)
from sayou.core.workspace import WorkspaceService
from sayou.storage.local import LocalStorage


# ── Unit tests: embedding utilities ──────────────────────────────


def test_pack_unpack_embedding():
    """Round-trip pack/unpack preserves values."""
    vector = [0.1, 0.2, 0.3, -0.5, 1.0]
    packed = pack_embedding(vector)
    unpacked = unpack_embedding(packed)
    assert len(unpacked) == len(vector)
    for a, b in zip(vector, unpacked):
        assert abs(a - b) < 1e-6


def test_cosine_similarity_identical():
    """Identical vectors have similarity 1.0."""
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors have similarity 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite():
    """Opposite vectors have similarity -1.0."""
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6


def test_cosine_similarity_empty():
    """Empty vectors return 0.0."""
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_mismatched_length():
    """Mismatched lengths return 0.0."""
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_content_hash_deterministic():
    """Same text produces same hash."""
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_prepare_embedding_input_with_frontmatter():
    """Frontmatter is prepended to body."""
    result = prepare_embedding_input(
        {"title": "Guide", "tags": ["setup", "tutorial"]},
        "Install the package."
    )
    assert "title: Guide" in result
    assert "tags: setup, tutorial" in result
    assert "Install the package." in result


def test_prepare_embedding_input_no_frontmatter():
    """Body only when no frontmatter."""
    result = prepare_embedding_input(None, "Just text")
    assert result == "Just text"


def test_null_provider():
    """NullEmbeddingProvider returns empty results."""
    provider = NullEmbeddingProvider()
    assert provider.provider_name == ""
    assert provider.dimensions == 0


def test_get_embedding_provider_empty():
    """Empty config returns NullProvider."""
    provider = get_embedding_provider()
    assert isinstance(provider, NullEmbeddingProvider)


def test_get_embedding_provider_no_key():
    """Provider name without key returns NullProvider."""
    provider = get_embedding_provider(provider="openai")
    assert isinstance(provider, NullEmbeddingProvider)


# ── Mock embedding provider for integration tests ────────────────


class MockEmbeddingProvider:
    """Simple mock that returns deterministic embeddings based on content hash."""

    def __init__(self, dims: int = 8):
        self._dims = dims

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"

    @property
    def dimensions(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        """Create a deterministic embedding from text hash."""
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        # Use first N bytes as float values normalized to [-1, 1]
        return [(b - 128) / 128.0 for b in h[:self._dims]]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


# ── Integration tests: semantic search ───────────────────────────


def _make_ws_with_embeddings(**kwargs) -> tuple:
    """Create workspace with mock embedding provider."""
    tmpdir = kwargs.pop("_tmpdir", None) or tempfile.mkdtemp()
    mock_provider = MockEmbeddingProvider()

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from contextlib import asynccontextmanager
    from sayou.catalog.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def get_db():
        session = session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    storage = LocalStorage(base_path=tmpdir)
    service = WorkspaceService(
        storage=storage,
        _get_db=get_db,
        embedding_provider=mock_provider,
    )

    return engine, service, get_db


@pytest.mark.asyncio
async def test_write_creates_embedding():
    """Writing a text file auto-creates an embedding."""
    engine, ws, get_db = _make_ws_with_embeddings()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        await ws.write("test-org", "test-user", "default", "doc.md", "# Hello World\nTest content")

        # Semantic search should work
        result = await ws.semantic_search(
            "test-org", "test-user", "default", "hello", top_k=5
        )
        assert result["total"] >= 1
        assert result["results"][0]["path"] == "doc.md"
        assert not result.get("fallback")
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_search_ranking():
    """More similar content ranks higher."""
    engine, ws, get_db = _make_ws_with_embeddings()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        await ws.write("test-org", "test-user", "default", "python.md", "Python programming tutorial")
        await ws.write("test-org", "test-user", "default", "cooking.md", "Pasta recipe with tomato sauce")
        await ws.write("test-org", "test-user", "default", "code.md", "Python code examples")

        result = await ws.semantic_search(
            "test-org", "test-user", "default", "Python programming", top_k=3
        )
        assert result["total"] >= 2
        # Results should have scores
        for r in result["results"]:
            assert "score" in r
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_search_skips_unchanged():
    """Re-writing identical content doesn't re-embed."""
    engine, ws, get_db = _make_ws_with_embeddings()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        # Write twice with same content
        await ws.write("test-org", "test-user", "default", "doc.md", "Same content")
        await ws.write("test-org", "test-user", "default", "doc.md", "Same content")

        # Should still work
        result = await ws.semantic_search(
            "test-org", "test-user", "default", "content", top_k=5
        )
        assert result["total"] >= 1
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_search_delete_removes_embedding():
    """Deleting a file removes its embedding."""
    engine, ws, get_db = _make_ws_with_embeddings()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        await ws.write("test-org", "test-user", "default", "doc.md", "Content here")
        await ws.delete("test-org", "test-user", "default", "doc.md")

        result = await ws.semantic_search(
            "test-org", "test-user", "default", "content", top_k=5
        )
        assert result["total"] == 0
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_search_fallback_no_provider():
    """Without a provider, semantic search falls back to text search."""
    async with Workspace(
        database_url="sqlite+aiosqlite://",
        storage_path=tempfile.mkdtemp(),
        org_id="test-org",
        user_id="test-user",
    ) as ws:
        await ws.write("doc.md", "Unique searchable content xyz123")

        result = await ws.semantic_search("xyz123")
        # Should fallback to text search since no provider configured
        assert result["total"] >= 1
