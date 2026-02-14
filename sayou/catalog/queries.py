import json
import re

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import (
    SayouFile,
    SayouFileVersion,
    SayouIndexCache,
    SayouMutationLog,
    SayouWorkspace,
    SayouWorkspaceMember,
    generate_uuid,
)

ROLE_HIERARCHY = {"reader": 0, "writer": 1, "admin": 2}


# --- Workspace ---


async def get_workspace_by_slug(
    session: AsyncSession, org_id: str, slug: str
) -> SayouWorkspace | None:
    result = await session.execute(
        select(SayouWorkspace).where(
            and_(SayouWorkspace.org_id == org_id, SayouWorkspace.slug == slug)
        )
    )
    return result.scalar_one_or_none()


async def create_workspace(
    session: AsyncSession, org_id: str, slug: str, name: str, created_by: str
) -> SayouWorkspace:
    ws = SayouWorkspace(
        id=generate_uuid(), org_id=org_id, slug=slug, name=name, created_by=created_by
    )
    session.add(ws)
    await session.flush()
    return ws


async def ensure_default_workspace(
    session: AsyncSession, org_id: str, user_id: str
) -> SayouWorkspace:
    ws = await get_workspace_by_slug(session, org_id, "default")
    if ws is None:
        ws = await create_workspace(session, org_id, "default", "Default Workspace", user_id)
        await add_member(session, ws.id, user_id, "admin")
    return ws


# --- Membership ---


async def get_membership(
    session: AsyncSession, workspace_id: str, user_id: str
) -> SayouWorkspaceMember | None:
    result = await session.execute(
        select(SayouWorkspaceMember).where(
            and_(
                SayouWorkspaceMember.workspace_id == workspace_id,
                SayouWorkspaceMember.user_id == user_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def add_member(
    session: AsyncSession, workspace_id: str, user_id: str, role: str = "reader"
) -> SayouWorkspaceMember:
    member = SayouWorkspaceMember(
        id=generate_uuid(), workspace_id=workspace_id, user_id=user_id, role=role
    )
    session.add(member)
    await session.flush()
    return member


async def check_permission(
    session: AsyncSession, workspace_id: str, user_id: str, required_role: str
) -> bool:
    member = await get_membership(session, workspace_id, user_id)
    if member is None:
        return False
    return ROLE_HIERARCHY.get(member.role, -1) >= ROLE_HIERARCHY.get(required_role, 99)


# --- Files ---


async def get_file_by_path(
    session: AsyncSession, org_id: str, workspace_id: str, path: str
) -> SayouFile | None:
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.path == path,
                SayouFile.deleted_at.is_(None),
            )
        )
    )
    return result.scalar_one_or_none()


async def create_file(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    path: str,
    folder_path: str,
    filename: str,
    content_type: str = "text/markdown",
    frontmatter: dict | None = None,
    content_text: str | None = None,
) -> SayouFile:
    file = SayouFile(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        path=path,
        folder_path=folder_path,
        filename=filename,
        content_type=content_type,
        frontmatter=json.dumps(frontmatter) if frontmatter else None,
        content_text=content_text,
        version_count=0,
    )
    session.add(file)
    await session.flush()
    return file


async def update_file_current_version(
    session: AsyncSession,
    file_id: str,
    version_id: str,
    version_count: int,
    frontmatter: dict | None = None,
    content_text: str | None = None,
) -> None:
    result = await session.execute(
        select(SayouFile).where(SayouFile.id == file_id)
    )
    file = result.scalar_one()
    file.current_version_id = version_id
    file.version_count = version_count
    file.frontmatter = json.dumps(frontmatter) if frontmatter else file.frontmatter
    if content_text is not None:
        file.content_text = content_text
    await session.flush()


async def soft_delete_file(session: AsyncSession, file_id: str) -> None:
    result = await session.execute(
        select(SayouFile).where(SayouFile.id == file_id)
    )
    file = result.scalar_one()
    file.deleted_at = func.now()
    await session.flush()


