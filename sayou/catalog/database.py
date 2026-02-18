import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sayou.config import settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _ensure_sqlite_dir(db_url: str) -> None:
    """Create parent directory for SQLite database files."""
    if ":///" in db_url:
        db_path = db_url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _stamp_alembic_head(db_url: str) -> None:
    """Stamp the database with the latest alembic version after create_all."""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_dir = str(Path(__file__).resolve().parent.parent / "alembic")
        sync_url = db_url.replace("+aiosqlite", "").replace("+aiomysql", "+pymysql")

        cfg = Config()
        cfg.set_main_option("script_location", alembic_dir)
        cfg.set_main_option("sqlalchemy.url", sync_url)
        cfg.set_main_option("version_table", "sayou_alembic_version")
        command.stamp(cfg, "head")
    except Exception as e:
        logger.debug("Could not stamp alembic version: %s", e)


def _create_engine(url: str | None = None):
    db_url = url or settings.database_url
    is_sqlite = db_url.startswith("sqlite")

    kwargs = {}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    else:
        if "mysql" in db_url or "aiomysql" in db_url:
            try:
                import aiomysql  # noqa: F401
            except ImportError:
                raise ImportError(
                    "MySQL support requires additional dependencies. "
                    "Install with: pip install sayou[mysql]"
                )
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow

    return create_async_engine(db_url, echo=settings.database_echo, **kwargs)


async def init_db(url: str | None = None):
    global _engine, _session_factory

    db_url = url or settings.database_url

    # Auto-create directory for SQLite databases
    if db_url.startswith("sqlite"):
        _ensure_sqlite_dir(db_url)

    _engine = _create_engine(url)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Auto-create tables for SQLite (dev/local mode)
    if db_url.startswith("sqlite"):
        from sayou.catalog.models import Base
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create FTS5 virtual tables and triggers
        from sayou.catalog.fts import create_fts_tables
        await create_fts_tables(_engine, db_url)

        # Stamp alembic version so future migrations know where we are
        await asyncio.to_thread(_stamp_alembic_head, db_url)


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
