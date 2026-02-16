"""Database queries for chunk operations."""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import SayouChunk, generate_uuid


async def replace_chunks_for_file(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    file_id: str,
    version_id: str,
    chunks: list[dict],
) -> list[SayouChunk]:
    """Delete old chunks and insert new ones for a file version."""
    # Delete existing chunks for this file
    await delete_chunks_for_file(session, file_id)

    # Insert new chunks
    result = []
    for chunk_data in chunks:
        chunk = SayouChunk(
            id=generate_uuid(),
            org_id=org_id,
            workspace_id=workspace_id,
            file_id=file_id,
            version_id=version_id,
            chunk_index=chunk_data["chunk_index"],
            heading=chunk_data.get("heading"),
            heading_level=chunk_data.get("heading_level"),
            content=chunk_data["content"],
            line_start=chunk_data["line_start"],
            line_end=chunk_data["line_end"],
            char_count=chunk_data["char_count"],
            token_estimate=chunk_data["token_estimate"],
            content_hash=chunk_data["content_hash"],
        )
        session.add(chunk)
        result.append(chunk)

    await session.flush()
    return result


async def get_chunks_for_file(
    session: AsyncSession, file_id: str
) -> list[SayouChunk]:
    """Get all chunks for a file, ordered by chunk_index."""
    result = await session.execute(
        select(SayouChunk)
        .where(SayouChunk.file_id == file_id)
        .order_by(SayouChunk.chunk_index)
    )
    return list(result.scalars().all())


async def get_chunk_by_index(
    session: AsyncSession, file_id: str, chunk_index: int
) -> SayouChunk | None:
    """Get a specific chunk by file_id and index."""
    result = await session.execute(
        select(SayouChunk).where(
            and_(
                SayouChunk.file_id == file_id,
                SayouChunk.chunk_index == chunk_index,
            )
        )
    )
    return result.scalar_one_or_none()


async def search_chunks(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    query: str,
    path_pattern: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search chunk content using SQL LIKE. Returns dicts with file path info.

    Joins with SayouFile to get path information.
    """
    from sayou.catalog.models import SayouFile
    from sayou.catalog.queries import glob_to_regex, glob_to_sql

    pattern = f"%{query}%"
    conditions = [
        SayouChunk.org_id == org_id,
        SayouChunk.workspace_id == workspace_id,
        SayouChunk.content.like(pattern),
        SayouFile.id == SayouChunk.file_id,
        SayouFile.deleted_at.is_(None),
    ]

    if path_pattern:
        sql_pat = glob_to_sql(path_pattern)
        conditions.append(SayouFile.path.like(sql_pat))

    result = await session.execute(
        select(SayouChunk, SayouFile.path, SayouFile.filename)
        .where(and_(*conditions))
        .order_by(SayouFile.path, SayouChunk.chunk_index)
        .limit(limit)
    )
    rows = result.all()

    # Apply regex filter for path pattern
    if path_pattern:
        pat_re = glob_to_regex(path_pattern)
        rows = [r for r in rows if pat_re.match(r[1])]

    return [
        {
            "chunk": r[0],
            "path": r[1],
            "filename": r[2],
        }
        for r in rows
    ]


async def delete_chunks_for_file(
    session: AsyncSession, file_id: str
) -> int:
    """Delete all chunks for a file. Returns count deleted."""
    result = await session.execute(
        select(SayouChunk).where(SayouChunk.file_id == file_id)
    )
    chunks = list(result.scalars().all())
    for chunk in chunks:
        await session.delete(chunk)
    await session.flush()
    return len(chunks)
