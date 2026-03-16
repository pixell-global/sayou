"""Tests for WorkspaceService.get_context() — session start context assembly."""

from datetime import datetime, timezone

import pytest


ORG = "test-org"
USER = "test-user"
SLUG = "default"


@pytest.mark.asyncio
async def test_empty_workspace(workspace_service):
    """Empty workspace returns empty preferences, recent_files, zero activity."""
    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert result["preferences"] == []
    assert result["recent_files"] == []
    assert result["activity"] == {"today": 0, "yesterday": 0}
    assert result["file_count"] == 0


@pytest.mark.asyncio
async def test_with_preferences(workspace_service):
    """Preferences files are returned with content."""
    content = "---\ntype: preference\n---\nAlways use dark mode"
    await workspace_service.write(ORG, USER, SLUG, "preferences/coding-style.md", content)

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert len(result["preferences"]) == 1
    pref = result["preferences"][0]
    assert pref["path"] == "preferences/coding-style.md"
    assert "Always use dark mode" in pref["content"]
    assert pref["frontmatter"]["type"] == "preference"


@pytest.mark.asyncio
async def test_multiple_preferences(workspace_service):
    """Multiple preference files are all returned."""
    await workspace_service.write(
        ORG, USER, SLUG, "preferences/style.md",
        "---\ntype: preference\n---\nUse tabs not spaces"
    )
    await workspace_service.write(
        ORG, USER, SLUG, "preferences/conventions.md",
        "---\ntype: preference\n---\nPEP 8 always"
    )
    await workspace_service.write(
        ORG, USER, SLUG, "preferences/tools.md",
        "---\ntype: preference\n---\nPrefer ruff over flake8"
    )

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert len(result["preferences"]) == 3
    paths = {p["path"] for p in result["preferences"]}
    assert "preferences/style.md" in paths
    assert "preferences/conventions.md" in paths
    assert "preferences/tools.md" in paths


@pytest.mark.asyncio
async def test_recent_files_filtering(workspace_service):
    """Recent files excludes activity/, sessions/, and preferences/ folders."""
    await workspace_service.write(ORG, USER, SLUG, "notes/idea.md", "An idea")
    await workspace_service.write(ORG, USER, SLUG, "research/topic.md", "Research")
    await workspace_service.write(ORG, USER, SLUG, "activity/2026-02-23.md", "- 10:00 did stuff")
    await workspace_service.write(ORG, USER, SLUG, "sessions/abc.md", "Session log")
    await workspace_service.write(ORG, USER, SLUG, "preferences/style.md", "Style pref")

    result = await workspace_service.get_context(ORG, USER, SLUG)

    recent_paths = {f["path"] for f in result["recent_files"]}
    assert "notes/idea.md" in recent_paths
    assert "research/topic.md" in recent_paths
    assert "activity/2026-02-23.md" not in recent_paths
    assert "sessions/abc.md" not in recent_paths
    assert "preferences/style.md" not in recent_paths


@pytest.mark.asyncio
async def test_file_count_includes_all(workspace_service):
    """file_count includes all files (even activity/sessions/preferences)."""
    await workspace_service.write(ORG, USER, SLUG, "notes/a.md", "A")
    await workspace_service.write(ORG, USER, SLUG, "notes/b.md", "B")
    await workspace_service.write(ORG, USER, SLUG, "activity/today.md", "- 10:00 x")
    await workspace_service.write(ORG, USER, SLUG, "preferences/p.md", "pref")

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert result["file_count"] == 4


@pytest.mark.asyncio
async def test_activity_counting(workspace_service):
    """Activity entries are counted correctly."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    activity_content = (
        "# Activity Log\n\n"
        "- 09:15 Started coding\n"
        "- 10:30 Fixed a bug\n"
        "- 14:00 Reviewed PR\n"
        "Some other text\n"
    )
    await workspace_service.write(
        ORG, USER, SLUG, f"activity/{today_str}.md", activity_content
    )

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert result["activity"]["today"] == 3


@pytest.mark.asyncio
async def test_resilience_missing_preferences(workspace_service):
    """Missing preferences/ folder doesn't crash — returns empty list."""
    await workspace_service.write(ORG, USER, SLUG, "notes/hello.md", "Hello")

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert result["preferences"] == []
    assert len(result["recent_files"]) == 1


@pytest.mark.asyncio
async def test_recent_files_have_metadata(workspace_service):
    """Recent files include frontmatter, version, and updated_at."""
    content = "---\nstatus: active\ntopic: ai\n---\n# Research"
    await workspace_service.write(ORG, USER, SLUG, "research/ai.md", content)
    # Overwrite to get version 2
    await workspace_service.write(ORG, USER, SLUG, "research/ai.md", content + "\nMore text")

    result = await workspace_service.get_context(ORG, USER, SLUG)

    assert len(result["recent_files"]) == 1
    f = result["recent_files"][0]
    assert f["path"] == "research/ai.md"
    assert f["frontmatter"]["status"] == "active"
    assert f["version"] == 2
    assert f["updated_at"] is not None
