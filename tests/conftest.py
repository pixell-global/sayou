import os
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set env vars BEFORE any sayou imports
os.environ["SAYOU_DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["SAYOU_S3_BUCKET_NAME"] = "test-bucket"
os.environ["SAYOU_S3_REGION"] = "us-east-1"
os.environ["SAYOU_S3_ACCESS_KEY_ID"] = "testing"
os.environ["SAYOU_S3_SECRET_ACCESS_KEY"] = "testing"
os.environ["SAYOU_ORG_ID"] = "test-org"
os.environ["SAYOU_USER_ID"] = "test-user"
os.environ["SAYOU_WORKSPACE_SLUG"] = "default"

# Clear settings cache so it picks up test env vars
from sayou.config import get_settings  # noqa: E402

get_settings.cache_clear()

from sayou.catalog.models import Base  # noqa: E402
from sayou.core.workspace import WorkspaceService  # noqa: E402
from sayou.storage.s3 import StorageService  # noqa: E402


class InMemoryStorage(StorageService):
    """In-memory storage for tests. No S3 calls."""

    def __init__(self):
        self._store: dict[str, bytes] = {}
        self._client = None
        self._client_cm = None

    async def upload_version(
        self, content: bytes, org_id: str, workspace_id: str, version_id: str,
        content_type: str = "text/markdown",
    ) -> tuple[str, str, int, str]:
        s3_key = self.generate_key(org_id, workspace_id, version_id)
        content_hash = self.calculate_checksum(content)
        self._store[s3_key] = content
        return s3_key, "test-bucket", len(content), content_hash

    async def download_version(self, s3_key: str, bucket: str | None = None) -> bytes:
        return self._store[s3_key]

    async def ensure_bucket(self) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest_asyncio.fixture
async def workspace_service(db_engine, storage):
    """WorkspaceService with patched get_db using test engine."""
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

    svc = WorkspaceService(storage=storage)
    with patch("sayou.core.workspace.get_db", test_get_db):
        yield svc
