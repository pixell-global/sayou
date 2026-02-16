"""Automatic content chunking strategies.

Splits file content into semantic chunks based on structure (headings, paragraphs).
Pure Python — no external dependencies.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol


class ChunkResult:
    """A single chunk extracted from content."""

    __slots__ = (
        "chunk_index", "heading", "heading_level", "content",
        "line_start", "line_end", "char_count", "token_estimate", "content_hash",
    )

    def __init__(
        self,
        chunk_index: int,
        content: str,
        line_start: int,
        line_end: int,
        heading: str | None = None,
        heading_level: int | None = None,
    ):
        self.chunk_index = chunk_index
        self.heading = heading
        self.heading_level = heading_level
        self.content = content
        self.line_start = line_start
        self.line_end = line_end
        self.char_count = len(content)
        self.token_estimate = max(1, len(content) // 4)
        self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChunkingStrategy(Protocol):
    """Protocol for content chunking implementations."""

    def chunk(self, content: str) -> list[ChunkResult]: ...


# Heading pattern: lines starting with 1-6 # characters followed by space
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Minimum chunk size — merge small sections below this threshold
_MIN_CHUNK_CHARS = 100

# Maximum chunk size — split large sections above this threshold
_MAX_CHUNK_CHARS = 4000


class MarkdownHeadingChunker:
    """Split markdown at heading boundaries.

    - Splits at any heading level (# through ######)
    - Merges small sections (<100 chars) into the previous chunk
    - Splits large sections (>4000 chars) at paragraph boundaries
    """

    def __init__(
        self,
        min_chunk_chars: int = _MIN_CHUNK_CHARS,
        max_chunk_chars: int = _MAX_CHUNK_CHARS,
    ):
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars

    def chunk(self, content: str) -> list[ChunkResult]:
        if not content or not content.strip():
            return []

        lines = content.split("\n")
        raw_sections = self._split_at_headings(lines)

        # Merge small sections
        merged = self._merge_small(raw_sections)

        # Split large sections
        final = self._split_large(merged)

        # Build ChunkResult objects with correct indexes
        results = []
        for i, section in enumerate(final):
            results.append(ChunkResult(
                chunk_index=i,
                content=section["content"],
                line_start=section["line_start"],
                line_end=section["line_end"],
                heading=section.get("heading"),
                heading_level=section.get("heading_level"),
            ))
        return results

    def _split_at_headings(self, lines: list[str]) -> list[dict]:
        """Split lines into sections at heading boundaries."""
        sections: list[dict] = []
        current_lines: list[str] = []
        current_heading: str | None = None
        current_level: int | None = None
        current_start: int = 1  # 1-indexed

        for i, line in enumerate(lines):
            m = _HEADING_RE.match(line)
            if m and current_lines:
                # Flush current section
                sections.append({
                    "heading": current_heading,
                    "heading_level": current_level,
                    "content": "\n".join(current_lines),
                    "line_start": current_start,
                    "line_end": current_start + len(current_lines) - 1,
                })
                current_lines = [line]
                current_heading = m.group(2).strip()
                current_level = len(m.group(1))
                current_start = i + 1  # 1-indexed
            elif m and not current_lines:
                # First heading at start
                current_lines = [line]
                current_heading = m.group(2).strip()
                current_level = len(m.group(1))
                current_start = i + 1
            else:
                current_lines.append(line)

        # Flush remaining
        if current_lines:
            sections.append({
                "heading": current_heading,
                "heading_level": current_level,
                "content": "\n".join(current_lines),
                "line_start": current_start,
                "line_end": current_start + len(current_lines) - 1,
            })

        return sections

    def _merge_small(self, sections: list[dict]) -> list[dict]:
        """Merge sections smaller than min_chunk_chars into the previous section.

        Only merges headingless small fragments — sections with their own heading
        are kept independent regardless of size.
        """
        if not sections:
            return []

        merged: list[dict] = [sections[0]]
        for section in sections[1:]:
            if (
                len(section["content"]) < self.min_chunk_chars
                and not section.get("heading")
                and merged
            ):
                # Merge headingless small fragment into previous
                prev = merged[-1]
                prev["content"] = prev["content"] + "\n" + section["content"]
                prev["line_end"] = section["line_end"]
            else:
                merged.append(section)

        return merged

    def _split_large(self, sections: list[dict]) -> list[dict]:
        """Split sections larger than max_chunk_chars at paragraph boundaries."""
        result: list[dict] = []
        for section in sections:
            if len(section["content"]) <= self.max_chunk_chars:
                result.append(section)
                continue

            # Split at double-newline (paragraph boundaries)
            paragraphs = re.split(r"\n\n+", section["content"])
            current_parts: list[str] = []
            current_len = 0
            sub_start = section["line_start"]

            for para in paragraphs:
                para_len = len(para)
                if current_len + para_len > self.max_chunk_chars and current_parts:
                    # Flush current accumulation
                    chunk_content = "\n\n".join(current_parts)
                    line_count = chunk_content.count("\n") + 1
                    result.append({
                        "heading": section.get("heading") if not result or result[-1].get("heading") != section.get("heading") else None,
                        "heading_level": section.get("heading_level") if not result or result[-1].get("heading") != section.get("heading") else None,
                        "content": chunk_content,
                        "line_start": sub_start,
                        "line_end": sub_start + line_count - 1,
                    })
                    sub_start = sub_start + line_count + 1  # +1 for paragraph separator
                    current_parts = [para]
                    current_len = para_len
                else:
                    current_parts.append(para)
                    current_len += para_len + 2  # +2 for \n\n separator

            # Flush remaining
            if current_parts:
                chunk_content = "\n\n".join(current_parts)
                line_count = chunk_content.count("\n") + 1
                result.append({
                    "heading": section.get("heading") if not any(
                        r.get("heading") == section.get("heading") for r in result
                    ) else None,
                    "heading_level": section.get("heading_level") if not any(
                        r.get("heading") == section.get("heading") for r in result
                    ) else None,
                    "content": chunk_content,
                    "line_start": sub_start,
                    "line_end": sub_start + line_count - 1,
                })

        return result


class ParagraphChunker:
    """Fallback chunker for non-markdown content. Splits at paragraph boundaries."""

    def __init__(self, max_chunk_chars: int = _MAX_CHUNK_CHARS):
        self.max_chunk_chars = max_chunk_chars

    def chunk(self, content: str) -> list[ChunkResult]:
        if not content or not content.strip():
            return []

        paragraphs = re.split(r"\n\n+", content)
        results: list[ChunkResult] = []
        current_parts: list[str] = []
        current_len = 0
        line_offset = 1  # 1-indexed

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len > self.max_chunk_chars and current_parts:
                # Flush
                chunk_content = "\n\n".join(current_parts)
                line_count = chunk_content.count("\n") + 1
                results.append(ChunkResult(
                    chunk_index=len(results),
                    content=chunk_content,
                    line_start=line_offset,
                    line_end=line_offset + line_count - 1,
                ))
                line_offset += line_count + 1
                current_parts = [para]
                current_len = para_len
            else:
                current_parts.append(para)
                current_len += para_len + 2

        # Flush remaining
        if current_parts:
            chunk_content = "\n\n".join(current_parts)
            line_count = chunk_content.count("\n") + 1
            results.append(ChunkResult(
                chunk_index=len(results),
                content=chunk_content,
                line_start=line_offset,
                line_end=line_offset + line_count - 1,
            ))

        return results


def get_chunker(content_type: str = "text/markdown") -> ChunkingStrategy:
    """Factory: return the appropriate chunker for the content type."""
    if content_type in ("text/markdown", "text/x-markdown"):
        return MarkdownHeadingChunker()
    return ParagraphChunker()
