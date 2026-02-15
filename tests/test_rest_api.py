"""Test REST API (Gap 6).

All operations in a single test to avoid SQLite in-memory isolation issues.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _auth_headers(org_id="test-org", user_id="test-user"):
    return {
        "Authorization": f"Bearer {user_id}",
        "X-Org-Id": org_id,
    }


async def _create_api_client():
    """Create an httpx.AsyncClient pointing at a test REST API app."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from fastapi import FastAPI
    from sayou.api.routes import create_router
    from sayou.catalog.models import Base
    from sayou.core.workspace import WorkspaceService
    from sayou.storage.s3 import StorageService

    class InMemStorage(StorageService):
        def __init__(self):
            self._store: dict[str, bytes] = {}
            self._client = None
            self._client_cm = None

        async def upload_version(self, content, org_id, workspace_id, version_id, content_type="text/markdown"):
            s3_key = self.generate_key(org_id, workspace_id, version_id)
            content_hash = self.calculate_checksum(content)
            self._store[s3_key] = content
            return s3_key, "test-bucket", len(content), content_hash

        async def download_version(self, s3_key, bucket=None):
            return self._store[s3_key]

        async def ensure_bucket(self):
            pass

        async def close(self):
            pass

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage = InMemStorage()
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
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

    ws = WorkspaceService(storage=storage, _get_db=test_get_db)
    app = FastAPI()
    router = create_router(ws)
    app.include_router(router)

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), engine


@pytest.mark.asyncio
async def test_rest_api_full_cycle():
    """Comprehensive REST API test covering all endpoints."""
    client, engine = await _create_api_client()
    headers = _auth_headers()

    try:
        # ── Auth required ────────────────────────────────────────────
        resp = await client.get("/api/v1/workspaces/default/files")
        assert resp.status_code == 401

        # ── Create workspace ─────────────────────────────────────────
        resp = await client.post(
            "/api/v1/workspaces",
            json={"slug": "test-ws", "name": "Test Workspace"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "test-ws"

        # ── Write files ──────────────────────────────────────────────
        resp = await client.put(
            "/api/v1/workspaces/default/files/docs/hello.md",
            json={"content": "---\ntitle: Hello\n---\n# Hello World\n"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "docs/hello.md"
        assert data["version_number"] == 1

        resp = await client.put(
            "/api/v1/workspaces/default/files/docs/notes.md",
            json={"content": "---\ntitle: Notes\n---\n# Notes\n"},
            headers=headers,
        )
        assert resp.status_code == 200

        # ── Read file ────────────────────────────────────────────────
        resp = await client.get(
            "/api/v1/workspaces/default/files/docs/hello.md",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "---\ntitle: Hello\n---\n# Hello World\n"
        assert data["frontmatter"]["title"] == "Hello"

        # ── List files ───────────────────────────────────────────────
        resp = await client.get(
            "/api/v1/workspaces/default/files",
            params={"path": "docs"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_count"] == 2

        # ── Write v2 for diff test ───────────────────────────────────
        resp = await client.put(
            "/api/v1/workspaces/default/files/docs/hello.md",
            json={"content": "---\ntitle: Hello v2\n---\n# Hello World Updated\n"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["version_number"] == 2

        # ── File history ─────────────────────────────────────────────
        resp = await client.get(
            "/api/v1/workspaces/default/history/docs/hello.md",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        # ── File diff ────────────────────────────────────────────────
        resp = await client.get(
            "/api/v1/workspaces/default/diff/docs/hello.md",
            params={"version_a": 1, "version_b": 2},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["has_changes"] is True

        # ── Move file ───────────────────────────────────────────────
        resp = await client.put(
            "/api/v1/workspaces/default/files/old.md",
            json={"content": "movable"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/v1/workspaces/default/move/old.md",
            json={"destination": "moved.md"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["moved"] is True

        # Old path 404
        resp = await client.get(
            "/api/v1/workspaces/default/files/old.md",
            headers=headers,
        )
        assert resp.status_code == 404

        # ── Copy file ───────────────────────────────────────────────
        resp = await client.put(
            "/api/v1/workspaces/default/files/original.md",
            json={"content": "copyable"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/v1/workspaces/default/copy/original.md",
            json={"destination": "copy.md"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["copied"] is True

        for path in ["original.md", "copy.md"]:
            resp = await client.get(
                f"/api/v1/workspaces/default/files/{path}",
                headers=headers,
            )
            assert resp.status_code == 200

        # ── Delete file ──────────────────────────────────────────────
        resp = await client.put(
            "/api/v1/workspaces/default/files/temp.md",
            json={"content": "temporary"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.delete(
            "/api/v1/workspaces/default/files/temp.md",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp = await client.get(
            "/api/v1/workspaces/default/files/temp.md",
            headers=headers,
        )
        assert resp.status_code == 404

        # ── Search ───────────────────────────────────────────────────
        resp = await client.get(
            "/api/v1/workspaces/default/search",
            params={"query": "Hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # ── KV Store CRUD ────────────────────────────────────────────
        # Set
        resp = await client.put(
            "/api/v1/workspaces/default/kv/config.theme",
            json={"value": "dark"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Get
        resp = await client.get(
            "/api/v1/workspaces/default/kv/config.theme",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["found"] is True
        assert resp.json()["value"] == "dark"

        # List
        resp = await client.get(
            "/api/v1/workspaces/default/kv",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # Delete KV
        resp = await client.delete(
            "/api/v1/workspaces/default/kv/config.theme",
            headers=headers,
        )
        assert resp.status_code == 200

        # Verify deleted
        resp = await client.get(
            "/api/v1/workspaces/default/kv/config.theme",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["found"] is False

    finally:
        await client.aclose()
        async with engine.begin() as conn:
            await conn.run_sync(
                __import__("sayou.catalog.models", fromlist=["Base"]).Base.metadata.drop_all
            )
        await engine.dispose()
