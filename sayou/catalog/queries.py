import json
import re

from datetime import datetime

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayou.catalog.models import (
    SayouFile,
    SayouFileVersion,
    SayouIndexCache,
    SayouKVEntry,
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
    else:
        # Ensure the current user has access
        member = await get_membership(session, ws.id, user_id)
        if member is None:
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


async def get_file_by_path_including_deleted(
    session: AsyncSession, org_id: str, workspace_id: str, path: str
) -> SayouFile | None:
    """Like get_file_by_path but also returns soft-deleted files.

    Used by the write path to restore (undelete) files that were previously
    soft-deleted, avoiding UNIQUE constraint violations on re-sync.
    """
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.path == path,
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


async def get_subfolder_stats(
    session: AsyncSession, org_id: str, workspace_id: str, parent_folder: str = "/"
) -> list[dict]:
    """Get stats (file_count, last_updated) for each immediate subfolder.

    Returns list of {"folder": str, "file_count": int, "last_updated": datetime|None}.
    """
    # Get all files in the workspace that are not deleted
    result = await session.execute(
        select(
            SayouFile.folder_path,
            func.count(SayouFile.id).label("file_count"),
            func.max(SayouFile.updated_at).label("last_updated"),
        ).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.deleted_at.is_(None),
            )
        ).group_by(SayouFile.folder_path)
    )
    rows = result.all()

    # Aggregate into immediate subfolders of parent_folder
    folder_stats: dict[str, dict] = {}
    for folder_path, file_count, last_updated in rows:
        if parent_folder == "/":
            # Top-level: extract first path segment
            parts = folder_path.strip("/").split("/")
            if not parts or not parts[0]:
                # Root-level files (folder_path="/") — skip, handled separately
                continue
            top_folder = parts[0]
        else:
            prefix = parent_folder.rstrip("/") + "/"
            if not folder_path.startswith(prefix) and folder_path != parent_folder:
                continue
            if folder_path == parent_folder:
                continue
            remainder = folder_path[len(prefix):]
            parts = remainder.strip("/").split("/")
            if not parts or not parts[0]:
                continue
            top_folder = parts[0]

        if top_folder not in folder_stats:
            folder_stats[top_folder] = {"folder": top_folder, "file_count": 0, "last_updated": None}
        folder_stats[top_folder]["file_count"] += file_count
        existing = folder_stats[top_folder]["last_updated"]
        if last_updated and (existing is None or last_updated > existing):
            folder_stats[top_folder]["last_updated"] = last_updated

    return sorted(folder_stats.values(), key=lambda s: s["folder"])


async def update_file_path(
    session: AsyncSession,
    file_id: str,
    new_path: str,
    new_folder_path: str,
    new_filename: str,
) -> None:
    """Update the path of a file (for move operations). Catalog-only, no S3 ops."""
    result = await session.execute(
        select(SayouFile).where(SayouFile.id == file_id)
    )
    file = result.scalar_one()
    file.path = new_path
    file.folder_path = new_folder_path
    file.filename = new_filename
    await session.flush()


async def duplicate_file(
    session: AsyncSession,
    source_file: SayouFile,
    new_path: str,
    new_folder_path: str,
    new_filename: str,
    created_by: str,
) -> tuple[SayouFile, SayouFileVersion | None]:
    """Duplicate a file record pointing to the same S3 version objects.

    Creates a new file and a new version record pointing to the same S3 key.
    Returns (new_file, new_version).
    """
    new_file = SayouFile(
        id=generate_uuid(),
        org_id=source_file.org_id,
        workspace_id=source_file.workspace_id,
        path=new_path,
        folder_path=new_folder_path,
        filename=new_filename,
        content_type=source_file.content_type,
        frontmatter=source_file.frontmatter,
        content_text=source_file.content_text,
        version_count=0,
    )
    session.add(new_file)
    await session.flush()

    # Copy the latest version if exists
    if source_file.current_version_id:
        source_version = await get_version(session, source_file.current_version_id)
        if source_version:
            new_version = SayouFileVersion(
                id=generate_uuid(),
                file_id=new_file.id,
                version_number=1,
                s3_key=source_version.s3_key,
                s3_bucket=source_version.s3_bucket,
                size_bytes=source_version.size_bytes,
                content_hash=source_version.content_hash,
                created_by=created_by,
            )
            session.add(new_version)
            await session.flush()
            new_file.current_version_id = new_version.id
            new_file.version_count = 1
            await session.flush()
            return new_file, new_version

    return new_file, None


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


