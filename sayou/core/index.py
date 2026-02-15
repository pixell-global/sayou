import json
from datetime import datetime

from sayou.catalog.models import SayouFile


def generate_folder_index(folder_path: str, files: list[SayouFile]) -> str:
    """Generate a markdown table index for files in a folder.

    Dynamically discovers frontmatter columns across all files.
    Returns formatted markdown string. No LLM calls. Deterministic.
    """
    if not files:
        return f"# {folder_path}\n\n*No files in this folder.*"

    # Collect all unique frontmatter keys across files
    all_keys: list[str] = []
    seen_keys: set[str] = set()
    file_data: list[tuple[SayouFile, dict]] = []

    for f in files:
        fm = {}
        if f.frontmatter:
            try:
                fm = json.loads(f.frontmatter)
            except (json.JSONDecodeError, TypeError):
                pass
        file_data.append((f, fm))
        for key in fm:
            if key not in seen_keys:
                seen_keys.add(key)
                all_keys.append(key)

    # Build header
    header_cols = ["File"] + all_keys + ["Updated"]
    separator = ["-" * max(len(c), 3) for c in header_cols]

    # Build rows (sorted by updated_at descending)
    file_data.sort(key=lambda x: x[0].updated_at or datetime.min, reverse=True)

    rows = []
    for f, fm in file_data:
        row = [f.filename]
        for key in all_keys:
            val = fm.get(key, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            elif val is None:
                val = ""
            row.append(str(val))
        updated = f.updated_at.strftime("%Y-%m-%d %H:%M") if f.updated_at else ""
        row.append(updated)
        rows.append(row)

    # Format table
    lines = [f"# {folder_path}", ""]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("| " + " | ".join(separator) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append(f"*{len(files)} files*")
    return "\n".join(lines)


def generate_root_index(
    subfolder_stats: list[dict], root_files: list[SayouFile], max_chars: int = 2000
) -> str:
    """Generate a compressed root index showing top-level folders and files.

    Returns a markdown table capped at max_chars (~500 tokens).
    subfolder_stats: list of {"folder": str, "file_count": int, "last_updated": datetime|None}
    """
    lines = ["# /", ""]

    if subfolder_stats:
        lines.append("| Folder | Files | Last Updated |")
        lines.append("| ------ | ----- | ------------ |")
        for stat in subfolder_stats:
            updated = ""
            if stat.get("last_updated"):
                updated = stat["last_updated"].strftime("%Y-%m-%d %H:%M")
            lines.append(f"| {stat['folder']}/ | {stat['file_count']} | {updated} |")
        lines.append("")

    if root_files:
        lines.append("| File | Updated |")
        lines.append("| ---- | ------- |")
        for f in root_files:
            updated = f.updated_at.strftime("%Y-%m-%d %H:%M") if f.updated_at else ""
            lines.append(f"| {f.filename} | {updated} |")
        lines.append("")

    total_files = sum(s["file_count"] for s in subfolder_stats) + len(root_files)
    lines.append(
        f"*{len(subfolder_stats)} folders, {len(root_files)} root files, "
        f"{total_files} total files*"
    )

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 20] + "\n\n*(truncated)*"
    return result
