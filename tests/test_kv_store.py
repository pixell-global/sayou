"""Test KV store (Gap 2)."""

import asyncio

import pytest

from sayou.core.workspace import AccessDeniedError


@pytest.mark.asyncio
async def test_kv_set_get_roundtrip(workspace_service):
    """Set and get a KV entry."""
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "config.theme", "dark"
    )
    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "config.theme"
    )
    assert result["found"] is True
    assert result["key"] == "config.theme"
    assert result["value"] == "dark"


@pytest.mark.asyncio
async def test_kv_set_complex_value(workspace_service):
    """KV store handles complex JSON values."""
    value = {"nested": {"key": "value"}, "list": [1, 2, 3]}
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "complex", value
    )
    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "complex"
    )
    assert result["found"] is True
    assert result["value"] == value


@pytest.mark.asyncio
async def test_kv_upsert(workspace_service):
    """Setting an existing key overwrites the value."""
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "counter", 1
    )
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "counter", 2
    )
    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "counter"
    )
    assert result["value"] == 2


@pytest.mark.asyncio
async def test_kv_delete(workspace_service):
    """Delete removes a KV entry."""
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "temp", "data"
    )
    result = await workspace_service.kv_delete(
        "test-org", "test-user", "default", "temp"
    )
    assert result["deleted"] is True

    get_result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "temp"
    )
    assert get_result["found"] is False


@pytest.mark.asyncio
async def test_kv_delete_nonexistent(workspace_service):
    """Deleting a non-existent key returns deleted=False."""
    result = await workspace_service.kv_delete(
        "test-org", "test-user", "default", "nope"
    )
    assert result["deleted"] is False


@pytest.mark.asyncio
async def test_kv_get_nonexistent(workspace_service):
    """Getting a non-existent key returns found=False."""
    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "nope"
    )
    assert result["found"] is False


@pytest.mark.asyncio
async def test_kv_list(workspace_service):
    """List returns all KV entries."""
    await workspace_service.kv_set("test-org", "test-user", "default", "a.key", "val1")
    await workspace_service.kv_set("test-org", "test-user", "default", "b.key", "val2")
    await workspace_service.kv_set("test-org", "test-user", "default", "a.other", "val3")

    result = await workspace_service.kv_list("test-org", "test-user", "default")
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_kv_list_with_prefix(workspace_service):
    """List filters by key prefix."""
    await workspace_service.kv_set("test-org", "test-user", "default", "config.a", "1")
    await workspace_service.kv_set("test-org", "test-user", "default", "config.b", "2")
    await workspace_service.kv_set("test-org", "test-user", "default", "other.c", "3")

    result = await workspace_service.kv_list(
        "test-org", "test-user", "default", prefix="config."
    )
    assert result["total"] == 2
    keys = {item["key"] for item in result["items"]}
    assert keys == {"config.a", "config.b"}


@pytest.mark.asyncio
async def test_kv_ttl_expiry(workspace_service):
    """KV entry with TTL expires after the TTL period."""
    await workspace_service.kv_set(
        "test-org", "test-user", "default", "ephemeral", "temp", ttl_seconds=1
    )

    # Should exist immediately
    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "ephemeral"
    )
    assert result["found"] is True
    assert result["ttl_seconds"] == 1

    # Wait for expiry
    await asyncio.sleep(1.5)

    result = await workspace_service.kv_get(
        "test-org", "test-user", "default", "ephemeral"
    )
    assert result["found"] is False


@pytest.mark.asyncio
async def test_kv_org_isolation(workspace_service, db_engine):
    """KV entries are isolated between orgs."""
    from contextlib import asynccontextmanager
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sayou.core.workspace import WorkspaceService

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

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

    svc2 = WorkspaceService(storage=workspace_service.storage, _get_db=test_get_db)

    await workspace_service.kv_set("test-org", "test-user", "default", "shared-key", "org1-val")
    await svc2.kv_set("other-org", "test-user", "default", "shared-key", "org2-val")

    r1 = await workspace_service.kv_get("test-org", "test-user", "default", "shared-key")
    r2 = await svc2.kv_get("other-org", "test-user", "default", "shared-key")
    assert r1["value"] == "org1-val"
    assert r2["value"] == "org2-val"
