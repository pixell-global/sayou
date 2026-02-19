"""Test CLI subcommands (Gap 10).

Uses the Workspace public API directly (same as CLI commands.py does)
to verify CLI command functions work correctly.
"""

import json

import pytest

from sayou.workspace import Workspace


@pytest.fixture
def ws_kwargs(tmp_path):
    """Workspace kwargs for a temporary SQLite database."""
    db_path = tmp_path / "test.db"
    return {
        "slug": "default",
        "org_id": "cli-org",
        "user_id": "cli-user",
        "database_url": f"sqlite+aiosqlite:///{db_path}",
        "storage_path": str(tmp_path / "storage"),
    }


@pytest.mark.asyncio
async def test_cli_file_write_and_read(ws_kwargs, capsys):
    """file write + file read roundtrip via Workspace API."""
    from sayou.cli.commands import file_read, file_write

    from argparse import Namespace

    # Write
    args = Namespace(
        path="notes/hello.md",
        content="---\ntitle: Hello\n---\n# Hello World\n",
        source=None,
        json=False,
        **ws_kwargs,
    )
    await file_write(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["path"] == "notes/hello.md"
    assert output["version_number"] == 1

    # Read (text mode)
    args = Namespace(
        path="notes/hello.md",
        token_budget=4000,
        version=None,
        json=False,
        **ws_kwargs,
    )
    await file_read(args)
    captured = capsys.readouterr()
    assert "# Hello World" in captured.out

    # Read (JSON mode)
    args = Namespace(
        path="notes/hello.md",
        token_budget=4000,
        version=None,
        json=True,
        **ws_kwargs,
    )
    await file_read(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["frontmatter"]["title"] == "Hello"


@pytest.mark.asyncio
async def test_cli_file_list(ws_kwargs, capsys):
    """file list shows files in a folder."""
    from sayou.cli.commands import file_list, file_write
    from argparse import Namespace

    # Write two files
    for name in ["a.md", "b.md"]:
        args = Namespace(
            path=f"docs/{name}",
            content=f"# {name}",
            source=None,
            json=False,
            **ws_kwargs,
        )
        await file_write(args)
        capsys.readouterr()  # discard

    # List (JSON mode)
    args = Namespace(
        path="docs",
        recursive=False,
        json=True,
        **ws_kwargs,
    )
    await file_list(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["file_count"] == 2


@pytest.mark.asyncio
async def test_cli_file_delete(ws_kwargs, capsys):
    """file delete removes a file."""
    from sayou.cli.commands import file_delete, file_write
    from argparse import Namespace

    # Write
    args = Namespace(
        path="temp.md", content="temporary", source=None, json=False, **ws_kwargs
    )
    await file_write(args)
    capsys.readouterr()

    # Delete
    args = Namespace(path="temp.md", source=None, **ws_kwargs)
    await file_delete(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["deleted"] is True


@pytest.mark.asyncio
async def test_cli_file_history_and_diff(ws_kwargs, capsys):
    """file history + file diff work after multiple writes."""
    from sayou.cli.commands import file_diff, file_history, file_write
    from argparse import Namespace

    # Write v1
    args = Namespace(
        path="versioned.md", content="version 1", source=None, json=False, **ws_kwargs
    )
    await file_write(args)
    capsys.readouterr()

    # Write v2
    args = Namespace(
        path="versioned.md", content="version 2", source=None, json=False, **ws_kwargs
    )
    await file_write(args)
    capsys.readouterr()

    # History
    args = Namespace(path="versioned.md", limit=20, **ws_kwargs)
    await file_history(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total"] == 2

    # Diff (text mode)
    args = Namespace(
        path="versioned.md", version_a=1, version_b=2, json=False, **ws_kwargs
    )
    await file_diff(args)
    captured = capsys.readouterr()
    assert "-version 1" in captured.out
    assert "+version 2" in captured.out


@pytest.mark.asyncio
async def test_cli_file_move_and_copy(ws_kwargs, capsys):
    """file move + file copy operations."""
    from sayou.cli.commands import file_copy, file_move, file_read, file_write
    from argparse import Namespace

    # Write original
    args = Namespace(
        path="original.md", content="original content", source=None, json=False,
        **ws_kwargs,
    )
    await file_write(args)
    capsys.readouterr()

    # Move
    args = Namespace(
        source_path="original.md", dest_path="moved.md", source=None, **ws_kwargs
    )
    await file_move(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["moved"] is True

    # Read moved file
    args = Namespace(
        path="moved.md", token_budget=4000, version=None, json=True, **ws_kwargs
    )
    await file_read(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["content"] == "original content"

    # Write another for copy test
    args = Namespace(
        path="src.md", content="copy me", source=None, json=False, **ws_kwargs
    )
    await file_write(args)
    capsys.readouterr()

    # Copy
    args = Namespace(
        source_path="src.md", dest_path="dst.md", source=None, **ws_kwargs
    )
    await file_copy(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["copied"] is True


@pytest.mark.asyncio
async def test_cli_file_search(ws_kwargs, capsys):
    """file search finds files by frontmatter."""
    from sayou.cli.commands import file_search, file_write
    from argparse import Namespace

    # Write file with frontmatter
    args = Namespace(
        path="tagged.md",
        content="---\nstatus: active\n---\n# Active\n",
        source=None,
        json=False,
        **ws_kwargs,
    )
    await file_write(args)
    capsys.readouterr()

    # Search
    args = Namespace(query=None, filter=["status=active"], **ws_kwargs)
    await file_search(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_cli_kv_crud(ws_kwargs, capsys):
    """kv set/get/list/delete roundtrip."""
    from sayou.cli.commands import kv_delete, kv_get, kv_list, kv_set
    from argparse import Namespace

    # Set
    args = Namespace(key="config.theme", value='"dark"', ttl=None, **ws_kwargs)
    await kv_set(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["key"] == "config.theme"

    # Get
    args = Namespace(key="config.theme", **ws_kwargs)
    await kv_get(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["found"] is True
    assert data["value"] == "dark"

    # List
    args = Namespace(prefix="config", **ws_kwargs)
    await kv_list(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total"] >= 1

    # Delete
    args = Namespace(key="config.theme", **ws_kwargs)
    await kv_delete(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["deleted"] is True

    # Verify deleted
    args = Namespace(key="config.theme", **ws_kwargs)
    await kv_get(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["found"] is False


@pytest.mark.asyncio
async def test_cli_audit(ws_kwargs, capsys):
    """audit command returns mutation log entries."""
    from sayou.cli.commands import audit, file_write
    from argparse import Namespace

    # Write a file to create audit entries
    args = Namespace(
        path="audited.md", content="# Audited", source="test-agent",
        json=False, **ws_kwargs,
    )
    await file_write(args)
    capsys.readouterr()

    # Query audit log
    args = Namespace(
        path=None, action=None, agent_id="test-agent", limit=50, **ws_kwargs
    )
    await audit(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_init_configure_editor(tmp_path):
    """sayou init --claude writes mcp.json correctly."""
    from sayou.cli.init import _configure_editor, EDITOR_CONFIGS
    from unittest.mock import patch

    mcp_path = tmp_path / "mcp.json"

    with patch.dict(EDITOR_CONFIGS, {"claude": mcp_path}):
        # First call: creates file
        _configure_editor("claude")
        data = json.loads(mcp_path.read_text())
        assert data == {"mcpServers": {"sayou": {"command": "sayou"}}}

        # Second call: idempotent (doesn't duplicate)
        _configure_editor("claude")
        data = json.loads(mcp_path.read_text())
        assert data == {"mcpServers": {"sayou": {"command": "sayou"}}}


@pytest.mark.asyncio
async def test_init_configure_editor_preserves_existing(tmp_path):
    """sayou init --claude preserves existing MCP servers."""
    from sayou.cli.init import _configure_editor, EDITOR_CONFIGS
    from unittest.mock import patch

    mcp_path = tmp_path / "mcp.json"
    existing = {"mcpServers": {"other-server": {"command": "other"}}}
    mcp_path.write_text(json.dumps(existing))

    with patch.dict(EDITOR_CONFIGS, {"claude": mcp_path}):
        _configure_editor("claude")
        data = json.loads(mcp_path.read_text())
        assert "other-server" in data["mcpServers"]
        assert "sayou" in data["mcpServers"]


@pytest.mark.asyncio
async def test_cli_argparse_structure():
    """Verify argparse subparsers are structured correctly."""
    from sayou.__main__ import main
    import sys
    from unittest.mock import patch
    from io import StringIO

    # Test that --help works without errors
    with patch("sys.argv", ["sayou", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    # Test file --help
    with patch("sys.argv", ["sayou", "file", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    # Test kv --help
    with patch("sys.argv", ["sayou", "kv", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
