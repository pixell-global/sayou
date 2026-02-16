"""Tests for schema discovery from frontmatter."""

import tempfile

import pytest

from sayou import Workspace
from sayou.core.schema_discovery import discover_schema, infer_field_type


# ── Unit tests: type inference ───────────────────────────────────


def test_infer_string():
    assert infer_field_type(["hello", "world"]) == "string"


def test_infer_number():
    assert infer_field_type([1, 2.5, 3]) == "number"


def test_infer_boolean():
    assert infer_field_type([True, False, True]) == "boolean"


def test_infer_list():
    assert infer_field_type([["a", "b"], ["c"]]) == "list"


def test_infer_date():
    assert infer_field_type(["2026-01-01", "2026-02-15"]) == "date"


def test_infer_empty():
    assert infer_field_type([]) == "string"


def test_infer_mixed_prefers_majority():
    """Mixed types: majority wins."""
    assert infer_field_type(["a", "b", 1]) == "string"


# ── Unit tests: schema discovery ─────────────────────────────────


def test_discover_schema_basic():
    """Discover fields from frontmatter list."""
    frontmatters = [
        {"title": "Doc 1", "status": "active", "tags": ["a", "b"]},
        {"title": "Doc 2", "status": "draft"},
        {"title": "Doc 3", "status": "active", "priority": 1},
    ]
    schema = discover_schema(frontmatters)
    field_map = {f["field_name"]: f for f in schema}

    assert "title" in field_map
    assert field_map["title"]["field_type"] == "string"
    assert field_map["title"]["occurrence_count"] == 3

    assert "status" in field_map
    assert field_map["status"]["occurrence_count"] == 3
    assert "active" in field_map["status"]["sample_values"]

    assert "tags" in field_map
    assert field_map["tags"]["field_type"] == "list"

    assert "priority" in field_map
    assert field_map["priority"]["field_type"] == "number"


def test_discover_schema_auto_flag():
    """_auto_ prefixed fields are flagged."""
    frontmatters = [
        {"title": "Doc", "_auto_summary": "A doc", "_auto_tags": ["test"]},
    ]
    schema = discover_schema(frontmatters)
    field_map = {f["field_name"]: f for f in schema}

    assert not field_map["title"]["is_auto"]
    assert field_map["_auto_summary"]["is_auto"]
    assert field_map["_auto_tags"]["is_auto"]


def test_discover_schema_sample_values():
    """Sample values limited to 10."""
    frontmatters = [{"x": f"val_{i}"} for i in range(20)]
    schema = discover_schema(frontmatters)
    assert len(schema[0]["sample_values"]) == 10


def test_discover_schema_empty():
    """Empty input returns empty schema."""
    assert discover_schema([]) == []


def test_discover_schema_none_frontmatters():
    """None values in list are skipped."""
    assert discover_schema([None, {}, None]) == []


# ── Integration tests ────────────────────────────────────────────


def _make_ws(**kwargs) -> Workspace:
    tmpdir = kwargs.pop("_tmpdir", None) or tempfile.mkdtemp()
    defaults = dict(
        database_url="sqlite+aiosqlite://",
        storage_path=tmpdir,
        org_id="test-org",
        user_id="test-user",
    )
    defaults.update(kwargs)
    return Workspace(**defaults)


@pytest.mark.asyncio
async def test_workspace_schema():
    """schema() discovers fields from all files."""
    async with _make_ws() as ws:
        await ws.write("a.md", "---\ntitle: Doc A\nstatus: active\n---\nBody A")
        await ws.write("b.md", "---\ntitle: Doc B\nstatus: draft\npriority: 1\n---\nBody B")
        await ws.write("c.md", "---\ntitle: Doc C\nstatus: active\n---\nBody C")

        result = await ws.schema()
        assert result["total_files_scanned"] == 3
        assert result["total_fields"] >= 3

        field_map = {f["field_name"]: f for f in result["fields"]}
        assert "title" in field_map
        assert field_map["status"]["occurrence_count"] == 3
        assert field_map["priority"]["occurrence_count"] == 1


@pytest.mark.asyncio
async def test_workspace_schema_empty():
    """schema() on empty workspace returns empty."""
    async with _make_ws() as ws:
        result = await ws.schema()
        assert result["total_fields"] == 0
        assert result["total_files_scanned"] == 0


@pytest.mark.asyncio
async def test_workspace_schema_no_frontmatter():
    """Files without frontmatter are scanned but contribute nothing."""
    async with _make_ws() as ws:
        await ws.write("plain.md", "No frontmatter here")
        result = await ws.schema()
        assert result["total_fields"] == 0
