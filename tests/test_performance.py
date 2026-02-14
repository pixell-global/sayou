"""S8: Write latency - write completes in <1 second."""

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
