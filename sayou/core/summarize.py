"""Context-aware content summarization.

Produces structural summaries with section pointers for drill-down,
keeping output within a character budget.
"""

import json
import re


def summarize_content(content: str, frontmatter: dict, char_budget: int) -> dict:
    """Produce a structural summary that fits within char_budget.

    Returns:
        {
            "summary": str,        # fits within char_budget
            "sections": [          # drill-down pointers
                {"heading": "## Background", "line_start": 15, "line_end": 42},
            ],
            "total_lines": int,
        }
    """
    lines = content.split("\n")
    total_lines = len(lines)

    # Extract section headings with line ranges
    sections = _extract_sections(lines)

    # Build the summary
    parts = []

    # Frontmatter summary
    if frontmatter:
        fm_lines = ["**Frontmatter:**"]
        for k, v in frontmatter.items():
            val = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            fm_lines.append(f"  {k}: {val}")
        parts.append("\n".join(fm_lines))

    # Section outline with first lines
    if sections:
        parts.append("")
        parts.append("**Sections:**")
        for sec in sections:
            first_line = _get_first_content_line(lines, sec["line_start"] - 1, sec["line_end"] - 1)
            preview = f"  {sec['heading']} (lines {sec['line_start']}-{sec['line_end']})"
            if first_line:
                preview += f" — {first_line[:80]}"
            parts.append(preview)

    # Section pointers for drill-down
    if sections:
        parts.append("")
        parts.append(f"*{total_lines} total lines. Use read_section() to drill into specific sections.*")

    summary = "\n".join(parts)

    # Truncate if still over budget
    if len(summary) > char_budget:
        summary = summary[:char_budget - 20] + "\n\n*(truncated)*"

    return {
        "summary": summary,
        "sections": sections,
        "total_lines": total_lines,
    }


def _extract_sections(lines: list[str]) -> list[dict]:
    """Extract markdown headings and their line ranges."""
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
    sections = []

    for i, line in enumerate(lines):
        m = heading_re.match(line)
        if m:
            sections.append({
                "heading": line.strip(),
                "line_start": i + 1,  # 1-indexed
                "line_end": 0,  # will be filled
            })

    # Fill line_end: each section ends where the next begins (or at EOF)
    for idx in range(len(sections)):
        if idx + 1 < len(sections):
            sections[idx]["line_end"] = sections[idx + 1]["line_start"] - 1
        else:
            sections[idx]["line_end"] = len(lines)

    return sections


def _get_first_content_line(lines: list[str], start: int, end: int) -> str:
    """Get the first non-empty, non-heading line in a range."""
    heading_re = re.compile(r"^#{1,6}\s+")
    for i in range(start, min(end + 1, len(lines))):
        line = lines[i].strip()
        if line and not heading_re.match(line):
            return line
    return ""
