"""CLI command implementations using the Workspace public API."""

from __future__ import annotations

import asyncio
import json
import sys

from sayou.workspace import Workspace


def _get_workspace(**kwargs) -> Workspace:
    """Create a Workspace from CLI args + env vars."""
    return Workspace(
        slug=kwargs.get("workspace", "default"),
        org_id=kwargs.get("org_id"),
        user_id=kwargs.get("user_id"),
        database_url=kwargs.get("database_url"),
        storage_path=kwargs.get("storage_path"),
    )


def _print_json(data):
    print(json.dumps(data, indent=2, default=str))


# ── File commands ────────────────────────────────────────────────

async def file_read(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.read(
            args.path,
            token_budget=args.token_budget,
            version=args.version,
        )
        if args.json:
            _print_json(result)
        else:
            print(result["content"])


async def file_write(args):
    content = args.content
    if content == "-":
        content = sys.stdin.read()
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.write(args.path, content, source=args.source)
        _print_json(result)


async def file_delete(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.delete(args.path, source=args.source)
        _print_json(result)


async def file_list(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.list(args.path, recursive=args.recursive)
        if args.json:
            _print_json(result)
        else:
            print(result.get("index_content", ""))


async def file_search(args):
    async with _get_workspace(**vars(args)) as ws:
        filters = None
        if args.filter:
            filters = {}
            for f in args.filter:
                k, _, v = f.partition("=")
                filters[k] = v
        result = await ws.search(query=args.query, filters=filters)
        _print_json(result)


async def file_history(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.history(args.path, limit=args.limit)
        _print_json(result)


async def file_diff(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.diff(args.path, args.version_a, args.version_b)
        if args.json:
            _print_json(result)
        else:
            print(result["diff"])


async def file_move(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.move(args.source_path, args.dest_path, source=args.source)
        _print_json(result)


async def file_copy(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.copy(args.source_path, args.dest_path, source=args.source)
        _print_json(result)


# ── KV commands ──────────────────────────────────────────────────

async def kv_get(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.kv_get(args.key)
        _print_json(result)


async def kv_set(args):
    value = args.value
    try:
        value = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        pass
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.kv_set(args.key, value, ttl_seconds=args.ttl)
        _print_json(result)


async def kv_delete(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.kv_delete(args.key)
        _print_json(result)


async def kv_list(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.kv_list(prefix=args.prefix)
        _print_json(result)


# ── Workspace commands ───────────────────────────────────────────

async def workspace_list(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.list("/")
        _print_json({"workspace": args.workspace, "root": result})


# ── Audit command ────────────────────────────────────────────────

async def audit(args):
    async with _get_workspace(**vars(args)) as ws:
        result = await ws.audit(
            path=args.path,
            action=args.action,
            agent_id=args.agent_id,
            limit=args.limit,
        )
        _print_json(result)
