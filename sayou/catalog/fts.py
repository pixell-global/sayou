"""FTS5 full-text search DDL and helpers.

Creates FTS5 virtual tables (SQLite) or FULLTEXT indexes (MySQL) for
ranked text search on files and chunks.  Safe to call multiple times.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def is_sqlite(db_url: str) -> bool:
    """Return True if *db_url* points to a SQLite database."""
    return db_url.startswith("sqlite")


# ---------------------------------------------------------------------------
# SQLite FTS5
# ---------------------------------------------------------------------------

_FILES_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS sayou_files_fts USING fts5(
    file_id UNINDEXED,
    org_id UNINDEXED,
    workspace_id UNINDEXED,
    path,
    content_text,
    frontmatter
);
"""

_CHUNKS_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS sayou_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    org_id UNINDEXED,
    workspace_id UNINDEXED,
    file_id UNINDEXED,
    content
);
"""

# --- Triggers: keep FTS tables in sync with base tables ------------------

_FILES_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_files_fts_ai AFTER INSERT ON sayou_files
BEGIN
    INSERT INTO sayou_files_fts(file_id, org_id, workspace_id, path, content_text, frontmatter)
    VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.path,
            COALESCE(NEW.content_text, ''), COALESCE(NEW.frontmatter, ''));
END;
"""

_FILES_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_files_fts_au AFTER UPDATE ON sayou_files
BEGIN
    DELETE FROM sayou_files_fts WHERE file_id = OLD.id;
    INSERT INTO sayou_files_fts(file_id, org_id, workspace_id, path, content_text, frontmatter)
    VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.path,
            COALESCE(NEW.content_text, ''), COALESCE(NEW.frontmatter, ''));
END;
"""

_FILES_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_files_fts_ad AFTER DELETE ON sayou_files
BEGIN
    DELETE FROM sayou_files_fts WHERE file_id = OLD.id;
END;
"""

_CHUNKS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_ai AFTER INSERT ON sayou_chunks
BEGIN
    INSERT INTO sayou_chunks_fts(chunk_id, org_id, workspace_id, file_id, content)
    VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.file_id, NEW.content);
END;
"""

_CHUNKS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_au AFTER UPDATE ON sayou_chunks
BEGIN
    DELETE FROM sayou_chunks_fts WHERE chunk_id = OLD.id;
    INSERT INTO sayou_chunks_fts(chunk_id, org_id, workspace_id, file_id, content)
    VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.file_id, NEW.content);
END;
"""

_CHUNKS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_ad AFTER DELETE ON sayou_chunks
BEGIN
    DELETE FROM sayou_chunks_fts WHERE chunk_id = OLD.id;
END;
"""

# Populate FTS from existing data (idempotent: skips rows already present)
_FILES_FTS_POPULATE = """
INSERT OR IGNORE INTO sayou_files_fts(file_id, org_id, workspace_id, path, content_text, frontmatter)
SELECT id, org_id, workspace_id, path,
       COALESCE(content_text, ''), COALESCE(frontmatter, '')
FROM sayou_files
WHERE id NOT IN (SELECT file_id FROM sayou_files_fts);
"""

_CHUNKS_FTS_POPULATE = """
INSERT OR IGNORE INTO sayou_chunks_fts(chunk_id, org_id, workspace_id, file_id, content)
SELECT id, org_id, workspace_id, file_id, content
FROM sayou_chunks
WHERE id NOT IN (SELECT chunk_id FROM sayou_chunks_fts);
"""


async def _create_sqlite_fts(engine: AsyncEngine) -> None:
    """Create FTS5 virtual tables, triggers, and backfill existing data."""
    async with engine.begin() as conn:
        # Virtual tables
        await conn.execute(text(_FILES_FTS_DDL))
        await conn.execute(text(_CHUNKS_FTS_DDL))

        # Triggers
        for stmt in (
            _FILES_INSERT_TRIGGER,
            _FILES_UPDATE_TRIGGER,
            _FILES_DELETE_TRIGGER,
            _CHUNKS_INSERT_TRIGGER,
            _CHUNKS_UPDATE_TRIGGER,
            _CHUNKS_DELETE_TRIGGER,
        ):
            await conn.execute(text(stmt))

        # Backfill
        await conn.execute(text(_FILES_FTS_POPULATE))
        await conn.execute(text(_CHUNKS_FTS_POPULATE))


# ---------------------------------------------------------------------------
# MySQL FULLTEXT
# ---------------------------------------------------------------------------

_MYSQL_FILES_FULLTEXT = """
ALTER TABLE sayou_files
ADD FULLTEXT INDEX ft_files_search (path, content_text, frontmatter);
"""

_MYSQL_CHUNKS_FULLTEXT = """
ALTER TABLE sayou_chunks
ADD FULLTEXT INDEX ft_chunks_search (content);
"""


async def _create_mysql_fts(engine: AsyncEngine) -> None:
    """Create FULLTEXT indexes on MySQL tables. Skips if they already exist."""
    async with engine.begin() as conn:
        # Check existing indexes before adding
        for idx_name, ddl in [
            ("ft_files_search", _MYSQL_FILES_FULLTEXT),
            ("ft_chunks_search", _MYSQL_CHUNKS_FULLTEXT),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND index_name = :idx"
            ), {"idx": idx_name})
            if result.scalar() == 0:
                await conn.execute(text(ddl))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_fts_tables(engine: AsyncEngine, db_url: str) -> None:
    """Create FTS infrastructure for the given database.

    Safe to call multiple times — uses IF NOT EXISTS / existence checks.
    """
    if is_sqlite(db_url):
        await _create_sqlite_fts(engine)
    else:
        await _create_mysql_fts(engine)


async def fts_available(engine: AsyncEngine, db_url: str) -> bool:
    """Return True if FTS tables/indexes exist and are queryable."""
    try:
        async with engine.begin() as conn:
            if is_sqlite(db_url):
                result = await conn.execute(text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='sayou_files_fts'"
                ))
                return result.scalar() is not None
            else:
                result = await conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() AND index_name = 'ft_files_search'"
                ))
                return result.scalar() > 0
    except Exception:
        return False
