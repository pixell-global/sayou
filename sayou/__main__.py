import argparse
import asyncio

from sayou.server import create_server


async def _run_stdio():
    server, ws = create_server()
    try:
        await server.run_stdio_async()
    finally:
        await ws.close()


async def _run_http(host: str, port: int):
    server, ws = create_server()
    server.settings.host = host
    server.settings.port = port
    server.settings.stateless_http = True
    try:
        await server.run_streamable_http_async()
    finally:
        await ws.close()


def _add_common_args(parser):
    """Add common workspace identity args to a parser."""
    parser.add_argument("--workspace", "-w", default="default", help="Workspace slug")
    parser.add_argument("--org-id", default=None, help="Organization ID")
    parser.add_argument("--user-id", default=None, help="User ID")
    parser.add_argument("--database-url", default=None, help="Database URL")
    parser.add_argument("--storage-path", default=None, help="Local storage path")


def main():
    parser = argparse.ArgumentParser(prog="sayou", description="sayou — persistent workspace for AI agents")
    subparsers = parser.add_subparsers(dest="command")

    # ── server ───────────────────────────────────────────────────
    server_parser = subparsers.add_parser("server", help="Start MCP server")
    server_parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="Transport type (default: stdio)",
    )
    server_parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    server_parser.add_argument("--port", type=int, default=8080, help="HTTP bind port")

    # ── file ─────────────────────────────────────────────────────
    file_parser = subparsers.add_parser("file", help="File operations")
    file_sub = file_parser.add_subparsers(dest="file_command")

    # file read
    fr = file_sub.add_parser("read", help="Read a file")
    fr.add_argument("path", help="File path")
    fr.add_argument("--token-budget", type=int, default=4000, help="Token budget")
    fr.add_argument("--version", type=int, default=None, help="Specific version number")
    fr.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(fr)

    # file write
    fw = file_sub.add_parser("write", help="Write a file")
    fw.add_argument("path", help="File path")
    fw.add_argument("content", help="Content (use '-' for stdin)")
    fw.add_argument("--source", default=None, help="Source agent ID")
    _add_common_args(fw)

    # file delete
    fd = file_sub.add_parser("delete", help="Delete a file")
    fd.add_argument("path", help="File path")
    fd.add_argument("--source", default=None, help="Source agent ID")
    _add_common_args(fd)

    # file list
    fl = file_sub.add_parser("list", help="List files")
    fl.add_argument("path", nargs="?", default="/", help="Folder path")
    fl.add_argument("--recursive", "-r", action="store_true", help="Recursive listing")
    fl.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(fl)

    # file search
    fs = file_sub.add_parser("search", help="Search files")
    fs.add_argument("--query", "-q", default=None, help="Full-text query")
    fs.add_argument("--filter", "-f", action="append", help="Frontmatter filter (key=value)")
    _add_common_args(fs)

    # file history
    fh = file_sub.add_parser("history", help="File version history")
    fh.add_argument("path", help="File path")
    fh.add_argument("--limit", type=int, default=20, help="Max versions to show")
    _add_common_args(fh)

    # file diff
    fdi = file_sub.add_parser("diff", help="Diff two versions")
    fdi.add_argument("path", help="File path")
    fdi.add_argument("version_a", type=int, help="First version number")
    fdi.add_argument("version_b", type=int, help="Second version number")
    fdi.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(fdi)

    # file move
    fm = file_sub.add_parser("move", help="Move a file")
    fm.add_argument("source_path", help="Source path")
    fm.add_argument("dest_path", help="Destination path")
    fm.add_argument("--source", default=None, help="Source agent ID")
    _add_common_args(fm)

    # file copy
    fc = file_sub.add_parser("copy", help="Copy a file")
    fc.add_argument("source_path", help="Source path")
    fc.add_argument("dest_path", help="Destination path")
    fc.add_argument("--source", default=None, help="Source agent ID")
    _add_common_args(fc)

    # ── kv ───────────────────────────────────────────────────────
    kv_parser = subparsers.add_parser("kv", help="Key-value store operations")
    kv_sub = kv_parser.add_subparsers(dest="kv_command")

    # kv get
    kg = kv_sub.add_parser("get", help="Get a KV entry")
    kg.add_argument("key", help="Key name")
    _add_common_args(kg)

    # kv set
    ks = kv_sub.add_parser("set", help="Set a KV entry")
    ks.add_argument("key", help="Key name")
    ks.add_argument("value", help="Value (JSON string)")
    ks.add_argument("--ttl", type=int, default=None, help="TTL in seconds")
    _add_common_args(ks)

    # kv delete
    kd = kv_sub.add_parser("delete", help="Delete a KV entry")
    kd.add_argument("key", help="Key name")
    _add_common_args(kd)

    # kv list
    kl = kv_sub.add_parser("list", help="List KV entries")
    kl.add_argument("--prefix", default=None, help="Key prefix filter")
    _add_common_args(kl)

    # ── init ─────────────────────────────────────────────────────
    init_parser = subparsers.add_parser("init", help="Initialize local sayou setup")
    init_parser.add_argument("--claude", action="store_true", help="Auto-configure Claude Code (~/.claude/mcp.json)")
    init_parser.add_argument("--cursor", action="store_true", help="Auto-configure Cursor (.cursor/mcp.json)")
    init_parser.add_argument("--windsurf", action="store_true", help="Auto-configure Windsurf (~/.codeium/windsurf/mcp_config.json)")

    # ── status ───────────────────────────────────────────────────
    subparsers.add_parser("status", help="Show sayou diagnostic status")

    # ── audit ────────────────────────────────────────────────────
    audit_parser = subparsers.add_parser("audit", help="Query audit log")
    audit_parser.add_argument("--path", default=None, help="Filter by file path")
    audit_parser.add_argument("--action", default=None, help="Filter by action")
    audit_parser.add_argument("--agent-id", default=None, help="Filter by agent")
    audit_parser.add_argument("--limit", type=int, default=50, help="Max entries")
    _add_common_args(audit_parser)

    args = parser.parse_args()

    # Default: bare `sayou` or `sayou --transport stdio` runs server
    if args.command is None:
        asyncio.run(_run_stdio())
        return

    if args.command == "server":
        if args.transport == "http":
            try:
                import fastapi  # noqa: F401
            except ImportError:
                print("REST API requires additional dependencies.")
                print("Install with: pip install sayou[api]")
                return
            asyncio.run(_run_http(args.host, args.port))
        else:
            asyncio.run(_run_stdio())
        return

    if args.command == "init":
        from sayou.cli.init import run_init
        editor = None
        for name in ("claude", "cursor", "windsurf"):
            if getattr(args, name, False):
                editor = name
                break
        asyncio.run(run_init(editor=editor))
        return

    if args.command == "status":
        from sayou.cli.status import run_status
        asyncio.run(run_status())
        return

    # CLI commands
    from sayou.cli import commands

    cmd_map = {
        ("file", "read"): commands.file_read,
        ("file", "write"): commands.file_write,
        ("file", "delete"): commands.file_delete,
        ("file", "list"): commands.file_list,
        ("file", "search"): commands.file_search,
        ("file", "history"): commands.file_history,
        ("file", "diff"): commands.file_diff,
        ("file", "move"): commands.file_move,
        ("file", "copy"): commands.file_copy,
        ("kv", "get"): commands.kv_get,
        ("kv", "set"): commands.kv_set,
        ("kv", "delete"): commands.kv_delete,
        ("kv", "list"): commands.kv_list,
        ("audit", None): commands.audit,
    }

    sub = getattr(args, "file_command", None) or getattr(args, "kv_command", None)
    handler = cmd_map.get((args.command, sub))

    if handler is None:
        parser.print_help()
        return

    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
