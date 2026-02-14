"""S6: Workspace isolation - reader can't write, non-member can't read, admin can do all."""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sayou.catalog.queries import add_member, create_workspace
from sayou.core.workspace import AccessDeniedError, WorkspaceService


@pytest_asyncio.fixture
async def ws_with_engineering(db_engine, storage):
    """Set up an engineering workspace with admin + reader members."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def test_get_db():
        session = session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # Create engineering workspace with members
    async with test_get_db() as session:
        ws = await create_workspace(session, "test-org", "engineering", "Engineering", "admin-user")
        await add_member(session, ws.id, "admin-user", "admin")
        await add_member(session, ws.id, "reader-user", "reader")

    svc = WorkspaceService(storage=storage)
    with patch("sayou.core.workspace.get_db", test_get_db):
        yield svc


@pytest.mark.asyncio
async def test_admin_can_write_read_delete(ws_with_engineering):
    svc = ws_with_engineering

    # Admin can write
    result = await svc.write(
        "test-org", "admin-user", "engineering", "design.md",
        "---\nstatus: draft\n---\nDesign doc",
    )
    assert result["version_number"] == 1

    # Admin can read
    read_result = await svc.read("test-org", "admin-user", "engineering", "design.md")
    assert "Design doc" in read_result["content"]

    # Admin can delete
    del_result = await svc.delete("test-org", "admin-user", "engineering", "design.md")
    assert del_result["deleted"] is True


@pytest.mark.asyncio
async def test_reader_can_read_but_not_write(ws_with_engineering):
    svc = ws_with_engineering

    # Admin writes a file first
    await svc.write(
        "test-org", "admin-user", "engineering", "readme.md",
        "---\nstatus: published\n---\nReadme content",
    )

    # Reader can read
    read_result = await svc.read("test-org", "reader-user", "engineering", "readme.md")
    assert "Readme content" in read_result["content"]

    # Reader cannot write
    with pytest.raises(AccessDeniedError):
        await svc.write(
            "test-org", "reader-user", "engineering", "unauthorized.md",
            "Should fail",
        )


@pytest.mark.asyncio
async def test_non_member_cannot_read(ws_with_engineering):
    svc = ws_with_engineering

    # Admin writes a file
    await svc.write(
        "test-org", "admin-user", "engineering", "secret.md", "Secret content"
    )

    # Non-member cannot read
    with pytest.raises(AccessDeniedError):
        await svc.read("test-org", "outsider-user", "engineering", "secret.md")


@pytest.mark.asyncio
async def test_non_member_cannot_list(ws_with_engineering):
    svc = ws_with_engineering

    with pytest.raises(AccessDeniedError):
        await svc.list_folder("test-org", "outsider-user", "engineering")
