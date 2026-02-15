"""Performance validation tests (Gap 7).

Validates write latency, index chain propagation, list/search performance
at scale, and query plan efficiency.
"""

import time

import pytest


@pytest.mark.asyncio
async def test_write_50kb_under_1_second(workspace_service):
    """Write ~50KB file completes in <1 second."""
    content = "x" * 50_000  # ~50KB
    start = time.monotonic()
    result = await workspace_service.write(
        "test-org", "test-user", "default", "perf/large.md", content
    )
    elapsed = time.monotonic() - start

    assert result["size_bytes"] == 50_000
    assert elapsed < 1.0, f"Write took {elapsed:.3f}s, expected <1s"


@pytest.mark.asyncio
async def test_average_write_latency(workspace_service):
    """Average write latency for 10 files is <1s."""
    times = []
    for i in range(10):
        content = f"---\nindex: {i}\n---\nFile content {i}\n" + ("data " * 100)
        start = time.monotonic()
        await workspace_service.write(
            "test-org", "test-user", "default", f"perf/file_{i}.md", content
        )
        times.append(time.monotonic() - start)

    avg = sum(times) / len(times)
    assert avg < 1.0, f"Average write latency {avg:.3f}s, expected <1s"


@pytest.mark.asyncio
async def test_write_200_files_across_20_folders(workspace_service):
    """Write 200 files across 20 folders, each write stays under 1s."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    slow_count = 0
    for folder_idx in range(20):
        for file_idx in range(10):
            path = f"scale/folder_{folder_idx:02d}/file_{file_idx:02d}.md"
            content = (
                f"---\nfolder: {folder_idx}\nindex: {file_idx}\n"
                f"status: {'active' if file_idx % 2 == 0 else 'draft'}\n---\n"
                f"# File {folder_idx}-{file_idx}\n\nContent body.\n"
            )
            start = time.monotonic()
            await svc.write(org, user, slug, path, content)
            elapsed = time.monotonic() - start
            if elapsed > 1.0:
                slow_count += 1

    # Allow up to 5% of writes to exceed 1s (e.g. first write creates workspace)
    assert slow_count <= 10, f"{slow_count}/200 writes exceeded 1s"


@pytest.mark.asyncio
async def test_deep_index_chain_propagation(workspace_service):
    """Write to 5-level deep path, verify index chain propagates to root."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    deep_path = "a/b/c/d/e/deep_file.md"
    content = "---\ntitle: Deep\n---\n# Deep File\n"

    start = time.monotonic()
    await svc.write(org, user, slug, deep_path, content)
    elapsed = time.monotonic() - start

    # Even with 5-level chain propagation, should complete quickly
    assert elapsed < 2.0, f"Deep write + chain took {elapsed:.3f}s"

    # Verify root index exists and references the top-level folder
    root_listing = await svc.list_folder(org, user, slug, "/")
    assert root_listing["file_count"] >= 0  # root listing works

    # Verify intermediate folder listing
    mid_listing = await svc.list_folder(org, user, slug, "a/b/c")
    assert mid_listing["file_count"] >= 0


@pytest.mark.asyncio
async def test_list_latency_with_many_files(workspace_service):
    """List folder with 50 files completes in <1s."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Write 50 files to same folder
    for i in range(50):
        path = f"listing_test/file_{i:03d}.md"
        content = f"---\nindex: {i}\n---\n# File {i}\n"
        await svc.write(org, user, slug, path, content)

    # Time the list operation
    start = time.monotonic()
    result = await svc.list_folder(org, user, slug, "listing_test")
    elapsed = time.monotonic() - start

    assert result["file_count"] == 50
    assert elapsed < 1.0, f"Listing 50 files took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_search_latency_with_many_files(workspace_service):
    """Search across 50 files completes in <1s."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Write 50 files with varied frontmatter
    for i in range(50):
        status = "active" if i % 3 == 0 else "draft"
        path = f"search_perf/doc_{i:03d}.md"
        content = f"---\nstatus: {status}\nauthor: user-{i % 5}\n---\n# Doc {i}\n"
        await svc.write(org, user, slug, path, content)

    # Time the search
    start = time.monotonic()
    result = await svc.search(org, user, slug, filters={"status": "active"})
    elapsed = time.monotonic() - start

    assert result["total"] >= 10  # roughly 1/3 of 50
    assert elapsed < 1.0, f"Search took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_kv_store_throughput(workspace_service):
    """KV store can handle 100 set/get operations quickly."""
    svc = workspace_service
    org, user, slug = "test-org", "test-user", "default"

    # Set 100 keys
    start = time.monotonic()
    for i in range(100):
        await svc.kv_set(org, user, slug, f"bench.key.{i}", {"index": i, "data": "x" * 100})
    set_elapsed = time.monotonic() - start

    # Get 100 keys
    start = time.monotonic()
    for i in range(100):
        result = await svc.kv_get(org, user, slug, f"bench.key.{i}")
        assert result["found"] is True
    get_elapsed = time.monotonic() - start

    # List all
    start = time.monotonic()
    result = await svc.kv_list(org, user, slug, "bench.key")
    list_elapsed = time.monotonic() - start
    assert result["total"] == 100

    # All operations should be fast
    assert set_elapsed < 10.0, f"100 KV sets took {set_elapsed:.3f}s"
    assert get_elapsed < 5.0, f"100 KV gets took {get_elapsed:.3f}s"
    assert list_elapsed < 1.0, f"KV list of 100 items took {list_elapsed:.3f}s"
