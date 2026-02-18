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


async def search_chunks_fts(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    query: str,
    path_pattern: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search chunks using FTS5 MATCH with BM25 ranking (SQLite only).

    Raises an exception if FTS5 tables are not available.
    """
    from sqlalchemy import text as sa_text
    from sayou.catalog.models import SayouFile
    from sayou.catalog.queries import glob_to_regex

    fts_sql = sa_text(
        "SELECT fts.chunk_id, fts.file_id, fts.rank "
        "FROM sayou_chunks_fts fts "
        "WHERE sayou_chunks_fts MATCH :query "
        "AND fts.org_id = :org_id "
        "AND fts.workspace_id = :ws_id "
        "ORDER BY fts.rank "
        "LIMIT :lim"
    )
    fts_result = await session.execute(
        fts_sql,
        {"query": query, "org_id": org_id, "ws_id": workspace_id, "lim": limit},
    )
    fts_rows = fts_result.all()

    if not fts_rows:
        return []

    chunk_ids = [row[0] for row in fts_rows]
    file_ids = list({row[1] for row in fts_rows})

    # Fetch chunks
    chunk_result = await session.execute(
        select(SayouChunk).where(SayouChunk.id.in_(chunk_ids))
    )
    chunk_map = {c.id: c for c in chunk_result.scalars().all()}

    # Fetch files for path info
    file_result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.id.in_(file_ids),
                SayouFile.deleted_at.is_(None),
            )
        )
    )
    file_map = {f.id: f for f in file_result.scalars().all()}

    # Build results in FTS5 rank order
    results = []
    for chunk_id, file_id, _rank in fts_rows:
        chunk = chunk_map.get(chunk_id)
        file = file_map.get(file_id)
        if not chunk or not file:
            continue
        if path_pattern:
            pat_re = glob_to_regex(path_pattern)
            if not pat_re.match(file.path):
                continue
        results.append({
            "chunk": chunk,
            "path": file.path,
            "filename": file.filename,
        })

    return results


async def search_chunks_mysql_fts(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    query: str,
    path_pattern: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search chunks using MySQL FULLTEXT MATCH with relevance ranking.

    Requires ft_chunks_search FULLTEXT index on sayou_chunks.content.
    Raises an exception if FULLTEXT index is not available.
    """
    from sqlalchemy import text as sa_text
    from sayou.catalog.models import SayouFile
    from sayou.catalog.queries import glob_to_regex

    fts_sql = sa_text(
        "SELECT c.id AS chunk_id, c.file_id, "
        "MATCH(c.content) AGAINST(:query IN NATURAL LANGUAGE MODE) AS score "
        "FROM sayou_chunks c "
        "WHERE c.org_id = :org_id "
        "AND c.workspace_id = :ws_id "
        "AND MATCH(c.content) AGAINST(:query IN NATURAL LANGUAGE MODE) "
        "ORDER BY score DESC "
        "LIMIT :lim"
    )
    fts_result = await session.execute(
        fts_sql,
        {"query": query, "org_id": org_id, "ws_id": workspace_id, "lim": limit},
    )
    fts_rows = fts_result.all()

    if not fts_rows:
        return []

    chunk_ids = [row[0] for row in fts_rows]
    file_ids = list({row[1] for row in fts_rows})

    # Fetch chunks
    chunk_result = await session.execute(
        select(SayouChunk).where(SayouChunk.id.in_(chunk_ids))
    )
    chunk_map = {c.id: c for c in chunk_result.scalars().all()}

    # Fetch files for path info
    file_result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.id.in_(file_ids),
                SayouFile.deleted_at.is_(None),
            )
        )
    )
    file_map = {f.id: f for f in file_result.scalars().all()}

    # Build results in relevance order
    results = []
    for chunk_id, file_id, _score in fts_rows:
        chunk = chunk_map.get(chunk_id)
        file = file_map.get(file_id)
        if not chunk or not file:
            continue
        if path_pattern:
            pat_re = glob_to_regex(path_pattern)
            if not pat_re.match(file.path):
                continue
        results.append({
            "chunk": chunk,
            "path": file.path,
            "filename": file.filename,
        })

    return results


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

    # For multi-word queries, split into terms and match ANY (OR logic)
    from sqlalchemy import or_
    terms = query.split()
    if len(terms) <= 1:
        terms = [query]
    term_conditions = []
    for term in terms:
        if term.strip():
            term_conditions.append(SayouChunk.content.like(f"%{term.strip()}%"))

    conditions = [
        SayouChunk.org_id == org_id,
        SayouChunk.workspace_id == workspace_id,
        or_(*term_conditions) if term_conditions else SayouChunk.content.like(f"%{query}%"),
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
