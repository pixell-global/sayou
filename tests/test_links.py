"""Tests for file relationships / knowledge graph."""

import tempfile

import pytest

from sayou import Workspace
from sayou.core.links import (
    extract_links_from_frontmatter,
    extract_links_from_markdown,
    resolve_relative_path,
)


# ── Unit tests: link extraction ──────────────────────────────────


def test_extract_wiki_links():
    """Detect [[wiki-style]] links."""
    content = "See [[docs/setup.md]] and also [[faq.md]] for details."
    links = extract_links_from_markdown(content)
    assert len(links) == 2
    assert links[0]["target_path"] == "docs/setup.md"
    assert links[1]["target_path"] == "faq.md"
    assert all(l["link_type"] == "reference" for l in links)


def test_extract_markdown_links():
    """Detect [text](path) links, excluding http URLs."""
    content = "Read the [guide](docs/guide.md) and visit [site](https://example.com)."
    links = extract_links_from_markdown(content)
    assert len(links) == 1
    assert links[0]["target_path"] == "docs/guide.md"


def test_extract_markdown_link_with_anchor():
    """Strip anchor from markdown links."""
    content = "See [section](docs/guide.md#setup) for details."
    links = extract_links_from_markdown(content)
    assert len(links) == 1
    assert links[0]["target_path"] == "docs/guide.md"


def test_extract_anchor_only_link_skipped():
    """Links to anchors only (#section) are skipped."""
    content = "See [above](#introduction) for context."
    links = extract_links_from_markdown(content)
    assert len(links) == 0


def test_extract_frontmatter_single():
    """Single string frontmatter field."""
    fm = {"related": "other.md"}
    links = extract_links_from_frontmatter(fm)
    assert len(links) == 1
    assert links[0]["target_path"] == "other.md"
    assert links[0]["link_type"] == "related"


def test_extract_frontmatter_list():
    """List of paths in frontmatter field."""
    fm = {"depends_on": ["a.md", "b.md"]}
    links = extract_links_from_frontmatter(fm)
    assert len(links) == 2
    assert links[0]["link_type"] == "depends_on"


def test_extract_frontmatter_multiple_fields():
    """Multiple relationship fields."""
    fm = {"related": "x.md", "supersedes": "old.md", "parent": "index.md"}
    links = extract_links_from_frontmatter(fm)
    assert len(links) == 3
    types = {l["link_type"] for l in links}
    assert types == {"related", "supersedes", "parent"}


def test_resolve_relative_path_simple():
    """Resolve relative path from source directory."""
    assert resolve_relative_path("docs/a.md", "b.md") == "docs/b.md"


def test_resolve_relative_path_parent():
    """Resolve .. path."""
    assert resolve_relative_path("docs/a.md", "../b.md") == "b.md"


def test_resolve_relative_path_absolute():
    """Absolute paths (starting with /) are returned as-is."""
    assert resolve_relative_path("docs/a.md", "/abs/d.md") == "abs/d.md"


def test_resolve_relative_path_subdirectory():
    """Resolve into subdirectory."""
    assert resolve_relative_path("docs/a.md", "sub/c.md") == "docs/sub/c.md"


def test_resolve_relative_path_root_file():
    """Resolve from root-level file."""
    assert resolve_relative_path("readme.md", "docs/guide.md") == "docs/guide.md"


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
async def test_auto_detect_wiki_links():
    """Writing a file with [[wiki-links]] auto-creates relationships."""
    async with _make_ws() as ws:
        await ws.write("index.md", "See [[docs/setup.md]] for setup.")
        result = await ws.links("index.md")
        assert len(result["outgoing"]) == 1
        assert result["outgoing"][0]["target_path"] == "docs/setup.md"
        assert result["outgoing"][0]["auto_detected"] is True


@pytest.mark.asyncio
async def test_auto_detect_markdown_links():
    """Markdown [text](path) links are auto-detected."""
    async with _make_ws() as ws:
        await ws.write("readme.md", "Read the [guide](docs/guide.md).")
        result = await ws.links("readme.md")
        assert len(result["outgoing"]) == 1
        assert result["outgoing"][0]["target_path"] == "docs/guide.md"


