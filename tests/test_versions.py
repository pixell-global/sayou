"""S4: Version history - 5 writes = 5 versions, correct ordering, distinct hashes."""

import pytest


@pytest.mark.asyncio
async def test_five_versions(workspace_service):
    """Write same path 5 times, verify version history."""
    path = "docs/evolving.md"
    hashes = []

    for i in range(5):
        result = await workspace_service.write(
            "test-org", "test-user", "default",
            path,
            f"---\nversion: {i + 1}\n---\nContent revision {i + 1}",
        )
        assert result["version_number"] == i + 1
        hashes.append(result["content_hash"])

    # All hashes should be distinct
    assert len(set(hashes)) == 5

    # History returns versions in descending order [5, 4, 3, 2, 1]
    history = await workspace_service.history(
        "test-org", "test-user", "default", path
    )
    assert history["total"] == 5
    version_numbers = [v["version_number"] for v in history["versions"]]
    assert version_numbers == [5, 4, 3, 2, 1]

    # Read returns latest (5th) version content
    read_result = await workspace_service.read(
        "test-org", "test-user", "default", path
    )
    assert read_result["version_number"] == 5
    assert "Content revision 5" in read_result["content"]


@pytest.mark.asyncio
async def test_version_count_on_file(workspace_service):
    """File's version_count is accurate after multiple writes."""
    path = "tracking/count.md"
    for i in range(3):
        result = await workspace_service.write(
            "test-org", "test-user", "default", path, f"v{i + 1}"
        )

    history = await workspace_service.history(
        "test-org", "test-user", "default", path
    )
    assert history["total"] == 3
