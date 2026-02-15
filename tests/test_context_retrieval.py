"""Test context-aware retrieval (Gap 3)."""

import pytest


@pytest.mark.asyncio
async def test_large_file_returns_section_pointers(workspace_service):
    """Reading a large file with small budget returns structural summary with section pointers."""
    # Create a multi-section document
    sections = []
    for i in range(5):
        sections.append(f"## Section {i+1}\n\n")
        sections.append(f"This is the content of section {i+1}.\n")
        sections.append("A" * 200 + "\n\n")

    content = "---\ntitle: Big Doc\nstatus: active\n---\n# Main Title\n\n" + "".join(sections)

    await workspace_service.write(
        "test-org", "test-user", "default", "big-doc.md", content
    )

    # Read with a small budget that forces summarization
    result = await workspace_service.read(
        "test-org", "test-user", "default", "big-doc.md", token_budget=200
    )

    assert result["truncated"] is True
    # Should have section pointers
    assert "sections" in result
    assert len(result["sections"]) > 0
    assert result["total_lines"] > 0

    # All section headings should be referenced
    for sec in result["sections"]:
        assert "heading" in sec
        assert "line_start" in sec
        assert "line_end" in sec
        assert sec["line_start"] <= sec["line_end"]


@pytest.mark.asyncio
async def test_section_headings_present_in_summary(workspace_service):
    """Summary includes all section headings from the document."""
    content = (
        "---\ntitle: Test\n---\n"
        "# Introduction\n\nSome intro text.\n\n"
        "## Background\n\nBackground info here.\n\n"
        "## Methods\n\nMethod details.\n\n"
        "## Results\n\nResult data.\n\n"
        "## Conclusion\n\nFinal thoughts.\n\n"
        + ("Extra text. " * 200)  # Make it large enough to trigger summarization
    )

    await workspace_service.write(
        "test-org", "test-user", "default", "paper.md", content
    )

    result = await workspace_service.read(
        "test-org", "test-user", "default", "paper.md", token_budget=300
    )

    assert result["truncated"] is True
    # Summary content should reference the headings
    summary = result["content"]
    assert "Introduction" in summary or "Background" in summary


@pytest.mark.asyncio
async def test_read_section_returns_correct_lines(workspace_service):
    """read_section() returns the correct line range."""
    lines = [f"Line {i+1}" for i in range(50)]
    content = "\n".join(lines)

    await workspace_service.write(
        "test-org", "test-user", "default", "lines.md", content
    )

    result = await workspace_service.read_section(
        "test-org", "test-user", "default", "lines.md", 10, 15
    )

    assert result["line_start"] == 10
    assert result["line_end"] == 15
    assert result["total_lines"] == 50
    assert "Line 10" in result["content"]
    assert "Line 15" in result["content"]
    assert "Line 9" not in result["content"]
    assert "Line 16" not in result["content"]


@pytest.mark.asyncio
async def test_small_file_not_truncated(workspace_service):
    """Small files are returned in full without summarization."""
    content = "---\ntitle: Small\n---\n# Small\n\nShort content."

    await workspace_service.write(
        "test-org", "test-user", "default", "small.md", content
    )

    result = await workspace_service.read(
        "test-org", "test-user", "default", "small.md", token_budget=4000
    )

    assert result["truncated"] is False
    assert result["content"] == content
    assert "sections" not in result


@pytest.mark.asyncio
async def test_very_small_budget_falls_back_to_truncation(workspace_service):
    """Very small token budget falls back to simple truncation."""
    content = "---\ntitle: Test\nstatus: active\nauthor: alice\n---\n" + "x" * 5000

    await workspace_service.write(
        "test-org", "test-user", "default", "tiny-budget.md", content
    )

    # Budget of 1 = 4 chars, which is less than frontmatter size
    result = await workspace_service.read(
        "test-org", "test-user", "default", "tiny-budget.md", token_budget=1
    )

    assert result["truncated"] is True
    assert len(result["content"]) == 4


@pytest.mark.asyncio
async def test_read_section_nonexistent_file(workspace_service):
    """read_section() on a non-existent file raises error."""
    from sayou.core.workspace import FileNotFoundError as WsNotFound

    with pytest.raises(WsNotFound):
        await workspace_service.read_section(
            "test-org", "test-user", "default", "nope.md", 1, 10
        )
