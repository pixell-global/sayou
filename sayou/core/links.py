"""File relationship extraction and graph utilities.

Detects wiki-links [[target]], markdown links [text](path.md),
and frontmatter relationship fields. Pure Python — no external dependencies.
"""

from __future__ import annotations

import re

# [[wiki-link]] pattern — captures the target path
_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# [text](path) markdown link — captures the target path (excludes http/https URLs)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((?!https?://)([^)]+)\)")

# Frontmatter fields that imply relationships
_RELATIONSHIP_FIELDS = {
    "related": "related",
    "depends_on": "depends_on",
    "supersedes": "supersedes",
    "parent": "parent",
    "references": "reference",
}


def extract_links_from_markdown(content: str) -> list[dict]:
    """Extract links from markdown body text.

    Returns list of {"target_path": str, "link_type": str, "context": str}.
    """
    links = []

    # Wiki-links: [[path]]
    for match in _WIKI_LINK_RE.finditer(content):
        target = match.group(1).strip()
        # Get surrounding context (up to 50 chars each side)
        start = max(0, match.start() - 50)
        end = min(len(content), match.end() + 50)
        context = content[start:end].replace("\n", " ").strip()
        links.append({
            "target_path": _normalize_path(target),
            "link_type": "reference",
            "context": context,
        })

    # Markdown links: [text](path)
    for match in _MD_LINK_RE.finditer(content):
        target = match.group(2).strip()
        # Skip anchors-only links like (#section)
        if target.startswith("#"):
            continue
        # Strip anchor from path (e.g., path.md#section -> path.md)
        if "#" in target:
            target = target.split("#")[0]
        text = match.group(1).strip()
        links.append({
            "target_path": _normalize_path(target),
            "link_type": "reference",
            "context": text or target,
        })

    return links


def extract_links_from_frontmatter(frontmatter: dict) -> list[dict]:
    """Extract relationship links from frontmatter fields.

    Recognized fields: related, depends_on, supersedes, parent, references.
    Values can be a string (single path) or list of strings.
    """
    links = []

    for field, link_type in _RELATIONSHIP_FIELDS.items():
        value = frontmatter.get(field)
        if value is None:
            continue

        targets = value if isinstance(value, list) else [value]
        for target in targets:
            if isinstance(target, str) and target.strip():
                links.append({
                    "target_path": _normalize_path(target.strip()),
                    "link_type": link_type,
                    "context": f"frontmatter.{field}",
                })

    return links


def resolve_relative_path(source_path: str, target: str) -> str:
    """Resolve a relative target path against the source file's directory.

    Examples:
        resolve_relative_path("docs/a.md", "../b.md") -> "b.md"
        resolve_relative_path("docs/a.md", "sub/c.md") -> "docs/sub/c.md"
        resolve_relative_path("docs/a.md", "/abs/d.md") -> "abs/d.md"
    """
    # Absolute paths (starting with /)
    if target.startswith("/"):
        return target.strip("/")

    # Get source directory
    source_dir = ""
    if "/" in source_path:
        source_dir = source_path.rsplit("/", 1)[0]

    # Resolve relative path
    if source_dir:
        parts = (source_dir + "/" + target).split("/")
    else:
        parts = target.split("/")

    # Resolve .. and .
    resolved: list[str] = []
    for part in parts:
        if part == "..":
            if resolved:
                resolved.pop()
        elif part != ".":
            resolved.append(part)

    return "/".join(resolved)


def _normalize_path(path: str) -> str:
    """Normalize a link target path."""
    return path.strip("/").strip()
