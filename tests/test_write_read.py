"""S1: Write-read cycle - byte identity, version=1, frontmatter parsed."""

import pytest


@pytest.mark.asyncio
async def test_write_read_with_frontmatter(workspace_service):
    content = """---
status: active
tags: [research, ai]
author: test-user
---
# Hello World

This is a test document.
"""
    result = await workspace_service.write(
        "test-org", "test-user", "default", "research/hello.md", content
    )
    assert result["path"] == "research/hello.md"
    assert result["version_number"] == 1
    assert result["size_bytes"] == len(content.encode("utf-8"))

    read_result = await workspace_service.read(
        "test-org", "test-user", "default", "research/hello.md"
    )
    assert read_result["content"] == content
    assert read_result["version_number"] == 1
    assert read_result["frontmatter"]["status"] == "active"
    assert read_result["frontmatter"]["tags"] == ["research", "ai"]
    assert read_result["frontmatter"]["author"] == "test-user"


@pytest.mark.asyncio
async def test_write_read_without_frontmatter(workspace_service):
    content = "# Just a plain markdown file\n\nNo frontmatter here."
    result = await workspace_service.write(
        "test-org", "test-user", "default", "notes/plain.md", content
    )
    assert result["version_number"] == 1

    read_result = await workspace_service.read(
        "test-org", "test-user", "default", "notes/plain.md"
    )
    assert read_result["content"] == content
    assert read_result["frontmatter"] == {}


@pytest.mark.asyncio
async def test_write_empty_content(workspace_service):
    result = await workspace_service.write(
        "test-org", "test-user", "default", "empty.md", ""
    )
    assert result["version_number"] == 1
    assert result["size_bytes"] == 0

    read_result = await workspace_service.read(
        "test-org", "test-user", "default", "empty.md"
    )
    assert read_result["content"] == ""


@pytest.mark.asyncio
async def test_write_read_byte_identity(workspace_service):
    """Content read back must be byte-identical to what was written."""
    content = "---\ntitle: Test\n---\nLine 1\nLine 2\n  indented\n\ttabbed\n"
    await workspace_service.write(
        "test-org", "test-user", "default", "identity.md", content
    )
    read_result = await workspace_service.read(
        "test-org", "test-user", "default", "identity.md"
    )
    assert read_result["content"].encode("utf-8") == content.encode("utf-8")


@pytest.mark.asyncio
async def test_read_with_token_budget_truncation(workspace_service):
    # Create content larger than budget * 4 chars
    content = "x" * 5000  # 5000 chars, budget=1 means 4 char limit
    await workspace_service.write(
        "test-org", "test-user", "default", "big.md", content
    )
    read_result = await workspace_service.read(
        "test-org", "test-user", "default", "big.md", token_budget=1
    )
    assert read_result["truncated"] is True
    assert len(read_result["content"]) == 4


@pytest.mark.asyncio
async def test_recursive_listing(workspace_service):
    """Recursive listing returns files at all depths under a folder."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/trends/q1.md", "---\ntitle: Q1\n---\nQ1 trends"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/trends/q2.md", "---\ntitle: Q2\n---\nQ2 trends"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/competitors/acme.md", "---\ntitle: Acme\n---\nAcme analysis"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "notes/todo.md", "---\ntitle: Todo\n---\nTodo list"
    )

    # Recursive under research/
    result = await workspace_service.list_folder(
        "test-org", "test-user", "default", "research", recursive=True
    )
    paths = {f["path"] for f in result["files"]}
    assert "research/trends/q1.md" in paths
    assert "research/trends/q2.md" in paths
    assert "research/competitors/acme.md" in paths
    assert "notes/todo.md" not in paths
    assert result["file_count"] == 3


@pytest.mark.asyncio
async def test_recursive_listing_root(workspace_service):
    """Recursive listing from root returns all files."""
    await workspace_service.write(
        "test-org", "test-user", "default", "readme.md", "Root file"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/guide.md", "Guide"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/deep/nested.md", "Nested"
    )

    result = await workspace_service.list_folder(
        "test-org", "test-user", "default", "/", recursive=True
    )
    paths = {f["path"] for f in result["files"]}
    assert "readme.md" in paths
    assert "docs/guide.md" in paths
    assert "docs/deep/nested.md" in paths


@pytest.mark.asyncio
async def test_version_specific_read(workspace_service):
    """Reading a specific version returns that version's content."""
    content_v1 = "---\ntitle: Draft\n---\nFirst draft"
    content_v2 = "---\ntitle: Final\n---\nFinal version"

    await workspace_service.write(
        "test-org", "test-user", "default", "doc.md", content_v1
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "doc.md", content_v2
    )

    # Read latest (v2)
    latest = await workspace_service.read(
        "test-org", "test-user", "default", "doc.md"
    )
    assert latest["version_number"] == 2
    assert latest["content"] == content_v2

    # Read specific version (v1)
    v1 = await workspace_service.read(
        "test-org", "test-user", "default", "doc.md", version_number=1
    )
    assert v1["version_number"] == 1
    assert v1["content"] == content_v1


@pytest.mark.asyncio
async def test_version_specific_read_not_found(workspace_service):
    """Reading a non-existent version raises FileNotFoundError."""
    from sayou.core.workspace import FileNotFoundError as WsFileNotFoundError

    await workspace_service.write(
        "test-org", "test-user", "default", "doc.md", "content"
    )

    with pytest.raises(WsFileNotFoundError):
        await workspace_service.read(
            "test-org", "test-user", "default", "doc.md", version_number=99
        )
