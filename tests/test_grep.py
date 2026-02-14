"""R2: Grep — search file body content, return matching lines with context."""

import pytest


@pytest.mark.asyncio
async def test_grep_finds_unique_phrase(workspace_service):
    """Grep finds a unique phrase in file body content."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/alpha.md",
        "---\nstatus: active\n---\n# Alpha Report\n\nThe market is growing rapidly.\nCompetitor X launched a new product.\n",
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/beta.md",
        "---\nstatus: draft\n---\n# Beta Report\n\nCustomer sentiment is positive.\nNo major competitors noted.\n",
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "growing rapidly"
    )
    assert result["total_files"] == 1
    assert result["results"][0]["path"] == "research/alpha.md"
    assert result["results"][0]["match_count"] == 1


@pytest.mark.asyncio
async def test_grep_context_lines(workspace_service):
    """Grep returns surrounding context lines."""
    content = "---\ntitle: Test\n---\nLine 1\nLine 2\nLine 3 TARGET_PHRASE here\nLine 4\nLine 5\nLine 6\n"
    await workspace_service.write(
        "test-org", "test-user", "default", "docs/context.md", content
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "TARGET_PHRASE", context_lines=2
    )
    assert result["total_files"] == 1
    context = result["results"][0]["matches"][0]["context"]
    # Should contain context lines
    assert "Line 2" in context
    assert "TARGET_PHRASE" in context
    assert "Line 4" in context


@pytest.mark.asyncio
async def test_grep_multiple_matches_in_file(workspace_service):
    """Grep finds multiple matches within the same file."""
    content = "---\ntitle: Multi\n---\nFirst KEYWORD here\nSome other text\nSecond KEYWORD there\n"
    await workspace_service.write(
        "test-org", "test-user", "default", "multi.md", content
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "KEYWORD"
    )
    assert result["total_files"] == 1
    assert result["results"][0]["match_count"] == 2


@pytest.mark.asyncio
async def test_grep_across_multiple_files(workspace_service):
    """Grep finds matches across multiple files."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "a.md", "---\ntitle: A\n---\nShared term appears here"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "b.md", "---\ntitle: B\n---\nShared term also here"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "c.md", "---\ntitle: C\n---\nNo match in this file"
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "Shared term"
    )
    assert result["total_files"] == 2
    paths = {r["path"] for r in result["results"]}
    assert "a.md" in paths
    assert "b.md" in paths
    assert "c.md" not in paths


@pytest.mark.asyncio
async def test_grep_with_path_pattern(workspace_service):
    """Grep can be filtered by path pattern."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "research/doc.md", "---\ntitle: R\n---\nUnique content xyz"
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "notes/doc.md", "---\ntitle: N\n---\nUnique content xyz"
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default",
        "Unique content xyz", path_pattern="research/**"
    )
    assert result["total_files"] == 1
    assert result["results"][0]["path"] == "research/doc.md"


@pytest.mark.asyncio
async def test_grep_no_matches(workspace_service):
    """Grep returns empty when no matches found."""
    await workspace_service.write(
        "test-org", "test-user", "default", "doc.md", "---\ntitle: X\n---\nSome content"
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "nonexistent_phrase_12345"
    )
    assert result["total_files"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_grep_case_insensitive(workspace_service):
    """Grep is case-insensitive."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "case.md", "---\ntitle: Case\n---\nImportant Meeting Notes"
    )

    result = await workspace_service.grep_files(
        "test-org", "test-user", "default", "important meeting"
    )
    assert result["total_files"] == 1