async def search_files_fts(
    session: AsyncSession, org_id: str, workspace_id: str, query: str
) -> list[SayouFile]:
    """Search files using FTS5 MATCH with BM25 ranking (SQLite only).

    Tokenizes the query so "password hashing" matches documents containing
    both words anywhere. Results are ranked by BM25 relevance score.

    Raises an exception if FTS5 tables are not available.
    """
    from sqlalchemy import text

    fts_sql = text(
        "SELECT fts.file_id, fts.rank "
        "FROM sayou_files_fts fts "
        "WHERE sayou_files_fts MATCH :query "
        "AND fts.org_id = :org_id "
        "AND fts.workspace_id = :ws_id "
        "ORDER BY fts.rank "
        "LIMIT 50"
    )
    fts_result = await session.execute(
        fts_sql, {"query": query, "org_id": org_id, "ws_id": workspace_id}
    )
    fts_rows = fts_result.all()

    if not fts_rows:
        return []

    # Fetch the actual SayouFile records in ranked order
    file_ids = [row[0] for row in fts_rows]
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.id.in_(file_ids),
                SayouFile.deleted_at.is_(None),
            )
        )
    )
    file_map = {f.id: f for f in result.scalars().all()}
    # Preserve FTS5 rank order
    return [file_map[fid] for fid in file_ids if fid in file_map]


async def search_files_mysql_fts(
    session: AsyncSession, org_id: str, workspace_id: str, query: str
) -> list[SayouFile]:
    """Search files using MySQL FULLTEXT MATCH with relevance ranking.

    Uses MATCH ... AGAINST in natural language mode for tokenized search
    with relevance scoring. Requires ft_files_search FULLTEXT index.

    Raises an exception if FULLTEXT index is not available.
    """
    from sqlalchemy import text

    fts_sql = text(
        "SELECT f.id, "
        "MATCH(f.path, f.content_text, f.frontmatter) AGAINST(:query IN NATURAL LANGUAGE MODE) AS score "
        "FROM sayou_files f "
        "WHERE f.org_id = :org_id "
        "AND f.workspace_id = :ws_id "
        "AND f.deleted_at IS NULL "
        "AND MATCH(f.path, f.content_text, f.frontmatter) AGAINST(:query IN NATURAL LANGUAGE MODE) "
        "ORDER BY score DESC "
        "LIMIT 50"
    )
    fts_result = await session.execute(
        fts_sql, {"query": query, "org_id": org_id, "ws_id": workspace_id}
    )
    fts_rows = fts_result.all()

    if not fts_rows:
        return []

    # Fetch the actual SayouFile records in ranked order
    file_ids = [row[0] for row in fts_rows]
    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.id.in_(file_ids),
                SayouFile.deleted_at.is_(None),
            )
        )
    )
    file_map = {f.id: f for f in result.scalars().all()}
    # Preserve relevance order
    return [file_map[fid] for fid in file_ids if fid in file_map]