async def list_files_in_folder(
    session: AsyncSession, org_id: str, workspace_id: str, folder_path: str
) -> list[SayouFile]:
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.folder_path == folder_path,
                SayouFile.deleted_at.is_(None),
            )
        ).order_by(SayouFile.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_subfolders(
    session: AsyncSession, org_id: str, workspace_id: str, folder_path: str
) -> list[str]:
    if folder_path == "/":
        # Get all unique top-level folder paths
        result = await session.execute(
            select(distinct(SayouFile.folder_path)).where(
                and_(
                    SayouFile.org_id == org_id,
                    SayouFile.workspace_id == workspace_id,
                    SayouFile.deleted_at.is_(None),
                )
            )
        )
    else:
        prefix = folder_path if folder_path.endswith("/") else folder_path + "/"
        result = await session.execute(
            select(distinct(SayouFile.folder_path)).where(
                and_(
                    SayouFile.org_id == org_id,
                    SayouFile.workspace_id == workspace_id,
                    SayouFile.folder_path.like(prefix + "%"),
                    SayouFile.deleted_at.is_(None),
                )
            )
        )

    all_paths = [row[0] for row in result.all()]

    # Extract immediate child folders
    subfolders = set()
    if folder_path == "/":
        for p in all_paths:
            parts = p.strip("/").split("/")
            if parts and parts[0]:
                subfolders.add(parts[0] + "/")
    else:
        prefix = folder_path.rstrip("/") + "/"
        for p in all_paths:
            if p.startswith(prefix) and p != prefix:
                remainder = p[len(prefix):]
                parts = remainder.strip("/").split("/")
                if parts and parts[0]:
                    subfolders.add(parts[0] + "/")

    return sorted(subfolders)


async def search_files_by_frontmatter(
    session: AsyncSession, org_id: str, workspace_id: str, filters: dict
) -> list[SayouFile]:
    query = select(SayouFile).where(
        and_(
            SayouFile.org_id == org_id,
            SayouFile.workspace_id == workspace_id,
            SayouFile.deleted_at.is_(None),
        )
    )
    result = await session.execute(query)
    files = list(result.scalars().all())

    # Filter in Python for cross-DB compatibility (SQLite + MySQL json_extract differences)
    matched = []
    for f in files:
        if f.frontmatter is None:
            continue
        try:
            fm = json.loads(f.frontmatter)
        except (json.JSONDecodeError, TypeError):
            continue
        match = all(fm.get(k) == v for k, v in filters.items())
        if match:
            matched.append(f)
    return matched


async def search_files_fulltext(
    session: AsyncSession, org_id: str, workspace_id: str, query: str
) -> list[SayouFile]:
    pattern = f"%{query}%"
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.deleted_at.is_(None),
                (
                    SayouFile.path.like(pattern)
                    | SayouFile.frontmatter.like(pattern)
                    | SayouFile.content_text.like(pattern)
                ),
            )
        )
    )
    return list(result.scalars().all())


# --- Glob & Recursive Listing ---


def glob_to_sql(pattern: str) -> str:
    """Convert a glob pattern to a SQL LIKE pattern (broad pre-filter).

    Both * and ** become % in SQL since LIKE can't distinguish path boundaries.
    Use glob_to_regex() for precise matching after SQL pre-filtering.
    """
    # Escape SQL LIKE special chars first
    result = pattern.replace("%", "\\%").replace("_", "\\_")
    # Then convert glob patterns
    result = result.replace("**", "\x00")  # placeholder
    result = result.replace("*", "%")
    result = result.replace("?", "_")
    result = result.replace("\x00", "%")
    return result


def glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a glob pattern to a regex that respects path boundaries.

    * matches any characters within a single path segment (no /)
    ** matches any characters across path segments (including /)
    ? matches a single non-separator character
    """
    regex_parts = []
    i = 0
    n = len(pattern)
    while i < n:
        if i < n - 1 and pattern[i:i + 2] == "**":
            regex_parts.append(".*")
            i += 2
            # Skip trailing / after ** (it's implied)
            if i < n and pattern[i] == "/":
                regex_parts.append("/?")
                i += 1
        elif pattern[i] == "*":
            regex_parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex_parts.append("[^/]")
            i += 1
        else:
            regex_parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(regex_parts) + "$")


async def list_files_by_glob(
    session: AsyncSession, org_id: str, workspace_id: str, pattern: str
) -> list[SayouFile]:
    """List files matching a glob pattern (e.g., **/*.md, research/**)."""
    sql_pattern = glob_to_sql(pattern)
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.deleted_at.is_(None),
                SayouFile.path.like(sql_pattern),
            )
        ).order_by(SayouFile.path)
    )
    candidates = list(result.scalars().all())
    # Refine with regex for proper * vs ** distinction
    pattern_re = glob_to_regex(pattern)
    return [f for f in candidates if pattern_re.match(f.path)]


async def list_all_files(
    session: AsyncSession, org_id: str, workspace_id: str, folder_prefix: str | None = None
) -> list[SayouFile]:
    """List all files, optionally filtered by folder prefix (recursive)."""
    conditions = [
        SayouFile.org_id == org_id,
        SayouFile.workspace_id == workspace_id,
        SayouFile.deleted_at.is_(None),
    ]
    if folder_prefix:
        prefix = folder_prefix if folder_prefix.endswith("/") else folder_prefix + "/"
        conditions.append(SayouFile.folder_path.like(prefix + "%"))

    result = await session.execute(
        select(SayouFile).where(and_(*conditions)).order_by(SayouFile.path)
    )
    return list(result.scalars().all())


async def search_files_content(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    query: str,
    path_pattern: str | None = None,
) -> list[SayouFile]:
    """Search files by content_text, optionally filtered by glob path pattern."""
    content_pattern = f"%{query}%"
    conditions = [
        SayouFile.org_id == org_id,
        SayouFile.workspace_id == workspace_id,
        SayouFile.deleted_at.is_(None),
        SayouFile.content_text.like(content_pattern),
    ]
    if path_pattern:
        sql_pattern = glob_to_sql(path_pattern)
        conditions.append(SayouFile.path.like(sql_pattern))

    result = await session.execute(
        select(SayouFile).where(and_(*conditions)).order_by(SayouFile.path)
    )
    candidates = list(result.scalars().all())

    if path_pattern:
        pattern_re = glob_to_regex(path_pattern)
        return [f for f in candidates if pattern_re.match(f.path)]
    return candidates


async def get_version_by_number(
    session: AsyncSession, file_id: str, version_number: int
) -> SayouFileVersion | None:
    """Get a specific version by file_id and version_number."""
    result = await session.execute(
        select(SayouFileVersion).where(
            and_(
                SayouFileVersion.file_id == file_id,
                SayouFileVersion.version_number == version_number,
            )
        )
    )
    return result.scalar_one_or_none()


# --- Versions ---


async def create_version(
    session: AsyncSession,
    file_id: str,
    version_number: int,
    s3_key: str,
    s3_bucket: str,
    size_bytes: int,
    content_hash: str,
    created_by: str,
) -> SayouFileVersion:
    version = SayouFileVersion(
        id=generate_uuid(),
        file_id=file_id,
        version_number=version_number,
        s3_key=s3_key,
        s3_bucket=s3_bucket,
        size_bytes=size_bytes,
        content_hash=content_hash,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return version


async def get_file_versions(
    session: AsyncSession, file_id: str, limit: int = 20
) -> list[SayouFileVersion]:
    result = await session.execute(
        select(SayouFileVersion)
        .where(SayouFileVersion.file_id == file_id)
        .order_by(SayouFileVersion.version_number.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_version(session: AsyncSession, version_id: str) -> SayouFileVersion | None:
    result = await session.execute(
        select(SayouFileVersion).where(SayouFileVersion.id == version_id)
    )
    return result.scalar_one_or_none()


# --- Index Cache ---


async def get_index_cache(
    session: AsyncSession, org_id: str, workspace_id: str, folder_path: str
) -> SayouIndexCache | None:
    result = await session.execute(
        select(SayouIndexCache).where(
            and_(
                SayouIndexCache.org_id == org_id,
                SayouIndexCache.workspace_id == workspace_id,
                SayouIndexCache.folder_path == folder_path,
            )
        )
    )
    return result.scalar_one_or_none()


async def upsert_index_cache(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    folder_path: str,
    content: str,
    file_count: int,
) -> SayouIndexCache:
    existing = await get_index_cache(session, org_id, workspace_id, folder_path)
    if existing:
        existing.content = content
        existing.file_count = file_count
        await session.flush()
        return existing

    cache = SayouIndexCache(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        folder_path=folder_path,
        content=content,
        file_count=file_count,
    )
    session.add(cache)
    await session.flush()
    return cache


# --- Mutation Log ---


async def log_mutation(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    agent_id: str | None,
    action: str,
    file_path: str,
    version_id: str | None = None,
) -> SayouMutationLog:
    log = SayouMutationLog(
        org_id=org_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        action=action,
        file_path=file_path,
        version_id=version_id,
    )
    session.add(log)
    await session.flush()
    return log
