"""Integration smoke tests — hits real RDS + S3.

Run:  SAYOU_SMOKE=1 pytest tests/test_smoke.py -v
Skip: pytest tests/  (skips automatically without SAYOU_SMOKE=1)
"""

import os
from pathlib import Path
from uuid import uuid4

import aioboto3
import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SAYOU_SMOKE") != "1",
        reason="Set SAYOU_SMOKE=1 to run integration tests",
    ),
    pytest.mark.integration,
]


def _load_real_env() -> dict[str, str]:
    """Parse sayou/.env for real infrastructure credentials."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        pytest.skip(f".env not found at {env_path}")
    vals: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            vals[key.strip()] = val.strip()
    return vals


@pytest_asyncio.fixture
async def smoke_env():
    """Real RDS + S3 connection. Cleans up all data on teardown."""
    from sayou.catalog.database import close_db, get_db, init_db
    from sayou.core.workspace import WorkspaceService
    from sayou.storage.s3 import StorageService

    real = _load_real_env()
    db_url = real.get("SAYOU_DATABASE_URL", "")
    if not db_url or "sqlite" in db_url:
        pytest.skip("Real MySQL DATABASE_URL required in .env")

    # Unique org prevents collisions between parallel runs
    smoke_org = f"smoke-{uuid4().hex[:12]}"

    # Connect to real MySQL
    await close_db()
    await init_db(db_url)

    # Real S3 storage
    storage = StorageService(
        bucket=real.get("SAYOU_S3_BUCKET_NAME", "pixell-agents"),
        region=real.get("SAYOU_S3_REGION", "us-east-2"),
        access_key_id=real.get("SAYOU_S3_ACCESS_KEY_ID", ""),
        secret_access_key=real.get("SAYOU_S3_SECRET_ACCESS_KEY", ""),
    )

    svc = WorkspaceService(storage=storage)

    yield {
        "svc": svc,
        "storage": storage,
        "org_id": smoke_org,
        "user_id": "smoke-tester",
        "ws_slug": "default",
    }

    # --- Cleanup: S3 objects ---
    s3_config = storage._client_config()
    s3_session = aioboto3.Session()
    prefix = f"{smoke_org}/sayou/"
    async with s3_session.client(**s3_config) as s3:
        resp = await s3.list_objects_v2(Bucket=storage.bucket, Prefix=prefix)
        for obj in resp.get("Contents", []):
            await s3.delete_object(Bucket=storage.bucket, Key=obj["Key"])

    # --- Cleanup: DB records ---
    async with get_db() as db:
        # Get IDs for FK-safe deletion
        ws_rows = await db.execute(
            text("SELECT id FROM sayou_workspaces WHERE org_id = :org"),
            {"org": smoke_org},
        )
        ws_ids = [r[0] for r in ws_rows.fetchall()]

        file_rows = await db.execute(
            text("SELECT id FROM sayou_files WHERE org_id = :org"),
            {"org": smoke_org},
        )
        file_ids = [r[0] for r in file_rows.fetchall()]

        # Break circular FK: files.current_version_id → versions
        await db.execute(
            text("UPDATE sayou_files SET current_version_id = NULL WHERE org_id = :org"),
            {"org": smoke_org},
        )

        # Delete in FK-safe order
        for fid in file_ids:
            await db.execute(
                text("DELETE FROM sayou_file_versions WHERE file_id = :fid"),
                {"fid": fid},
            )
        await db.execute(
            text("DELETE FROM sayou_files WHERE org_id = :org"),
            {"org": smoke_org},
        )
        await db.execute(
            text("DELETE FROM sayou_mutation_log WHERE org_id = :org"),
            {"org": smoke_org},
        )
        await db.execute(
            text("DELETE FROM sayou_index_cache WHERE org_id = :org"),
            {"org": smoke_org},
        )
        for wid in ws_ids:
            await db.execute(
                text("DELETE FROM sayou_workspace_members WHERE workspace_id = :wid"),
                {"wid": wid},
            )
        await db.execute(
            text("DELETE FROM sayou_workspaces WHERE org_id = :org"),
            {"org": smoke_org},
        )

    # Close real MySQL so unit tests aren't affected
    await close_db()


# ---------------------------------------------------------------------------
# Full-cycle integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_full_cycle(smoke_env):
    """write → read → overwrite → list → search → history → delete → S3 verify."""
    svc = smoke_env["svc"]
    org = smoke_env["org_id"]
    user = smoke_env["user_id"]
    slug = smoke_env["ws_slug"]
    storage = smoke_env["storage"]

    folder = f"smoke-test/{uuid4().hex[:8]}"

    # ── Step 1: WRITE 3 files ────────────────────────────────────────────
    files = {
        f"{folder}/alpha.md": (
            "---\nstatus: active\nauthor: alice\n---\n# Alpha\n\nFirst file.\n"
        ),
        f"{folder}/beta.md": (
            "---\nstatus: draft\nauthor: bob\n---\n# Beta\n\nSecond file.\n"
        ),
        f"{folder}/gamma.md": (
            "---\nstatus: active\nauthor: alice\n---\n# Gamma\n\nThird file.\n"
        ),
    }

    write_results = {}
    for path, content in files.items():
        result = await svc.write(org, user, slug, path, content)
        write_results[path] = result
        assert result["version_number"] == 1
        assert result["size_bytes"] == len(content.encode("utf-8"))
        assert result["content_hash"]

    # ── Step 2: READ back each file — byte-identical ─────────────────────
    for path, content in files.items():
        read = await svc.read(org, user, slug, path)
        assert read["content"] == content, f"Content mismatch for {path}"
        assert read["version_number"] == 1
        assert read["size_bytes"] == len(content.encode("utf-8"))

    # ── Step 3: OVERWRITE alpha.md → version 2 ──────────────────────────
    updated = "---\nstatus: active\nauthor: alice\nupdated: true\n---\n# Alpha v2\n\nUpdated.\n"
    overwrite = await svc.write(org, user, slug, f"{folder}/alpha.md", updated)
    assert overwrite["version_number"] == 2

    read_v2 = await svc.read(org, user, slug, f"{folder}/alpha.md")
    assert read_v2["content"] == updated
    assert read_v2["version_number"] == 2

    # ── Step 4: LIST folder — 3 files, frontmatter columns in index ─────
    listing = await svc.list_folder(org, user, slug, folder)
    assert listing["file_count"] == 3
    assert len(listing["files"]) == 3
    filenames = {f["filename"] for f in listing["files"]}
    assert filenames == {"alpha.md", "beta.md", "gamma.md"}
    assert "status" in listing["index_content"]

    # ── Step 5: SEARCH by frontmatter status=active ──────────────────────
    search = await svc.search(org, user, slug, filters={"status": "active"})
    assert search["total"] == 2
    found = {r["path"] for r in search["results"]}
    assert f"{folder}/alpha.md" in found
    assert f"{folder}/gamma.md" in found

    # ── Step 6: HISTORY — 2 versions for overwritten file ────────────────
    history = await svc.history(org, user, slug, f"{folder}/alpha.md")
    assert history["total"] == 2
    assert history["versions"][0]["version_number"] == 2  # newest first
    assert history["versions"][1]["version_number"] == 1

    # ── Step 7: DELETE beta.md, verify list count drops ──────────────────
    delete = await svc.delete(org, user, slug, f"{folder}/beta.md")
    assert delete["deleted"] is True

    listing_after = await svc.list_folder(org, user, slug, folder)
    assert listing_after["file_count"] == 2
    remaining = {f["filename"] for f in listing_after["files"]}
    assert "beta.md" not in remaining

    # ── Step 8: Verify S3 objects exist via head_object ──────────────────
    s3_config = storage._client_config()
    s3_session = aioboto3.Session()
    prefix = f"{org}/sayou/"
    async with s3_session.client(**s3_config) as s3:
        resp = await s3.list_objects_v2(Bucket=storage.bucket, Prefix=prefix)
        s3_keys = [obj["Key"] for obj in resp.get("Contents", [])]
        # 4 versions: alpha v1, alpha v2, beta v1, gamma v1
        assert len(s3_keys) == 4, f"Expected 4 S3 objects, got {len(s3_keys)}: {s3_keys}"

        # Spot-check one object
        head = await s3.head_object(Bucket=storage.bucket, Key=s3_keys[0])
        assert head["ContentLength"] > 0


# ---------------------------------------------------------------------------
# MCP tool discovery test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_mcp_tools():
    """create_server() exposes 12 core tools (13 with embeddings) with correct schemas."""
    from sayou.server import create_server

    server, ws = create_server()
    tools = await server.list_tools()

    tool_names = {t.name for t in tools}
    expected = {
        "workspace_write",
        "workspace_read",
        "workspace_list",
        "workspace_search",
        "workspace_delete",
        "workspace_history",
        "workspace_glob",
        "workspace_grep",
        "workspace_kv",
        "workspace_links",
        "workspace_chunks",
        "workspace_context",
    }
    # workspace_semantic_search only registered when SAYOU_EMBEDDING_PROVIDER is set
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"
    assert tool_names - expected <= {"workspace_semantic_search"}, f"Unexpected extra tools: {tool_names - expected}"

    tool_map = {t.name: t for t in tools}

    # workspace_write requires path + content
    write_schema = tool_map["workspace_write"].inputSchema
    assert "path" in write_schema["properties"]
    assert "content" in write_schema["properties"]

    # workspace_read requires path, has token_budget + line_start/line_end (merged read_section)
    read_schema = tool_map["workspace_read"].inputSchema
    assert "path" in read_schema["properties"]
    assert "token_budget" in read_schema["properties"]
    assert "line_start" in read_schema["properties"]
    assert "line_end" in read_schema["properties"]

    # workspace_search has query + filters + chunk_level (merged search_chunks)
    search_schema = tool_map["workspace_search"].inputSchema
    assert "query" in search_schema["properties"]
    assert "filters" in search_schema["properties"]
    assert "chunk_level" in search_schema["properties"]

    # workspace_history has path + limit + version_a/version_b (merged diff)
    history_schema = tool_map["workspace_history"].inputSchema
    assert "path" in history_schema["properties"]
    assert "limit" in history_schema["properties"]
    assert "version_a" in history_schema["properties"]
    assert "version_b" in history_schema["properties"]

    # workspace_glob has pattern
    glob_schema = tool_map["workspace_glob"].inputSchema
    assert "pattern" in glob_schema["properties"]

    # workspace_grep has query + path_pattern
    grep_schema = tool_map["workspace_grep"].inputSchema
    assert "query" in grep_schema["properties"]
    assert "path_pattern" in grep_schema["properties"]

    # workspace_kv has action (merged 4 KV tools)
    kv_schema = tool_map["workspace_kv"].inputSchema
    assert "action" in kv_schema["properties"]
    assert "key" in kv_schema["properties"]
    assert "value" in kv_schema["properties"]

    # workspace_links has path + add_target (merged add_link)
    links_schema = tool_map["workspace_links"].inputSchema
    assert "path" in links_schema["properties"]
    assert "add_target" in links_schema["properties"]

    # workspace_chunks has path + chunk_index (merged chunk)
    chunks_schema = tool_map["workspace_chunks"].inputSchema
    assert "path" in chunks_schema["properties"]
    assert "chunk_index" in chunks_schema["properties"]

    # workspace_context has no required parameters
    context_schema = tool_map["workspace_context"].inputSchema
    required = context_schema.get("required", [])
    assert len(required) == 0, f"workspace_context should have no required params, got: {required}"
