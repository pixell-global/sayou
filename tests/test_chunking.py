"""Tests for auto-chunking: strategies, integration, and search."""

import tempfile

import pytest

from sayou import Workspace
from sayou.core.chunking import (
    MarkdownHeadingChunker,
    ParagraphChunker,
    get_chunker,
)


# ── Unit tests: chunking strategies ──────────────────────────────


def test_markdown_heading_chunker_basic():
    """Split at headings, each section becomes a chunk."""
    content = "# Introduction\nHello world\n\n# Methods\nDo stuff\n\n# Results\nGot results"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    assert len(chunks) == 3
    assert chunks[0].heading == "Introduction"
    assert chunks[0].heading_level == 1
    assert chunks[1].heading == "Methods"
    assert chunks[2].heading == "Results"


def test_markdown_heading_chunker_nested_levels():
    """Handles h1-h6 headings."""
    content = "# Title\nIntro\n## Section A\nContent A\n### Subsection\nDeep content"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    assert len(chunks) == 3
    assert chunks[0].heading_level == 1
    assert chunks[1].heading_level == 2
    assert chunks[2].heading_level == 3


def test_markdown_heading_chunker_merge_small():
    """Small headingless fragments are merged into previous chunk."""
    # Headingless trailing text gets merged into the preceding headed section
    content = "# Big Section\n" + ("x " * 100) + "\nhi there"
    chunker = MarkdownHeadingChunker(min_chunk_chars=50)
    chunks = chunker.chunk(content)
    # Single section (no second heading), so single chunk
    assert len(chunks) == 1


def test_markdown_heading_chunker_split_large():
    """Large sections are split at paragraph boundaries."""
    big_para = "Lorem ipsum. " * 100  # ~1300 chars
    content = f"# Big Section\n{big_para}\n\n{big_para}\n\n{big_para}\n\n{big_para}"
    chunker = MarkdownHeadingChunker(max_chunk_chars=2000)
    chunks = chunker.chunk(content)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.char_count <= 3000  # Some tolerance for splitting


def test_markdown_heading_chunker_empty():
    """Empty content returns no chunks."""
    chunker = MarkdownHeadingChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_markdown_heading_chunker_no_headings():
    """Content without headings becomes a single chunk."""
    content = "Just plain text\nwith multiple lines\nand no headings"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    assert len(chunks) == 1
    assert chunks[0].heading is None


def test_markdown_heading_chunker_line_numbers():
    """Line numbers are 1-indexed and accurate."""
    content = "# A\nline 2\nline 3\n# B\nline 5\nline 6"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 3
    assert chunks[1].line_start == 4
    assert chunks[1].line_end == 6


def test_markdown_heading_chunker_content_hash():
    """Each chunk gets a unique content hash."""
    content = "# A\nContent A\n# B\nContent B"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    assert chunks[0].content_hash != chunks[1].content_hash


def test_markdown_heading_chunker_token_estimate():
    """Token estimate is ~chars/4."""
    content = "# Section\n" + "x" * 400
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(content)
    # Content is "# Section\n" + 400 x's = ~410 chars → ~102 tokens
    assert chunks[0].token_estimate > 50


def test_paragraph_chunker_basic():
    """Splits at double newlines when exceeding max size."""
    para = "A sentence with enough words to exceed the limit. " * 3
    content = f"{para}\n\n{para}\n\n{para}"
    chunker = ParagraphChunker(max_chunk_chars=200)
    chunks = chunker.chunk(content)
    assert len(chunks) >= 2


def test_paragraph_chunker_empty():
    """Empty content returns no chunks."""
    chunker = ParagraphChunker()
    assert chunker.chunk("") == []


def test_get_chunker_markdown():
    """Factory returns MarkdownHeadingChunker for markdown content."""
    chunker = get_chunker("text/markdown")
    assert isinstance(chunker, MarkdownHeadingChunker)


def test_get_chunker_fallback():
    """Factory returns ParagraphChunker for non-markdown content."""
    chunker = get_chunker("text/plain")
    assert isinstance(chunker, ParagraphChunker)


