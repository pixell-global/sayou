"""Test move/copy operations (Gap 4)."""

import pytest

from sayou.core.workspace import FileExistsError as WsFileExistsError
from sayou.core.workspace import FileNotFoundError as WsFileNotFoundError


@pytest.mark.asyncio
async def test_move_basic(workspace_service):
    """Move relocates a file: old path gone, new path has content."""
    content = "---\ntitle: Movable\n---\nMove me"
    await workspace_service.write(
        "test-org", "test-user", "default", "old/file.md", content
    )

    result = await workspace_service.move(
        "test-org", "test-user", "default", "old/file.md", "new/file.md"
    )
    assert result["moved"] is True

    # Old path gone
    with pytest.raises(WsFileNotFoundError):
        await workspace_service.read("test-org", "test-user", "default", "old/file.md")

    # New path has content
    read = await workspace_service.read("test-org", "test-user", "default", "new/file.md")
    assert read["content"] == content


@pytest.mark.asyncio
async def test_move_preserves_version_history(workspace_service):
    """Move preserves all version history."""
    await workspace_service.write(
        "test-org", "test-user", "default", "versioned.md", "v1"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "versioned.md", "v2"
    )

    await workspace_service.move(
        "test-org", "test-user", "default", "versioned.md", "moved/versioned.md"
    )

    history = await workspace_service.history(
        "test-org", "test-user", "default", "moved/versioned.md"
    )
    assert history["total"] == 2


@pytest.mark.asyncio
async def test_move_to_existing_path_fails(workspace_service):
    """Move to a path that already exists raises FileExistsError."""
    await workspace_service.write(
        "test-org", "test-user", "default", "a.md", "content a"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "b.md", "content b"
    )

    with pytest.raises(WsFileExistsError):
        await workspace_service.move(
            "test-org", "test-user", "default", "a.md", "b.md"
        )


@pytest.mark.asyncio
async def test_move_nonexistent_file(workspace_service):
    """Move of a non-existent file raises FileNotFoundError."""
    with pytest.raises(WsFileNotFoundError):
        await workspace_service.move(
            "test-org", "test-user", "default", "nope.md", "dest.md"
        )


@pytest.mark.asyncio
async def test_copy_basic(workspace_service):
    """Copy creates a duplicate: both paths have content."""
    content = "---\ntitle: Copyable\n---\nCopy me"
    await workspace_service.write(
        "test-org", "test-user", "default", "original.md", content
    )

    result = await workspace_service.copy(
        "test-org", "test-user", "default", "original.md", "duplicate.md"
    )
    assert result["copied"] is True

    # Both paths have content
    orig = await workspace_service.read("test-org", "test-user", "default", "original.md")
    dup = await workspace_service.read("test-org", "test-user", "default", "duplicate.md")
    assert orig["content"] == content
    assert dup["content"] == content


@pytest.mark.asyncio
async def test_copy_independent_versions(workspace_service):
    """After copy, modifying one doesn't affect the other."""
    await workspace_service.write(
        "test-org", "test-user", "default", "src.md", "original"
    )
    await workspace_service.copy(
        "test-org", "test-user", "default", "src.md", "dst.md"
    )

    # Modify original
    await workspace_service.write(
        "test-org", "test-user", "default", "src.md", "modified"
    )

    # Copy should still have original content
    dst = await workspace_service.read("test-org", "test-user", "default", "dst.md")
    assert dst["content"] == "original"


@pytest.mark.asyncio
async def test_copy_to_existing_path_fails(workspace_service):
    """Copy to an existing path raises FileExistsError."""
    await workspace_service.write(
        "test-org", "test-user", "default", "a.md", "a"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "b.md", "b"
    )

    with pytest.raises(WsFileExistsError):
        await workspace_service.copy(
            "test-org", "test-user", "default", "a.md", "b.md"
        )


@pytest.mark.asyncio
async def test_move_updates_indexes(workspace_service, db_engine):
    """Move regenerates indexes for both old and new parent folders."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sayou.catalog.queries import get_index_cache, get_workspace_by_slug

    await workspace_service.write(
        "test-org", "test-user", "default", "folder_a/file.md", "content"
    )
    await workspace_service.move(
        "test-org", "test-user", "default", "folder_a/file.md", "folder_b/file.md"
    )

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        ws = await get_workspace_by_slug(session, "test-org", "default")
        # Old folder index should show 0 files
        old_cache = await get_index_cache(session, "test-org", ws.id, "folder_a/")
        assert old_cache is not None
        assert old_cache.file_count == 0
        # New folder index should show 1 file
        new_cache = await get_index_cache(session, "test-org", ws.id, "folder_b/")
        assert new_cache is not None
        assert new_cache.file_count == 1


@pytest.mark.asyncio
async def test_mutation_log_records_move_copy(workspace_service):
    """Mutation log records move and copy actions."""
    await workspace_service.write(
        "test-org", "test-user", "default", "log-test.md", "content"
    )
    await workspace_service.copy(
        "test-org", "test-user", "default", "log-test.md", "log-copy.md"
    )
    await workspace_service.move(
        "test-org", "test-user", "default", "log-test.md", "log-moved.md"
    )

    audit = await workspace_service.audit_log("test-org", "test-user", "default")
    actions = [e["action"] for e in audit["entries"]]
    assert "copy" in actions
    assert "move" in actions
