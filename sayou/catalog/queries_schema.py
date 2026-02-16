"""Database queries for workspace schema operations."""

from __future__ import annotations

import json

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import SayouWorkspaceSchema, generate_uuid


async def upsert_schema_field(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    field_name: str,
    field_type: str,
    occurrence_count: int,
    sample_values: list | None = None,
    is_auto: bool = False,
) -> SayouWorkspaceSchema:
    """Insert or update a schema field entry."""
    existing = await session.execute(
        select(SayouWorkspaceSchema).where(
            and_(
                SayouWorkspaceSchema.org_id == org_id,
                SayouWorkspaceSchema.workspace_id == workspace_id,
                SayouWorkspaceSchema.field_name == field_name,
            )
        )
    )
    field = existing.scalar_one_or_none()
    if field:
        field.field_type = field_type
        field.occurrence_count = occurrence_count
        field.sample_values = json.dumps(sample_values) if sample_values else None
        field.is_auto = is_auto
        await session.flush()
        return field

    field = SayouWorkspaceSchema(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        field_name=field_name,
        field_type=field_type,
        occurrence_count=occurrence_count,
        sample_values=json.dumps(sample_values) if sample_values else None,
        is_auto=is_auto,
    )
    session.add(field)
    await session.flush()
    return field


async def get_schema(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
) -> list[SayouWorkspaceSchema]:
    """Get the full schema for a workspace."""
    result = await session.execute(
        select(SayouWorkspaceSchema).where(
            and_(
                SayouWorkspaceSchema.org_id == org_id,
                SayouWorkspaceSchema.workspace_id == workspace_id,
            )
        ).order_by(SayouWorkspaceSchema.field_name)
    )
    return list(result.scalars().all())


async def delete_schema(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
) -> int:
    """Delete all schema entries for a workspace. Returns count deleted."""
    result = await session.execute(
        select(SayouWorkspaceSchema).where(
            and_(
                SayouWorkspaceSchema.org_id == org_id,
                SayouWorkspaceSchema.workspace_id == workspace_id,
            )
        )
    )
    entries = list(result.scalars().all())
    for entry in entries:
        await session.delete(entry)
    await session.flush()
    return len(entries)
