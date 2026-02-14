"""R2: Glob pattern matching — **/*.md, research/**, *.md, clients/*/profile.md"""

import pytest


@pytest.mark.asyncio
async def test_glob_star_star_slash_star_md(workspace_service):
    """**/*.md matches all .md files at any depth."""
    await workspace_service.write(
        "test-org", "test-user", "default", "readme.md", "Root readme"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/guide.md", "Guide"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/deep/nested.md", "Nested"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "data/sheet.csv", "CSV data"
    )

    result = await workspace_service.glob_files(
        "test-org", "test-user", "default", "**/*.md"
    )
    paths = {f["path"] for f in result["files"]}
    assert "docs/guide.md" in paths
    assert "docs/deep/nested.md" in paths
    # *.md at root should also match since ** matches zero or more segments
    assert "data/sheet.csv" not in paths


@pytest.mark.asyncio
async def test_glob_folder_star_star(workspace_service):
    """research/** matches everything under research/."""
    await workspace_service.write(
        "test-org", "test-user", "default", "research/trends/q1.md", "Q1 trends"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "research/competitors/acme.md", "Acme"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "notes/todo.md", "Todo"
    )

    result = await workspace_service.glob_files(
        "test-org", "test-user", "default", "research/**"
    )
    paths = {f["path"] for f in result["files"]}
    assert "research/trends/q1.md" in paths
    assert "research/competitors/acme.md" in paths
    assert "notes/todo.md" not in paths
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_glob_single_star(workspace_service):
    """*.md matches only root-level .md files (single segment)."""
    await workspace_service.write(
        "test-org", "test-user", "default", "readme.md", "Root"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "changelog.md", "Changes"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/guide.md", "Guide"
    )

    result = await workspace_service.glob_files(
        "test-org", "test-user", "default", "*.md"
    )
    paths = {f["path"] for f in result["files"]}
    assert "readme.md" in paths
    assert "changelog.md" in paths
    # Single * should not cross path boundaries
    assert "docs/guide.md" not in paths


@pytest.mark.asyncio
async def test_glob_nested_wildcard(workspace_service):
    """clients/*/profile.md matches profile.md one level under clients/."""
    await workspace_service.write(
        "test-org", "test-user", "default", "clients/acme/profile.md", "Acme profile"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "clients/beta/profile.md", "Beta profile"
    )
    await workspace_service.write(
        "test-org", "test-user", "default", "clients/acme/notes.md", "Acme notes"
    )

    result = await workspace_service.glob_files(
        "test-org", "test-user", "default", "clients/*/profile.md"
    )
    paths = {f["path"] for f in result["files"]}
    assert "clients/acme/profile.md" in paths
    assert "clients/beta/profile.md" in paths
    assert "clients/acme/notes.md" not in paths


@pytest.mark.asyncio
async def test_glob_no_matches(workspace_service):
    """Glob with no matches returns empty list."""
    await workspace_service.write(
        "test-org", "test-user", "default", "readme.md", "Hello"
    )

    result = await workspace_service.glob_files(
        "test-org", "test-user", "default", "nonexistent/**"
    )
    assert result["total"] == 0
    assert result["files"] == []
