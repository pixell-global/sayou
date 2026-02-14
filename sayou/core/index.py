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
