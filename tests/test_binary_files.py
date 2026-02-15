"""Test binary file support (Gap 9).

Verifies that binary files (images, PDFs, etc.) can be written, read,
and listed correctly. Binary content is stored as raw bytes and returned
as base64 on read.
"""

import base64

import pytest


@pytest.mark.asyncio
async def test_write_binary_file(workspace_service):
    """Write binary content with explicit content_type."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Create a small "PNG" (fake binary data)
    binary_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    result = await svc.write(
        org, user, slug, "images/logo.png", binary_data,
        content_type="image/png",
    )

    assert result["path"] == "images/logo.png"
    assert result["version_number"] == 1
    assert result["size_bytes"] == len(binary_data)
    assert result["content_type"] == "image/png"


@pytest.mark.asyncio
async def test_read_binary_file_returns_base64(workspace_service):
    """Read binary file returns base64-encoded content."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    binary_data = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    await svc.write(
        org, user, slug, "images/photo.png", binary_data,
        content_type="image/png",
    )

    result = await svc.read(org, user, slug, "images/photo.png")
    assert result["content_type"] == "image/png"
    assert result["encoding"] == "base64"
    assert result["truncated"] is False

    # Decode and verify roundtrip
    decoded = base64.b64decode(result["content"])
    assert decoded == binary_data


@pytest.mark.asyncio
async def test_binary_file_auto_detect_content_type(workspace_service):
    """Content type is auto-detected from file extension."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Write with bytes but no explicit content_type
    binary_data = b"fake pdf content"
    result = await svc.write(
        org, user, slug, "docs/report.pdf", binary_data,
    )
    assert result["content_type"] == "application/pdf"

    # JPEG
    jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50
    result = await svc.write(
        org, user, slug, "images/pic.jpg", jpeg_data,
    )
    assert result["content_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_binary_file_no_frontmatter_parsing(workspace_service):
    """Binary files skip frontmatter parsing."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Binary data that starts with "---" (would look like frontmatter)
    binary_data = b"---\ntitle: fake\n---\nbinary stuff"
    await svc.write(
        org, user, slug, "data/file.bin", binary_data,
        content_type="application/octet-stream",
    )

    result = await svc.read(org, user, slug, "data/file.bin")
    assert result["frontmatter"] == {}
    assert result["encoding"] == "base64"


@pytest.mark.asyncio
async def test_binary_file_in_listing(workspace_service):
    """Binary files appear in folder listings."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Write a mix of text and binary files
    await svc.write(org, user, slug, "mix/readme.md", "# Hello")
    await svc.write(
        org, user, slug, "mix/logo.png", b"\x89PNG\r\n\x1a\n",
        content_type="image/png",
    )

    listing = await svc.list_folder(org, user, slug, "mix")
    assert listing["file_count"] == 2
    filenames = {f["filename"] for f in listing["files"]}
    assert filenames == {"readme.md", "logo.png"}


@pytest.mark.asyncio
async def test_binary_file_version_history(workspace_service):
    """Binary files support versioning."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    v1_data = b"version 1 binary"
    v2_data = b"version 2 binary updated"
    await svc.write(
        org, user, slug, "assets/data.bin", v1_data,
        content_type="application/octet-stream",
    )
    await svc.write(
        org, user, slug, "assets/data.bin", v2_data,
        content_type="application/octet-stream",
    )

    history = await svc.history(org, user, slug, "assets/data.bin")
    assert history["total"] == 2

    # Read v1
    v1_result = await svc.read(org, user, slug, "assets/data.bin", version_number=1)
    assert base64.b64decode(v1_result["content"]) == v1_data

    # Read latest (v2)
    v2_result = await svc.read(org, user, slug, "assets/data.bin")
    assert base64.b64decode(v2_result["content"]) == v2_data


@pytest.mark.asyncio
async def test_text_file_still_returns_utf8(workspace_service):
    """Text files continue to return UTF-8 string content (not base64)."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    await svc.write(org, user, slug, "docs/note.md", "# Plain text\n")
    result = await svc.read(org, user, slug, "docs/note.md")

    assert result["content"] == "# Plain text\n"
    assert result["content_type"] == "text/markdown"
    assert "encoding" not in result or result.get("encoding") is None


@pytest.mark.asyncio
async def test_binary_file_move_copy(workspace_service):
    """Binary files can be moved and copied."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    binary_data = b"\x89PNG" + b"\x42" * 50
    await svc.write(
        org, user, slug, "assets/original.png", binary_data,
        content_type="image/png",
    )

    # Copy
    await svc.copy(org, user, slug, "assets/original.png", "assets/copy.png")
    copy_result = await svc.read(org, user, slug, "assets/copy.png")
    assert base64.b64decode(copy_result["content"]) == binary_data

    # Move
    await svc.move(org, user, slug, "assets/original.png", "assets/moved.png")
    moved_result = await svc.read(org, user, slug, "assets/moved.png")
    assert base64.b64decode(moved_result["content"]) == binary_data
