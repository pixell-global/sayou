"""S3: Search - frontmatter filter exact match, full-text search."""

import pytest


@pytest.mark.asyncio
async def test_search_by_frontmatter_filter(workspace_service):
    """Write 5 files (3 active, 2 archived), search active returns exactly 3."""
    for i in range(3):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"docs/active_{i}.md",
            f"---\nstatus: active\ntopic: testing\n---\nActive doc {i}",
        )
    for i in range(2):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"docs/archived_{i}.md",
            f"---\nstatus: archived\ntopic: testing\n---\nArchived doc {i}",
        )

    result = await workspace_service.search(
        "test-org", "test-user", "default", filters={"status": "active"}
    )
    assert result["total"] == 3
    paths = [r["path"] for r in result["results"]]
    for i in range(3):
        assert f"docs/active_{i}.md" in paths


@pytest.mark.asyncio
async def test_search_fulltext(workspace_service):
    """Search by text query matches file path and frontmatter."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "analysis/competitive-analysis.md",
        "---\ntitle: Competitive Analysis\nstatus: draft\n---\nDetailed competitive analysis here.",
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "notes/random.md",
        "---\ntitle: Random Notes\n---\nSome random content.",
    )

    result = await workspace_service.search(
        "test-org", "test-user", "default", query="competitive"
    )
    assert result["total"] >= 1
    paths = [r["path"] for r in result["results"]]
    assert "analysis/competitive-analysis.md" in paths


@pytest.mark.asyncio
async def test_search_combined_filters_and_query(workspace_service):
    """Combined filters + query returns intersection."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "reports/q1-revenue.md",
        "---\nstatus: active\nquarter: Q1\n---\nQ1 report.",
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "reports/q2-revenue.md",
        "---\nstatus: archived\nquarter: Q2\n---\nQ2 report.",
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "reports/q3-growth.md",
        "---\nstatus: active\nquarter: Q3\n---\nQ3 report.",
    )

    # Active + path contains "revenue" → only q1 (active and path matches)
    result = await workspace_service.search(
        "test-org", "test-user", "default",
        query="revenue",
        filters={"status": "active"},
    )
    assert result["total"] == 1
    paths = [r["path"] for r in result["results"]]
    assert "reports/q1-revenue.md" in paths
    assert "reports/q2-revenue.md" not in paths  # archived
    assert "reports/q3-growth.md" not in paths  # no "revenue" in path/frontmatter
