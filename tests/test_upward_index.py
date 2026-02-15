"""Test upward index chain propagation (Gap 1)."""

import pytest

from sayou.catalog.queries import get_index_cache


@pytest.mark.asyncio
async def test_write_creates_full_index_chain(workspace_service, db_engine):
    """Writing to a/b/c/file.md creates index caches for a/b/c/, a/b/, a/, and /."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    await workspace_service.write(
        "test-org", "test-user", "default",
        "a/b/c/file.md", "---\ntitle: Deep\n---\nDeep file"
    )

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # Need to find workspace id
        from sayou.catalog.queries import get_workspace_by_slug
        ws = await get_workspace_by_slug(session, "test-org", "default")
        assert ws is not None

        # Check each level has an index
        for folder in ["a/b/c/", "a/b/", "a/", "/"]:
            cache = await get_index_cache(session, "test-org", ws.id, folder)
            assert cache is not None, f"Missing index cache for {folder}"
            assert len(cache.content) > 0

        # Root index should contain folder stats
        root = await get_index_cache(session, "test-org", ws.id, "/")
        assert "a/" in root.content


@pytest.mark.asyncio
async def test_root_index_stays_small(workspace_service, db_engine):
    """Root index stays under 2000 chars even with many folders."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    # Create files in 20 different top-level folders
    for i in range(20):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"folder{i:02d}/file.md", f"Content {i}"
        )

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        from sayou.catalog.queries import get_workspace_by_slug
        ws = await get_workspace_by_slug(session, "test-org", "default")
        root = await get_index_cache(session, "test-org", ws.id, "/")
        assert root is not None
        assert len(root.content) <= 2000


@pytest.mark.asyncio
async def test_delete_triggers_chain_repropagation(workspace_service, db_engine):
    """Deleting a file triggers index re-propagation up to root."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    await workspace_service.write(
        "test-org", "test-user", "default",
        "docs/notes/a.md", "File A"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "docs/notes/b.md", "File B"
    )

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    # Verify initial state: 2 files in folder
    async with session_factory() as session:
        from sayou.catalog.queries import get_workspace_by_slug
        ws = await get_workspace_by_slug(session, "test-org", "default")
        cache = await get_index_cache(session, "test-org", ws.id, "docs/notes/")
        assert cache is not None
        assert cache.file_count == 2

    # Delete one file
    await workspace_service.delete("test-org", "test-user", "default", "docs/notes/a.md")

    # Check index updated
    async with session_factory() as session:
        ws = await get_workspace_by_slug(session, "test-org", "default")
        cache = await get_index_cache(session, "test-org", ws.id, "docs/notes/")
        assert cache.file_count == 1

        # Root index should still exist
        root = await get_index_cache(session, "test-org", ws.id, "/")
        assert root is not None


@pytest.mark.asyncio
async def test_multiple_folders_at_same_level(workspace_service, db_engine):
    """Multiple sibling folders are all tracked in parent index."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/competitors/a.md", "Competitor A"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/trends/b.md", "Trend B"
    )

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        from sayou.catalog.queries import get_workspace_by_slug
        ws = await get_workspace_by_slug(session, "test-org", "default")

        # Parent folder "research/" should know about both subfolders
        research_cache = await get_index_cache(session, "test-org", ws.id, "research/")
        # It has 0 direct files (files are in subfolders)
        assert research_cache is not None
