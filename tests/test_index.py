"""S2: Index generation - 10 files across 3 folders, indexes accurate."""

import pytest


@pytest.mark.asyncio
async def test_folder_index_generation(workspace_service):
    """Write 10 files across 3 folders, verify indexes."""
    # research/trends/ - 4 files
    for i in range(4):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"research/trends/trend_{i}.md",
            f"---\nstatus: active\ncategory: trends\n---\nTrend {i} content",
        )

    # research/competitors/ - 3 files
    for i in range(3):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"research/competitors/comp_{i}.md",
            f"---\nstatus: active\ncategory: competitors\n---\nCompetitor {i}",
        )

    # clients/ - 3 files
    for i in range(3):
        await workspace_service.write(
            "test-org", "test-user", "default",
            f"clients/client_{i}.md",
            f"---\nstatus: active\ncategory: clients\n---\nClient {i}",
        )

    # Check research/trends/ folder
    trends = await workspace_service.list_folder(
        "test-org", "test-user", "default", "research/trends/"
    )
    assert trends["file_count"] == 4
    for i in range(4):
        assert f"trend_{i}.md" in trends["index_content"]

    # Check research/competitors/ folder
    comps = await workspace_service.list_folder(
        "test-org", "test-user", "default", "research/competitors/"
    )
    assert comps["file_count"] == 3
    for i in range(3):
        assert f"comp_{i}.md" in comps["index_content"]

    # Check clients/ folder
    clients = await workspace_service.list_folder(
        "test-org", "test-user", "default", "clients/"
    )
    assert clients["file_count"] == 3
    for i in range(3):
        assert f"client_{i}.md" in clients["index_content"]

    # Check root lists subfolders
    root = await workspace_service.list_folder(
        "test-org", "test-user", "default", "/"
    )
    assert "research/" in root["subfolders"]
    assert "clients/" in root["subfolders"]


@pytest.mark.asyncio
async def test_index_dynamic_frontmatter_columns(workspace_service):
    """Frontmatter columns appear dynamically in index table."""
    await workspace_service.write(
        "test-org", "test-user", "default",
        "docs/a.md", "---\npriority: high\nowner: alice\n---\nDoc A",
    )
    await workspace_service.write(
        "test-org", "test-user", "default",
        "docs/b.md", "---\npriority: low\nstage: review\n---\nDoc B",
    )

    result = await workspace_service.list_folder(
        "test-org", "test-user", "default", "docs/"
    )
    index = result["index_content"]
    # Dynamic columns should include priority, owner, stage
    assert "priority" in index
    assert "owner" in index
    assert "stage" in index