@pytest.mark.asyncio
async def test_auto_detect_frontmatter_links():
    """Frontmatter relationship fields create links."""
    async with _make_ws() as ws:
        content = "---\nrelated: other.md\ndepends_on:\n  - dep1.md\n  - dep2.md\n---\nBody"
        await ws.write("doc.md", content)
        result = await ws.links("doc.md")
        assert len(result["outgoing"]) == 3
        types = {l["link_type"] for l in result["outgoing"]}
        assert "related" in types
        assert "depends_on" in types


@pytest.mark.asyncio
async def test_incoming_links():
    """Check incoming links (backlinks)."""
    async with _make_ws() as ws:
        await ws.write("a.md", "See [[b.md]]")
        await ws.write("c.md", "Also see [[b.md]]")
        result = await ws.links("b.md")
        assert len(result["incoming"]) == 2
        sources = {l["source_path"] for l in result["incoming"]}
        assert sources == {"a.md", "c.md"}


@pytest.mark.asyncio
async def test_manual_link():
    """Manually add and remove a link."""
    async with _make_ws() as ws:
        await ws.write("a.md", "File A")
        await ws.write("b.md", "File B")

        result = await ws.add_link("a.md", "b.md", link_type="depends_on")
        assert result["created"] is True

        links = await ws.links("a.md")
        assert any(
            l["target_path"] == "b.md" and l["link_type"] == "depends_on"
            for l in links["outgoing"]
        )

        removed = await ws.remove_link("a.md", "b.md", link_type="depends_on")
        assert removed["deleted"] is True

        links2 = await ws.links("a.md")
        assert not any(
            l["target_path"] == "b.md" and l["link_type"] == "depends_on"
            for l in links2["outgoing"]
        )


@pytest.mark.asyncio
async def test_links_updated_on_rewrite():
    """Rewriting a file updates auto-detected links."""
    async with _make_ws() as ws:
        await ws.write("doc.md", "See [[old.md]]")
        r1 = await ws.links("doc.md")
        assert r1["outgoing"][0]["target_path"] == "old.md"

        await ws.write("doc.md", "Now see [[new.md]]")
        r2 = await ws.links("doc.md")
        assert len(r2["outgoing"]) == 1
        assert r2["outgoing"][0]["target_path"] == "new.md"


@pytest.mark.asyncio
async def test_links_deleted_on_file_delete():
    """Deleting a file removes its source links."""
    async with _make_ws() as ws:
        await ws.write("a.md", "See [[b.md]]")
        await ws.delete("a.md")
        # Source links from a.md should be gone
        # b.md should have no incoming from a.md
        result = await ws.links("b.md")
        assert len(result["incoming"]) == 0


@pytest.mark.asyncio
async def test_traverse_graph():
    """BFS traversal finds connected files."""
    async with _make_ws() as ws:
        await ws.write("a.md", "See [[b.md]]")
        await ws.write("b.md", "See [[c.md]]")
        await ws.write("c.md", "End")

        # Depth 1 from a: should find b
        r1 = await ws.traverse("a.md", depth=1)
        assert "b.md" in r1["nodes"]
        assert r1["node_count"] >= 2

        # Depth 2 from a: should find b and c
        r2 = await ws.traverse("a.md", depth=2)
        assert "c.md" in r2["nodes"]
        assert r2["node_count"] >= 3


@pytest.mark.asyncio
async def test_graph_summary():
    """Graph summary shows link counts and types."""
    async with _make_ws() as ws:
        await ws.write("a.md", "See [[b.md]]")
        await ws.write("c.md", "---\ndepends_on: d.md\n---\nBody")

        result = await ws.graph()
        assert result["total_links"] >= 2
        assert "reference" in result["link_types"]


@pytest.mark.asyncio
async def test_links_on_move():
    """Moving a file updates link paths."""
    async with _make_ws() as ws:
        await ws.write("a.md", "See [[b.md]]")
        await ws.write("b.md", "Target")

        # Move b.md to new-b.md
        await ws.move("b.md", "new-b.md")

        # Links should be updated
        result = await ws.links("a.md")
        targets = {l["target_path"] for l in result["outgoing"]}
        assert "new-b.md" in targets
