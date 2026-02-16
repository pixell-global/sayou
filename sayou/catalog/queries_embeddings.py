"""Database queries for embedding operations."""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import SayouEmbedding, generate_uuid


async def upsert_embedding(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    file_id: str,
    version_id: str,
    provider: str,
    model: str,
    dimensions: int,
    embedding: bytes,
    content_hash: str,
) -> SayouEmbedding:
    """Insert or update an embedding for a file."""
    existing = await session.execute(
        select(SayouEmbedding).where(
            and_(
                SayouEmbedding.file_id == file_id,
                SayouEmbedding.provider == provider,
                SayouEmbedding.model == model,
            )
        )
    )
    emb = existing.scalar_one_or_none()
    if emb:
        emb.version_id = version_id
        emb.dimensions = dimensions
        emb.embedding = embedding
        emb.content_hash = content_hash
        await session.flush()
        return emb

    emb = SayouEmbedding(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        file_id=file_id,
        version_id=version_id,
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding=embedding,
        content_hash=content_hash,
    )
    session.add(emb)
    await session.flush()
    return emb


async def get_embedding_for_file(
    session: AsyncSession,
    file_id: str,
    provider: str,
    model: str,
) -> SayouEmbedding | None:
    """Get the embedding for a specific file/provider/model combo."""
    result = await session.execute(
        select(SayouEmbedding).where(
            and_(
                SayouEmbedding.file_id == file_id,
                SayouEmbedding.provider == provider,
                SayouEmbedding.model == model,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_all_embeddings(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> list[SayouEmbedding]:
    """Get all embeddings for a workspace, optionally filtered by provider/model."""
    conditions = [
        SayouEmbedding.org_id == org_id,
        SayouEmbedding.workspace_id == workspace_id,
    ]
    if provider:
        conditions.append(SayouEmbedding.provider == provider)
    if model:
        conditions.append(SayouEmbedding.model == model)

    result = await session.execute(
        select(SayouEmbedding).where(and_(*conditions))
    )
    return list(result.scalars().all())


async def delete_embeddings_for_file(
    session: AsyncSession, file_id: str
) -> int:
    """Delete all embeddings for a file. Returns count deleted."""
    result = await session.execute(
        select(SayouEmbedding).where(SayouEmbedding.file_id == file_id)
    )
    embeddings = list(result.scalars().all())
    for emb in embeddings:
        await session.delete(emb)
    await session.flush()
    return len(embeddings)
