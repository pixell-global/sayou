"""Test diff tool (Gap 5)."""

import pytest

from sayou.core.workspace import FileNotFoundError as WsFileNotFoundError


@pytest.mark.asyncio
async def test_diff_shows_changes(workspace_service):
    """Diff between two versions shows additions and removals."""
    v1 = "---\ntitle: Draft\n---\n# Hello\n\nFirst version.\n"
    v2 = "---\ntitle: Final\n---\n# Hello\n\nSecond version with changes.\n"

    await workspace_service.write("test-org", "test-user", "default", "doc.md", v1)
    await workspace_service.write("test-org", "test-user", "default", "doc.md", v2)

    result = await workspace_service.diff(
        "test-org", "test-user", "default", "doc.md", 1, 2
    )
    assert result["has_changes"] is True
    assert result["path"] == "doc.md"
    assert result["version_a"] == 1
    assert result["version_b"] == 2
    # Unified diff should contain +/- lines
    assert "-" in result["diff"]
    assert "+" in result["diff"]
    assert "Draft" in result["diff"]
    assert "Final" in result["diff"]


@pytest.mark.asyncio
async def test_diff_identical_versions(workspace_service):
    """Diff of a version with itself returns empty."""
    await workspace_service.write(
        "test-org", "test-user", "default", "same.md", "Same content"
    )

    result = await workspace_service.diff(
        "test-org", "test-user", "default", "same.md", 1, 1
    )
    assert result["has_changes"] is False
    assert result["diff"] == ""


@pytest.mark.asyncio
async def test_diff_nonexistent_version(workspace_service):
    """Diff with a non-existent version raises error."""
    await workspace_service.write(
        "test-org", "test-user", "default", "doc.md", "content"
    )

    with pytest.raises(WsFileNotFoundError):
        await workspace_service.diff(
            "test-org", "test-user", "default", "doc.md", 1, 99
        )


@pytest.mark.asyncio
async def test_diff_nonexistent_file(workspace_service):
    """Diff on a non-existent file raises error."""
    with pytest.raises(WsFileNotFoundError):
        await workspace_service.diff(
            "test-org", "test-user", "default", "nope.md", 1, 2
        )


@pytest.mark.asyncio
async def test_diff_three_versions(workspace_service):
    """Diff works correctly across three versions."""
    await workspace_service.write(
        "test-org", "test-user", "default", "evolving.md", "Line 1\nLine 2\n"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "evolving.md", "Line 1\nLine 2 modified\n"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "evolving.md",
        "Line 1\nLine 2 modified\nLine 3 added\n"
    )

    # Diff v1 vs v3
    result = await workspace_service.diff(
        "test-org", "test-user", "default", "evolving.md", 1, 3
    )
    assert result["has_changes"] is True
    assert "Line 3 added" in result["diff"]

    # Diff v2 vs v3
    result23 = await workspace_service.diff(
        "test-org", "test-user", "default", "evolving.md", 2, 3
    )
    assert result23["has_changes"] is True
    assert "Line 3 added" in result23["diff"]
