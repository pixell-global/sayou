"""Schema discovery for workspace frontmatter fields.

Scans all file frontmatter to discover field names, types, and value distributions.
Pure Python — no external dependencies, no LLM needed.
"""

from __future__ import annotations

import json
from datetime import datetime


def infer_field_type(values: list) -> str:
    """Infer the type of a frontmatter field from its observed values."""
    if not values:
        return "string"

    type_counts = {"string": 0, "number": 0, "boolean": 0, "list": 0, "date": 0}

    for v in values:
        if isinstance(v, bool):
            type_counts["boolean"] += 1
        elif isinstance(v, (int, float)):
            type_counts["number"] += 1
        elif isinstance(v, list):
            type_counts["list"] += 1
        elif isinstance(v, str):
            # Try to detect dates
            if _looks_like_date(v):
                type_counts["date"] += 1
            else:
                type_counts["string"] += 1
        else:
            type_counts["string"] += 1

    # Return the most common type
    return max(type_counts, key=type_counts.get)


def _looks_like_date(value: str) -> bool:
    """Heuristic: check if a string looks like a date."""
    date_formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
    ]
    for fmt in date_formats:
        try:
            datetime.strptime(value.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def discover_schema(files_frontmatter: list[dict]) -> list[dict]:
    """Discover the frontmatter schema across all files.

    Args:
        files_frontmatter: List of frontmatter dicts (one per file).

    Returns:
        List of field descriptors: {
            "field_name": str,
            "field_type": str,
            "occurrence_count": int,
            "sample_values": list (up to 10 unique samples),
            "is_auto": bool (True if field starts with _auto_),
        }
    """
    # Collect all values per field
    field_values: dict[str, list] = {}

    for fm in files_frontmatter:
        if not fm:
            continue
        for key, value in fm.items():
            if key not in field_values:
                field_values[key] = []
            field_values[key].append(value)

    # Build schema
    schema = []
    for field_name, values in sorted(field_values.items()):
        # Collect unique sample values (up to 10)
        samples = []
        seen = set()
        for v in values:
            v_str = json.dumps(v) if not isinstance(v, str) else v
            if v_str not in seen and len(samples) < 10:
                seen.add(v_str)
                samples.append(v)

        schema.append({
            "field_name": field_name,
            "field_type": infer_field_type(values),
            "occurrence_count": len(values),
            "sample_values": samples,
            "is_auto": field_name.startswith("_auto_"),
        })

    return schema
