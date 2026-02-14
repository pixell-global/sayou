"""S5: Org isolation - 2 orgs same path, independent files, isolated search/list."""

import pytest


@pytest.mark.asyncio
async def test_org_isolation_write_read(workspace_service):
    """Org A and Org B write to same path, each sees only their own."""
    path = "research/test.md"

    await workspace_service.write(
        "org-a", "user-a", "default", path, "---\norg: A\n---\nOrg A content"
    )
    await workspace_service.write(
        "org-b", "user-b", "default", path, "---\norg: B\n---\nOrg B content"
    )

    read_a = await workspace_service.read("org-a", "user-a", "default", path)
    assert "Org A content" in read_a["content"]
    assert read_a["frontmatter"]["org"] == "A"

    read_b = await workspace_service.read("org-b", "user-b", "default", path)
    assert "Org B content" in read_b["content"]
    assert read_b["frontmatter"]["org"] == "B"


@pytest.mark.asyncio
async def test_org_isolation_search(workspace_service):
    """Search from Org A never returns Org B's files."""
    await workspace_service.write(
        "org-a", "user-a", "default", "shared/data.md",
        "---\nstatus: active\n---\nOrg A data",
    )
    await workspace_service.write(
        "org-b", "user-b", "default", "shared/data.md",
        "---\nstatus: active\n---\nOrg B data",
    )

    result_a = await workspace_service.search(
        "org-a", "user-a", "default", filters={"status": "active"}
    )
    paths_a = [r["path"] for r in result_a["results"]]
    assert result_a["total"] == 1
    assert "shared/data.md" in paths_a

    result_b = await workspace_service.search(
        "org-b", "user-b", "default", filters={"status": "active"}
    )
    assert result_b["total"] == 1


@pytest.mark.asyncio
async def test_org_isolation_list(workspace_service):
    """List from Org A never returns Org B's files."""
    await workspace_service.write(
        "org-a", "user-a", "default", "docs/a.md", "Org A doc"
    )
    await workspace_service.write(
        "org-b", "user-b", "default", "docs/b.md", "Org B doc"
    )

    list_a = await workspace_service.list_folder(
        "org-a", "user-a", "default", "docs/"
    )
    filenames = [f["filename"] for f in list_a["files"]]
    assert "a.md" in filenames
    assert "b.md" not in filenames

    list_b = await workspace_service.list_folder(
        "org-b", "user-b", "default", "docs/"
    )
    filenames_b = [f["filename"] for f in list_b["files"]]
    assert "b.md" in filenames_b
    assert "a.md" not in filenames_b