async def search_files_fulltext(
    session: AsyncSession, org_id: str, workspace_id: str, query: str
) -> list[SayouFile]:
    """Fallback search using LIKE (no ranking, works on all databases).

    For multi-word queries, splits into individual terms and matches files
    containing ANY term (OR logic). This handles CJK queries where the
    exact multi-word phrase may not appear as a contiguous substring.
    """
    terms = query.split()
    if len(terms) <= 1:
        terms = [query]

    # Build OR conditions: file matches if ANY term appears in path/content/frontmatter
    from sqlalchemy import or_
    term_conditions = []
    for term in terms:
        if not term.strip():
            continue
        pattern = f"%{term.strip()}%"
        term_conditions.append(
            SayouFile.path.like(pattern)
            | SayouFile.frontmatter.like(pattern)
            | SayouFile.content_text.like(pattern)
        )

    if not term_conditions:
        return []

    result = await session.execute(
        select(SayouFile).where(
            and_(
                SayouFile.org_id == org_id,
                SayouFile.workspace_id == workspace_id,
                SayouFile.deleted_at.is_(None),
                or_(*term_conditions),
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


async def query_mutation_log(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    *,
    file_path: str | None = None,
    action: str | None = None,
    agent_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
) -> list[SayouMutationLog]:
    """Query the mutation log with optional filters."""
    limit = min(limit, 200)

    conditions = [
        SayouMutationLog.org_id == org_id,
        SayouMutationLog.workspace_id == workspace_id,
    ]
    if file_path is not None:
        conditions.append(SayouMutationLog.file_path == file_path)
    if action is not None:
        conditions.append(SayouMutationLog.action == action)
    if agent_id is not None:
        conditions.append(SayouMutationLog.agent_id == agent_id)
    if since is not None:
        conditions.append(SayouMutationLog.created_at >= since)
    if until is not None:
        conditions.append(SayouMutationLog.created_at <= until)

    result = await session.execute(
        select(SayouMutationLog)
        .where(and_(*conditions))
        .order_by(SayouMutationLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# --- KV Store ---


async def kv_get(
    session: AsyncSession, org_id: str, workspace_id: str, key: str
) -> SayouKVEntry | None:
    """Get a KV entry, filtering out expired entries (lazy expiry)."""
    result = await session.execute(
        select(SayouKVEntry).where(
            and_(
                SayouKVEntry.org_id == org_id,
                SayouKVEntry.workspace_id == workspace_id,
                SayouKVEntry.key == key,
            )
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    # Lazy expiry check
    if entry.expires_at is not None and entry.expires_at <= datetime.utcnow():
        await session.delete(entry)
        await session.flush()
        return None
    return entry


async def kv_set(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    key: str,
    value: str,
    ttl_seconds: int | None = None,
) -> SayouKVEntry:
    """Set (upsert) a KV entry. value should be JSON-encoded."""
    expires_at = None
    if ttl_seconds is not None:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    existing = await session.execute(
        select(SayouKVEntry).where(
            and_(
                SayouKVEntry.org_id == org_id,
                SayouKVEntry.workspace_id == workspace_id,
                SayouKVEntry.key == key,
            )
        )
    )
    entry = existing.scalar_one_or_none()
    if entry:
        entry.value = value
        entry.ttl_seconds = ttl_seconds
        entry.expires_at = expires_at
        await session.flush()
        return entry

    entry = SayouKVEntry(
        id=generate_uuid(),
        org_id=org_id,
        workspace_id=workspace_id,
        key=key,
        value=value,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
    )
    session.add(entry)
    await session.flush()
    return entry


async def kv_delete(
    session: AsyncSession, org_id: str, workspace_id: str, key: str
) -> bool:
    """Delete a KV entry. Returns True if entry existed."""
    result = await session.execute(
        select(SayouKVEntry).where(
            and_(
                SayouKVEntry.org_id == org_id,
                SayouKVEntry.workspace_id == workspace_id,
                SayouKVEntry.key == key,
            )
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    await session.delete(entry)
    await session.flush()
    return True


async def kv_list(
    session: AsyncSession,
    org_id: str,
    workspace_id: str,
    prefix: str | None = None,
) -> list[SayouKVEntry]:
    """List KV entries, optionally filtered by key prefix. Filters out expired."""
    conditions = [
        SayouKVEntry.org_id == org_id,
        SayouKVEntry.workspace_id == workspace_id,
    ]
    if prefix:
        conditions.append(SayouKVEntry.key.like(prefix + "%"))

    # Filter out expired
    now = datetime.utcnow()
    conditions.append(
        or_(SayouKVEntry.expires_at.is_(None), SayouKVEntry.expires_at > now)
    )

    result = await session.execute(
        select(SayouKVEntry).where(and_(*conditions)).order_by(SayouKVEntry.key)
    )
    return list(result.scalars().all())
