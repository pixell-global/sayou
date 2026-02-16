"""Tests for auto-metadata generation with mock provider."""

import tempfile

import pytest

from sayou import Workspace
from sayou.core.auto_metadata import (
    NullMetadataProvider,
    build_metadata_prompt,
    get_metadata_provider,
    merge_auto_metadata,
)
from sayou.core.workspace import WorkspaceService
from sayou.storage.local import LocalStorage


# ── Unit tests: merge logic ──────────────────────────────────────


def test_merge_auto_metadata_adds_auto_fields():
    """Auto fields are added to frontmatter."""
    existing = {"title": "My Doc", "tags": ["a"]}
    auto = {"_auto_summary": "A doc about stuff", "_auto_tags": ["doc", "test"]}
    merged = merge_auto_metadata(existing, auto)
    assert merged["title"] == "My Doc"
    assert merged["_auto_summary"] == "A doc about stuff"
    assert merged["_auto_tags"] == ["doc", "test"]


def test_merge_auto_metadata_never_touches_user_fields():
    """Non-_auto_ fields in auto dict are ignored."""
    existing = {"title": "Original"}
    auto = {"title": "SHOULD NOT CHANGE", "_auto_summary": "Valid"}
    merged = merge_auto_metadata(existing, auto)
    assert merged["title"] == "Original"
    assert merged["_auto_summary"] == "Valid"


def test_merge_auto_metadata_replaces_existing_auto():
    """Existing _auto_ fields are updated."""
    existing = {"_auto_summary": "Old summary", "title": "Doc"}
    auto = {"_auto_summary": "New summary"}
    merged = merge_auto_metadata(existing, auto)
    assert merged["_auto_summary"] == "New summary"
    assert merged["title"] == "Doc"


def test_merge_auto_metadata_empty_auto():
    """Empty auto dict leaves frontmatter unchanged."""
    existing = {"title": "Doc"}
    merged = merge_auto_metadata(existing, {})
    assert merged == existing


def test_build_metadata_prompt_basic():
    """Prompt includes content."""
    prompt = build_metadata_prompt("Hello world content")
    assert "Hello world content" in prompt
    assert "_auto_summary" in prompt
    assert "_auto_tags" in prompt


def test_build_metadata_prompt_with_schema():
    """Prompt includes existing categories for consistency."""
    schema = [
        {"field_name": "_auto_category", "sample_values": ["tutorial", "guide"]},
        {"field_name": "_auto_tags", "sample_values": [["python", "setup"]]},
    ]
    prompt = build_metadata_prompt("Content", existing_schema=schema)
    assert "tutorial" in prompt
    assert "guide" in prompt


def test_build_metadata_prompt_truncates_long_content():
    """Long content is truncated."""
    long_content = "x" * 10000
    prompt = build_metadata_prompt(long_content)
    assert len(prompt) < 10000
    assert "truncated" in prompt


def test_null_provider():
    """NullMetadataProvider returns empty results."""
    provider = NullMetadataProvider()
    assert provider.provider_name == ""


def test_get_metadata_provider_empty():
    """Empty config returns NullProvider."""
    provider = get_metadata_provider()
    assert isinstance(provider, NullMetadataProvider)


# ── Mock metadata provider ───────────────────────────────────────


class MockMetadataProvider:
    """Returns deterministic metadata for testing."""

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, content: str, existing_schema: list[dict] | None = None) -> dict:
        """Generate predictable metadata from content."""
        word_count = len(content.split())
        return {
            "_auto_summary": f"Document with {word_count} words",
            "_auto_tags": ["test", "mock"],
            "_auto_category": "test-doc",
            "_auto_language": "en",
        }


# ── Integration tests ────────────────────────────────────────────


def _make_ws_with_metadata(**kwargs) -> tuple:
    """Create workspace with mock metadata provider."""
    tmpdir = kwargs.pop("_tmpdir", None) or tempfile.mkdtemp()
    mock_provider = MockMetadataProvider()

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
        metadata_provider=mock_provider,
        auto_metadata_enabled=True,
    )

    return engine, service, get_db


@pytest.mark.asyncio
async def test_auto_metadata_on_write():
    """Writing with auto_metadata_enabled adds _auto_ fields."""
    engine, ws, get_db = _make_ws_with_metadata()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        await ws.write("test-org", "test-user", "default", "doc.md", "Hello world test content")

        result = await ws.read("test-org", "test-user", "default", "doc.md")
        fm = result.get("frontmatter", {})
        assert "_auto_summary" in fm
        assert "_auto_tags" in fm
        assert "_auto_category" in fm
        assert "_auto_language" in fm
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_auto_metadata_preserves_user_fields():
    """Auto-metadata doesn't overwrite user frontmatter."""
    engine, ws, get_db = _make_ws_with_metadata()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        content = "---\ntitle: My Title\nstatus: draft\n---\nBody content here"
        await ws.write("test-org", "test-user", "default", "doc.md", content)

        result = await ws.read("test-org", "test-user", "default", "doc.md")
        fm = result.get("frontmatter", {})
        assert fm["title"] == "My Title"
        assert fm["status"] == "draft"
        assert "_auto_summary" in fm
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_generate_metadata_single_file():
    """Generate metadata for a specific file on demand."""
    engine, ws, get_db = _make_ws_with_metadata()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        # Write without auto-metadata first (create a service without auto)
        ws_no_auto = WorkspaceService(
            storage=ws.storage, _get_db=get_db,
            metadata_provider=MockMetadataProvider(),
            auto_metadata_enabled=False,
        )
        await ws_no_auto.write("test-org", "test-user", "default", "doc.md", "Some content here")

        # Now generate metadata explicitly
        result = await ws.generate_metadata("test-org", "test-user", "default", "doc.md")
        assert result["generated"].get("_auto_summary")
        assert result["generated"].get("_auto_tags")
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_bulk_generate_metadata():
    """Bulk generate metadata for all files."""
    engine, ws, get_db = _make_ws_with_metadata()
    from sayou.catalog.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        # Write files without auto-metadata
        ws_no_auto = WorkspaceService(
            storage=ws.storage, _get_db=get_db,
            metadata_provider=MockMetadataProvider(),
            auto_metadata_enabled=False,
        )
        await ws_no_auto.write("test-org", "test-user", "default", "a.md", "File A content")
        await ws_no_auto.write("test-org", "test-user", "default", "b.md", "File B content")

        result = await ws.bulk_generate_metadata("test-org", "test-user", "default")
        assert result["generated"] == 2
        assert result["errors"] == 0
    finally:
        await ws.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_no_provider_returns_error():
    """Without provider, generate_metadata returns error."""
    async with Workspace(
        database_url="sqlite+aiosqlite://",
        storage_path=tempfile.mkdtemp(),
        org_id="test-org",
        user_id="test-user",
    ) as ws:
        await ws.write("doc.md", "Content")
        result = await ws.generate_metadata("doc.md")
        assert "error" in result or result.get("generated") == {}
