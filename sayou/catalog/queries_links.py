"""Database queries for file link/relationship operations."""

from __future__ import annotations

from collections import deque

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import SayouFileLink, generate_uuid


async def upsert_link(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    source_path: str,
    target_path: str,
    link_type: str = "reference",
    auto_detected: bool = False,
    context: str | None = None,
    created_by: str = "system",
) -> SayouFileLink:
    """Create or update a link between two file paths."""
    existing = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == source_path,
                SayouFileLink.target_path == target_path,
                SayouFileLink.link_type == link_type,
            )
        )
    )
    link = existing.scalar_one_or_none()
    if link:
        link.auto_detected = auto_detected
        link.context = context
        link.created_by = created_by
        await session.flush()
        return link

    link = SayouFileLink(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        source_path=source_path,
        target_path=target_path,
        link_type=link_type,
        auto_detected=auto_detected,
        context=context,
        created_by=created_by,
    )
    session.add(link)
    await session.flush()
    return link


async def delete_auto_links_for_source(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    source_path: str,
) -> int:
    """Delete all auto-detected links from a source path. Returns count deleted."""
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == source_path,
                SayouFileLink.auto_detected.is_(True),
            )
        )
    )
    links = list(result.scalars().all())
    for link in links:
        await session.delete(link)
    await session.flush()
    return len(links)


async def delete_links_for_source(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    source_path: str,
) -> int:
    """Delete ALL links from a source path (both manual and auto). Returns count deleted."""
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == source_path,
            )
        )
    )
    links = list(result.scalars().all())
    for link in links:
        await session.delete(link)
    await session.flush()
    return len(links)


async def delete_link(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    source_path: str,
    target_path: str,
    link_type: str,
) -> bool:
    """Delete a specific link. Returns True if found and deleted."""
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == source_path,
                SayouFileLink.target_path == target_path,
                SayouFileLink.link_type == link_type,
            )
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        return False
    await session.delete(link)
    await session.flush()
    return True


async def get_links_from(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    source_path: str,
) -> list[SayouFileLink]:
    """Get all outgoing links from a file path."""
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == source_path,
            )
        ).order_by(SayouFileLink.target_path)
    )
    return list(result.scalars().all())


async def get_links_to(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    target_path: str,
) -> list[SayouFileLink]:
    """Get all incoming links to a file path."""
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.target_path == target_path,
            )
        ).order_by(SayouFileLink.source_path)
    )
    return list(result.scalars().all())


async def get_neighbors(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    start_path: str,
    depth: int = 1,
) -> dict:
    """BFS graph traversal from a starting path.

    Returns {"nodes": set[str], "edges": list[dict]} within N hops.
    """
    visited: set[str] = {start_path}
    edges: list[dict] = []
    queue: deque[tuple[str, int]] = deque([(start_path, 0)])

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue

        # Get outgoing links
        outgoing = await get_links_from(session, org_id, workspace_id, current)
        for link in outgoing:
            edges.append({
                "source": link.source_path,
                "target": link.target_path,
                "link_type": link.link_type,
                "auto_detected": link.auto_detected,
            })
            if link.target_path not in visited:
                visited.add(link.target_path)
                queue.append((link.target_path, current_depth + 1))

        # Get incoming links
        incoming = await get_links_to(session, org_id, workspace_id, current)
        for link in incoming:
            edges.append({
                "source": link.source_path,
                "target": link.target_path,
                "link_type": link.link_type,
                "auto_detected": link.auto_detected,
            })
            if link.source_path not in visited:
                visited.add(link.source_path)
                queue.append((link.source_path, current_depth + 1))

    # Deduplicate edges
    seen_edges: set[tuple] = set()
    unique_edges = []
    for e in edges:
        key = (e["source"], e["target"], e["link_type"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    return {"nodes": visited, "edges": unique_edges}


async def update_links_on_move(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    old_path: str,
    new_path: str,
) -> int:
    """Update links when a file is moved/renamed.

    Updates both source_path and target_path references.
    Returns total links updated.
    """
    count = 0

    # Update source_path references
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.source_path == old_path,
            )
        )
    )
    for link in result.scalars().all():
        link.source_path = new_path
        count += 1

    # Update target_path references
    result = await session.execute(
        select(SayouFileLink).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
                SayouFileLink.target_path == old_path,
            )
        )
    )
    for link in result.scalars().all():
        link.target_path = new_path
        count += 1

    await session.flush()
    return count


async def get_graph_summary(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
) -> dict:
    """Get workspace-level graph statistics."""
    # Total links
    total_result = await session.execute(
        select(func.count(SayouFileLink.id)).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
            )
        )
    )
    total_links = total_result.scalar() or 0

    # Links by type
    type_result = await session.execute(
        select(SayouFileLink.link_type, func.count(SayouFileLink.id)).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
            )
        ).group_by(SayouFileLink.link_type)
    )
    link_types = {row[0]: row[1] for row in type_result.all()}

    # Most connected files (by outgoing + incoming count)
    out_counts = await session.execute(
        select(
            SayouFileLink.source_path,
            func.count(SayouFileLink.id).label("cnt"),
        ).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
            )
        ).group_by(SayouFileLink.source_path)
    )
    in_counts = await session.execute(
        select(
            SayouFileLink.target_path,
            func.count(SayouFileLink.id).label("cnt"),
        ).where(
            and_(
                SayouFileLink.org_id == org_id,
                SayouFileLink.workspace_id == workspace_id,
            )
        ).group_by(SayouFileLink.target_path)
    )

    connection_counts: dict[str, int] = {}
    for path, cnt in out_counts.all():
        connection_counts[path] = connection_counts.get(path, 0) + cnt
    for path, cnt in in_counts.all():
        connection_counts[path] = connection_counts.get(path, 0) + cnt

    most_connected = sorted(
        connection_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]

    return {
        "total_links": total_links,
        "link_types": link_types,
        "most_connected": [{"path": p, "connections": c} for p, c in most_connected],
    }
