"""sayou status — show diagnostic information."""

from __future__ import annotations

import sys
from pathlib import Path

from sayou.config import settings


def _redact_url(url: str) -> str:
    """Redact credentials from database URL for display."""
    if "@" in url:
        # mysql+aiomysql://user:pass@host/db -> mysql+aiomysql://***@host/db
        scheme, rest = url.split("://", 1)
        _, host_part = rest.rsplit("@", 1)
        return f"{scheme}://***@{host_part}"
    return url


def _dir_size(path: Path) -> int:
    """Get total size of all files in a directory."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


async def run_status() -> None:
    """Show sayou diagnostic status."""
    from sayou.catalog.database import get_db, init_db
    from sqlalchemy import text

    db_url = settings.database_url
    display_url = _redact_url(db_url)

    # Database status
    file_count = 0
    try:
        await init_db(db_url)
        async with get_db() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM sayou_files "
                    "WHERE org_id = :org AND deleted_at IS NULL"
                ),
                {"org": settings.org_id},
            )
            file_count = result.scalar() or 0
        db_status = f"OK, {file_count} files"
    except Exception as e:
        db_status = f"ERROR: {e}"

    # Storage status
    has_s3 = bool(settings.s3_access_key_id and settings.s3_secret_access_key)
    if has_s3:
        storage_info = f"s3://{settings.s3_bucket_name}"
    else:
        storage_path = Path.home() / ".sayou" / "storage"
        size = _dir_size(storage_path)
        storage_info = f"local ({storage_path}, {_format_size(size)})"

    # Config file
    config_path = Path.home() / ".sayou" / "config.yaml"
    config_status = str(config_path) if config_path.exists() else "not found (run: sayou init)"

    # Version
    try:
        from importlib.metadata import version
        ver = version("sayou")
    except Exception:
        ver = "unknown"

    # Print
    print(f"Database:  {display_url} ({db_status})")
    print(f"Storage:   {storage_info}")
    print(f"Identity:  org={settings.org_id}, user={settings.user_id}")
    print(f"Workspace: {settings.workspace_slug}")
    print(f"Config:    {config_status}")
    print(f"Version:   {ver}")

    if "ERROR" in db_status:
        sys.exit(1)
