import re

import yaml


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from content. Lenient: never raises, never rejects.

    Handles:
    - Standard --- delimited frontmatter
    - Missing closing --- (parse until blank line or heading)
    - Bare key: value pairs at start (no ---)
    - Any failure returns ({}, original_content)
    """
    if not content or not content.strip():
        return {}, content or ""

    lines = content.split("\n")

    # Case 1: Standard --- delimited frontmatter
    if lines[0].strip() == "---":
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is not None:
            yaml_block = "\n".join(lines[1:end_idx])
            body = "\n".join(lines[end_idx + 1:])
            parsed = _safe_parse_yaml(yaml_block)
            if parsed is not None:
                return parsed, body.lstrip("\n")

        # Case 2: Opening --- but no closing ---
        # Parse until blank line or heading
        yaml_lines = []
        end_idx = len(lines)
        for i in range(1, len(lines)):
            line = lines[i]
            if line.strip() == "" or line.startswith("#"):
                end_idx = i
                break
            yaml_lines.append(line)

        if yaml_lines:
            yaml_block = "\n".join(yaml_lines)
            body = "\n".join(lines[end_idx:])
            parsed = _safe_parse_yaml(yaml_block)
            if parsed is not None:
                return parsed, body.lstrip("\n")

        return {}, content

    # Case 3: Bare key: value pairs at start (no ---)
    kv_pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*:.*$")
    kv_lines = []
    end_idx = 0
    for i, line in enumerate(lines):
        if kv_pattern.match(line):
            kv_lines.append(line)
            end_idx = i + 1
        else:
            break

    if len(kv_lines) >= 2:
        yaml_block = "\n".join(kv_lines)
        body = "\n".join(lines[end_idx:])
        parsed = _safe_parse_yaml(yaml_block)
        if parsed is not None:
            return parsed, body.lstrip("\n")

    return {}, content


def _safe_parse_yaml(yaml_str: str) -> dict | None:
    """Parse YAML string, returning dict or None on any error."""
    try:
        result = yaml.safe_load(yaml_str)
        if isinstance(result, dict):
            return _normalize_values(result)
        return None
    except Exception:
        return None


def _normalize_values(d: dict) -> dict:
    """Ensure all values are JSON-serializable (date/datetime → str)."""
    import datetime

    normalized = {}
    for k, v in d.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            normalized[k] = v.isoformat()
        elif isinstance(v, dict):
            normalized[k] = _normalize_values(v)
        elif isinstance(v, list):
            normalized[k] = [
                item.isoformat() if isinstance(item, (datetime.date, datetime.datetime)) else item
                for item in v
            ]
        else:
            normalized[k] = v
    return normalized
