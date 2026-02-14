"""Tests for the public Workspace API."""

import tempfile

import pytest

from sayou import Workspace, FileNotFoundError


def _make_ws(**kwargs) -> Workspace:
    """Create a Workspace with in-memory SQLite and temp local storage."""
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
async def test_zero_config_write_read():
    """Workspace() with defaults: write + read cycle."""
    async with _make_ws() as ws:
        result = await ws.write("hello.md", "# Hello")
        assert result["path"] == "hello.md"
        assert result["version_number"] == 1

        data = await ws.read("hello.md")
        assert data["content"] == "# Hello"
        assert data["version_number"] == 1


@pytest.mark.asyncio
async def test_context_manager():
    """async with Workspace() as ws: opens and closes cleanly."""
    ws = _make_ws()
    assert not ws._opened
    async with ws:
        assert ws._opened
        await ws.write("test.md", "content")
    assert not ws._opened


@pytest.mark.asyncio
async def test_lazy_init():
    """Calling write() without explicit open() works via lazy init."""
    ws = _make_ws()
    assert not ws._opened
    result = await ws.write("lazy.md", "lazy content")
    assert result["path"] == "lazy.md"
    assert ws._opened
    await ws.close()


@pytest.mark.asyncio
async def test_identity_binding():
    """org_id/user_id set once, not per call."""
    async with _make_ws(org_id="my-org", user_id="agent-1") as ws:
        await ws.write("bound.md", "identity test")
        data = await ws.read("bound.md")
        assert data["content"] == "identity test"


@pytest.mark.asyncio
async def test_write_creates_versions():
    """Multiple writes create incrementing versions."""
    async with _make_ws() as ws:
        r1 = await ws.write("versioned.md", "v1")
        assert r1["version_number"] == 1

        r2 = await ws.write("versioned.md", "v2")
        assert r2["version_number"] == 2


@pytest.mark.asyncio
async def test_version_specific_read():
    """read(path, version=1) returns the first version."""
    async with _make_ws() as ws:
        await ws.write("multi.md", "first")
        await ws.write("multi.md", "second")

        v1 = await ws.read("multi.md", version=1)
        assert v1["content"] == "first"
        assert v1["version_number"] == 1

        latest = await ws.read("multi.md")
        assert latest["content"] == "second"
        assert latest["version_number"] == 2


@pytest.mark.asyncio
async def test_list():
    """list() returns files in a folder."""
    async with _make_ws() as ws:
        await ws.write("docs/a.md", "a")
        await ws.write("docs/b.md", "b")
        await ws.write("other.md", "other")

        result = await ws.list("docs/")
        assert result["file_count"] == 2
        paths = [f["path"] for f in result["files"]]
        assert "docs/a.md" in paths
        assert "docs/b.md" in paths


@pytest.mark.asyncio
async def test_list_recursive():
    """list(recursive=True) returns nested files."""
    async with _make_ws() as ws:
        await ws.write("a/b/deep.md", "deep")
        await ws.write("a/top.md", "top")

        result = await ws.list("a/", recursive=True)
        paths = [f["path"] for f in result["files"]]
        assert "a/b/deep.md" in paths
        assert "a/top.md" in paths


@pytest.mark.asyncio
async def test_glob():
    """glob() matches files by pattern."""
    async with _make_ws() as ws:
        await ws.write("src/main.py", "print('hi')")
        await ws.write("src/utils.py", "def util(): pass")
        await ws.write("readme.md", "# Readme")

        result = await ws.glob("src/*.py")
        assert result["total"] == 2
        paths = [f["path"] for f in result["files"]]
        assert "src/main.py" in paths
        assert "src/utils.py" in paths


@pytest.mark.asyncio
async def test_grep():
    """grep() searches file content."""
    async with _make_ws() as ws:
        await ws.write("notes.md", "The quick brown fox")
        await ws.write("other.md", "Nothing here")

        result = await ws.grep("quick brown")
        assert result["total_files"] == 1
        assert result["results"][0]["path"] == "notes.md"


@pytest.mark.asyncio
async def test_search_by_frontmatter():
    """search(filters=...) queries by frontmatter."""
    async with _make_ws() as ws:
        await ws.write("active.md", "---\nstatus: active\n---\nActive file")
        await ws.write("draft.md", "---\nstatus: draft\n---\nDraft file")

        result = await ws.search(filters={"status": "active"})
        assert result["total"] == 1
        assert result["results"][0]["path"] == "active.md"


@pytest.mark.asyncio
async def test_search_fulltext():
    """search(query=...) queries by full-text."""
    async with _make_ws() as ws:
        await ws.write("target.md", "unique-keyword-xyz")
        await ws.write("other.md", "nothing special")

        result = await ws.search(query="unique-keyword-xyz")
        assert result["total"] == 1
        assert result["results"][0]["path"] == "target.md"


@pytest.mark.asyncio
async def test_delete():
    """delete() soft-deletes a file."""
    async with _make_ws() as ws:
        await ws.write("doomed.md", "bye")
        result = await ws.delete("doomed.md")
        assert result["deleted"] is True

        with pytest.raises(FileNotFoundError):
            await ws.read("doomed.md")


@pytest.mark.asyncio
async def test_history():
    """history() returns version list."""
    async with _make_ws() as ws:
        await ws.write("hist.md", "v1")
        await ws.write("hist.md", "v2")
        await ws.write("hist.md", "v3")

        result = await ws.history("hist.md")
        assert result["total"] == 3
        version_numbers = [v["version_number"] for v in result["versions"]]
        assert 1 in version_numbers
        assert 2 in version_numbers
        assert 3 in version_numbers


@pytest.mark.asyncio
async def test_custom_database_url_isolation():
    """Different database_urls are isolated."""
    async with _make_ws(database_url="sqlite+aiosqlite://") as ws1:
        await ws1.write("shared-name.md", "from ws1")

    async with _make_ws(database_url="sqlite+aiosqlite://") as ws2:
        with pytest.raises(FileNotFoundError):
            await ws2.read("shared-name.md")


@pytest.mark.asyncio
async def test_source_binding():
    """source parameter is passed through to mutations."""
    async with _make_ws(source="my-agent") as ws:
        result = await ws.write("sourced.md", "content")
        assert result["path"] == "sourced.md"


@pytest.mark.asyncio
async def test_frontmatter_parsing():
    """Frontmatter is parsed and returned on read."""
    async with _make_ws() as ws:
        content = "---\ntitle: Test\npriority: high\n---\n# Body"
        await ws.write("fm.md", content)

        data = await ws.read("fm.md")
        assert data["frontmatter"]["title"] == "Test"
        assert data["frontmatter"]["priority"] == "high"