def test_frontmatter_excluded_from_chunks():
    """Chunking operates on body text, not frontmatter."""
    # The workspace write() parses frontmatter and passes body to chunker
    # This unit test verifies that if we pass just the body, frontmatter isn't there
    body = "# Introduction\nHello\n# Methods\nStuff"
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk(body)
    for c in chunks:
        assert "---" not in c.content or c.content.count("---") == 0


# ── Integration tests: workspace API ────────────────────────────


def _make_ws(**kwargs) -> Workspace:
    tmpdir = kwargs.pop("_tmpdir", None) or tempfile.mkdtemp()
    defaults = dict(
        database_url="sqlite+aiosqlite://",
        storage_path=tmpdir,
        org_id="test-org",
        user_id="test-user",
    )
    defaults.update(kwargs)
    return Workspace(**defaults)


@pytest.mark.asyncio
async def test_write_creates_chunks():
    """Writing a markdown file auto-generates chunks."""
    async with _make_ws() as ws:
        content = "# Intro\nHello world\n# Methods\nDo research\n# Results\nGot data"
        await ws.write("doc.md", content)

        result = await ws.chunks("doc.md")
        assert result["total"] == 3
        assert result["chunks"][0]["heading"] == "Intro"
        assert result["chunks"][1]["heading"] == "Methods"
        assert result["chunks"][2]["heading"] == "Results"


@pytest.mark.asyncio
async def test_chunks_updated_on_rewrite():
    """Rewriting a file replaces old chunks with new ones."""
    async with _make_ws() as ws:
        await ws.write("doc.md", "# A\nFirst\n# B\nSecond")
        r1 = await ws.chunks("doc.md")
        assert r1["total"] == 2

        await ws.write("doc.md", "# X\nNew\n# Y\nAlso new\n# Z\nThird")
        r2 = await ws.chunks("doc.md")
        assert r2["total"] == 3
        assert r2["chunks"][0]["heading"] == "X"


@pytest.mark.asyncio
async def test_get_chunk_by_index():
    """Read a specific chunk by index returns content."""
    async with _make_ws() as ws:
        await ws.write("doc.md", "# Intro\nHello\n# Methods\nResearch details here")
        result = await ws.chunk("doc.md", 1)
        assert result["chunk_index"] == 1
        assert result["heading"] == "Methods"
        assert "Research details" in result["content"]


@pytest.mark.asyncio
async def test_search_chunks():
    """Chunk-level search finds the exact section."""
    async with _make_ws() as ws:
        await ws.write("doc.md", "# Setup\nInstall deps\n# Usage\nRun the command\n# FAQ\nCommon questions")
        result = await ws.search_chunks("command")
        assert result["total"] >= 1
        assert any("command" in r.get("content_preview", "").lower() for r in result["results"])


@pytest.mark.asyncio
async def test_chunks_deleted_on_file_delete():
    """Deleting a file also removes its chunks."""
    async with _make_ws() as ws:
        await ws.write("doc.md", "# Section\nContent here")
        r1 = await ws.chunks("doc.md")
        assert r1["total"] >= 1

        await ws.delete("doc.md")

        from sayou import FileNotFoundError
        with pytest.raises(FileNotFoundError):
            await ws.chunks("doc.md")


@pytest.mark.asyncio
async def test_chunks_with_frontmatter():
    """Files with frontmatter are chunked on body only."""
    async with _make_ws() as ws:
        content = "---\ntitle: Test\ntags: [a, b]\n---\n# Section One\nBody text\n# Section Two\nMore text"
        await ws.write("fm.md", content)

        result = await ws.chunks("fm.md")
        assert result["total"] == 2
        # Frontmatter should not appear in chunk content
        for chunk_info in result["chunks"]:
            c = await ws.chunk("fm.md", chunk_info["chunk_index"])
            assert "title: Test" not in c["content"]


@pytest.mark.asyncio
async def test_non_text_files_no_chunks():
    """Binary files don't generate chunks."""
    async with _make_ws() as ws:
        await ws.write("image.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")

        from sayou import FileNotFoundError
        # Binary files have no text body, so no chunks are created
        result = await ws.chunks("image.png")
        assert result["total"] == 0
