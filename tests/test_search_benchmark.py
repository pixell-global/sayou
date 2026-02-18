"""Benchmark tests: 500-file search comparing LIKE vs FTS5.

Run with: pytest tests/test_search_benchmark.py -v -s
"""

from __future__ import annotations

import json
import random
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sayou.catalog.models import Base, SayouChunk, SayouFile, generate_uuid
from sayou.catalog.queries import search_files_fts, search_files_fulltext
from sayou.catalog.queries_chunks import search_chunks, search_chunks_fts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILE_COUNT = 500
ORG_ID = "bench-org"
USER_ID = "bench-user"
WS_ID = "bench-ws"
DB_URL = "sqlite+aiosqlite://"

TOPICS = [
    "performance optimization", "database indexing", "machine learning",
    "frontend architecture", "API design", "security best practices",
    "deployment strategies", "monitoring and alerting", "data pipelines",
    "testing methodology", "code review guidelines", "team processes",
]
STATUSES = ["draft", "published", "archived", "review"]
AUTHORS = [
    "alice", "bob", "carol", "dave", "eve",
    "frank", "grace", "heidi", "ivan", "judy",
]

SEARCH_QUERIES = [
    "performance optimization",
    "database indexing",
    "machine learning",
    "API design",
    "monitoring",
]

random.seed(42)


