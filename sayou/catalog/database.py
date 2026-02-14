from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sayou.config import settings

_engine = None
_session_factory = None


def _create_engine(url: str | None = None):
    db_url = url or settings.database_url
    is_sqlite = db_url.startswith("sqlite")

    kwargs = {}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow

    return create_async_engine(db_url, echo=settings.database_echo, **kwargs)


async def init_db(url: str | None = None):
    global _engine, _session_factory
    _engine = _create_engine(url)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def close_db():
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    global _engine, _session_factory
    if _session_factory is None:
        await init_db()
    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