# ---------------------------------------------------------------------------
# Module-scoped fixtures (seed data once, reuse across tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def bench_engine():
    engine = create_async_engine(
        DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create FTS5 tables
    from sayou.catalog.fts import create_fts_tables
    await create_fts_tables(engine, DB_URL)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def bench_session_factory(bench_engine):
    return async_sessionmaker(
        bench_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture(scope="module")
async def seeded_data(bench_engine, bench_session_factory):
    """Seed 500 files with varied content. Returns file count."""
    factory = bench_session_factory

    t0 = time.perf_counter()
    async with factory() as session:
        # Create workspace and member records
        from sayou.catalog.models import SayouWorkspace, SayouWorkspaceMember

        ws = SayouWorkspace(
            id=WS_ID, org_id=ORG_ID, name="Benchmark",
            slug="benchmark", created_by=USER_ID,
        )
        session.add(ws)
        member = SayouWorkspaceMember(
            id=generate_uuid(), workspace_id=WS_ID,
            user_id=USER_ID, role="admin",
        )
        session.add(member)

        for i in range(FILE_COUNT):
            topic = random.choice(TOPICS)
            status = random.choice(STATUSES)
            author = random.choice(AUTHORS)

            path = f"docs/{topic.replace(' ', '-')}/file-{i:04d}.md"
            folder = "/".join(path.split("/")[:-1]) + "/"
            filename = path.split("/")[-1]

            # Build multi-section content
            body_sections = [
                f"# {topic.title()} — Document {i}",
                f"\nThis document covers {topic} in detail.",
                f"\n## Overview\n\nA comprehensive guide to {topic} "
                f"written by {author}. Status: {status}.",
            ]
            # Add some unique searchable phrases
            if i % 3 == 0:
                body_sections.append(
                    f"\n## Performance Considerations\n\n"
                    f"When implementing {topic}, performance is critical. "
                    f"Use caching, connection pooling, and batch processing."
                )
            if i % 5 == 0:
                body_sections.append(
                    f"\n## Security Notes\n\n"
                    f"Always validate inputs and use parameterized queries. "
                    f"Follow OWASP guidelines for {topic}."
                )
            if i % 7 == 0:
                body_sections.append(
                    f"\n## Benchmarks\n\n"
                    f"Measured throughput: {random.randint(100, 10000)} ops/sec. "
                    f"Latency p99: {random.randint(1, 500)}ms."
                )

            body = "\n".join(body_sections)
            frontmatter = json.dumps({
                "topic": topic,
                "status": status,
                "author": author,
                "tags": [topic.split()[0], status],
            })

            file = SayouFile(
                id=generate_uuid(),
                org_id=ORG_ID,
                workspace_id=WS_ID,
                path=path,
                folder_path=folder,
                filename=filename,
                content_type="text/markdown",
                frontmatter=frontmatter,
                content_text=body,
                version_count=1,
            )
            session.add(file)

            # Add a chunk per file (simplified)
            chunk = SayouChunk(
                id=generate_uuid(),
                org_id=ORG_ID,
                workspace_id=WS_ID,
                file_id=file.id,
                version_id=generate_uuid(),
                chunk_index=0,
                heading=f"{topic.title()} — Document {i}",
                heading_level=1,
                content=body,
                line_start=1,
                line_end=body.count("\n") + 1,
                char_count=len(body),
                token_estimate=len(body) // 4,
                content_hash=str(hash(body)),
            )
            session.add(chunk)

        await session.commit()

    elapsed = time.perf_counter() - t0
    print(f"\n[SEED] {FILE_COUNT} files + chunks in {elapsed:.2f}s "
          f"({FILE_COUNT / elapsed:.0f} files/sec)")
    return FILE_COUNT


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_500_files(seeded_data):
    """Verify seeding completed successfully."""
    assert seeded_data == FILE_COUNT


@pytest.mark.asyncio
async def test_benchmark_fulltext_like(bench_session_factory, seeded_data):
    """Benchmark LIKE-based fulltext search."""
    times = []
    total_results = 0

    for query in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            results = await search_files_fulltext(session, ORG_ID, WS_ID, query)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            total_results += len(results)
            assert len(results) > 0, f"LIKE search for '{query}' returned no results"

    avg = sum(times) / len(times)
    print(f"\n[LIKE search] avg={avg*1000:.1f}ms  "
          f"total_results={total_results}  "
          f"queries={len(SEARCH_QUERIES)}")
    # Sanity: each query should complete under 2s even at 500 files
    assert max(times) < 2.0


@pytest.mark.asyncio
async def test_benchmark_fts_file_search(bench_session_factory, seeded_data):
    """Benchmark FTS5-based file search."""
    times = []
    total_results = 0

    for query in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            results = await search_files_fts(session, ORG_ID, WS_ID, query)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            total_results += len(results)
            assert len(results) > 0, f"FTS search for '{query}' returned no results"

    avg = sum(times) / len(times)
    print(f"\n[FTS5 search] avg={avg*1000:.1f}ms  "
          f"total_results={total_results}  "
          f"queries={len(SEARCH_QUERIES)}")
    assert max(times) < 2.0


@pytest.mark.asyncio
async def test_benchmark_frontmatter_filter(bench_session_factory, seeded_data):
    """Benchmark frontmatter filtering (Python-side JSON parsing)."""
    from sayou.catalog.queries import search_files_by_frontmatter

    filter_queries = [
        {"topic": t} for t in TOPICS[:5]
    ]
    times = []
    total_results = 0

    for filters in filter_queries:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            results = await search_files_by_frontmatter(
                session, ORG_ID, WS_ID, filters
            )
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            total_results += len(results)
            assert len(results) > 0

    avg = sum(times) / len(times)
    print(f"\n[Frontmatter filter] avg={avg*1000:.1f}ms  "
          f"total_results={total_results}")
    assert max(times) < 5.0


@pytest.mark.asyncio
async def test_benchmark_chunk_search_like(bench_session_factory, seeded_data):
    """Benchmark LIKE-based chunk search."""
    times = []
    total_results = 0

    for query in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            results = await search_chunks(session, ORG_ID, WS_ID, query)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            total_results += len(results)
            assert len(results) > 0

    avg = sum(times) / len(times)
    print(f"\n[LIKE chunk search] avg={avg*1000:.1f}ms  "
          f"total_results={total_results}")
    assert max(times) < 2.0


@pytest.mark.asyncio
async def test_benchmark_fts_chunk_search(bench_session_factory, seeded_data):
    """Benchmark FTS5-based chunk search."""
    times = []
    total_results = 0

    for query in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            results = await search_chunks_fts(
                session, ORG_ID, WS_ID, query
            )
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            total_results += len(results)
            assert len(results) > 0

    avg = sum(times) / len(times)
    print(f"\n[FTS5 chunk search] avg={avg*1000:.1f}ms  "
          f"total_results={total_results}")
    assert max(times) < 2.0


@pytest.mark.asyncio
async def test_benchmark_comparison_summary(bench_session_factory, seeded_data):
    """Run all search types and print a comparison table."""
    from sayou.catalog.queries import search_files_by_frontmatter

    results_table = {}

    # LIKE file search
    like_times = []
    for q in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            await search_files_fulltext(session, ORG_ID, WS_ID, q)
            like_times.append(time.perf_counter() - t0)
    results_table["LIKE file search"] = sum(like_times) / len(like_times)

    # FTS5 file search
    fts_times = []
    for q in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            await search_files_fts(session, ORG_ID, WS_ID, q)
            fts_times.append(time.perf_counter() - t0)
    results_table["FTS5 file search"] = sum(fts_times) / len(fts_times)

    # LIKE chunk search
    like_chunk_times = []
    for q in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            await search_chunks(session, ORG_ID, WS_ID, q)
            like_chunk_times.append(time.perf_counter() - t0)
    results_table["LIKE chunk search"] = sum(like_chunk_times) / len(like_chunk_times)

    # FTS5 chunk search
    fts_chunk_times = []
    for q in SEARCH_QUERIES:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            await search_chunks_fts(session, ORG_ID, WS_ID, q)
            fts_chunk_times.append(time.perf_counter() - t0)
    results_table["FTS5 chunk search"] = sum(fts_chunk_times) / len(fts_chunk_times)

    # Frontmatter filter
    fm_times = []
    for topic in TOPICS[:5]:
        async with bench_session_factory() as session:
            t0 = time.perf_counter()
            await search_files_by_frontmatter(session, ORG_ID, WS_ID, {"topic": topic})
            fm_times.append(time.perf_counter() - t0)
    results_table["Frontmatter filter"] = sum(fm_times) / len(fm_times)

    # Print comparison
    print("\n" + "=" * 60)
    print(f"{'Search Type':<25} {'Avg (ms)':>10} {'Speedup':>10}")
    print("-" * 60)

    like_avg = results_table["LIKE file search"]
    fts_avg = results_table["FTS5 file search"]
    like_chunk_avg = results_table["LIKE chunk search"]
    fts_chunk_avg = results_table["FTS5 chunk search"]

    for name, avg in results_table.items():
        speedup = ""
        if name == "FTS5 file search" and like_avg > 0:
            speedup = f"{like_avg / fts_avg:.1f}x"
        elif name == "FTS5 chunk search" and like_chunk_avg > 0:
            speedup = f"{like_chunk_avg / fts_chunk_avg:.1f}x"
        print(f"{name:<25} {avg*1000:>9.1f} {speedup:>10}")

    print("=" * 60)
    print(f"Files: {FILE_COUNT}  Queries: {len(SEARCH_QUERIES)}")

    # The test passes as long as it runs without error
    assert True


@pytest.mark.asyncio
async def test_fts_ranking_quality(bench_session_factory, seeded_data):
    """Verify FTS returns relevant results ranked higher than tangential ones."""
    async with bench_session_factory() as session:
        results = await search_files_fts(
            session, ORG_ID, WS_ID, "performance optimization"
        )
        assert len(results) > 0

        # The top results should be files whose path contains "performance-optimization"
        top_paths = [f.path for f in results[:10]]
        perf_count = sum(1 for p in top_paths if "performance-optimization" in p)
        # At least some top results should be from the performance-optimization folder
        assert perf_count > 0, (
            f"Expected top FTS results to include performance-optimization files, "
            f"got: {top_paths[:5]}"
        )
