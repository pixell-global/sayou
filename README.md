# sayou

**A file-system inspired context store for AI agents.**

Built to replace the databases of the web era. Open source. File-first. SQL-compatible.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)

Databases were designed for transactions — they reduce nuance to fit a schema. Agents think deeply, then forget everything when the session ends. sayou is where reasoning persists, context accumulates, and knowledge compounds over time.

- **Files that hold what databases can't** — Frontmatter for structure. Markdown for context. Versioned. Auditable.
- **One read. Full context.** — Every read accepts a `token_budget`. Returns summaries with section pointers when content exceeds the budget.
- **Knowledge that compounds** — Append-only version history. Every change is a new version. Full audit trail and time-travel reads.
- **Any agent can connect** — MCP server, Python library, or CLI. Optional REST API with `pip install sayou[api]`.

## Quick Start (60 seconds)

### 1. Install
```bash
pip install sayou
```

### 2. Initialize
```bash
sayou init
```

### 3. Connect to Claude Code

Add to `~/.claude/mcp.json`:
```json
{
  "mcpServers": {
    "sayou": { "command": "sayou" }
  }
}
```

That's it. Claude Code now has persistent workspace memory.

## MCP Tools

The agent gets 11 tools (12 with embeddings enabled):

| Tool | Description |
|------|-------------|
| `workspace_write` | Write or update a file (text or binary with YAML frontmatter) |
| `workspace_read` | Read latest or specific version, with optional line range |
| `workspace_list` | List files and subfolders with auto-generated index |
| `workspace_search` | Search by full-text query, frontmatter filters, or chunk-level |
| `workspace_delete` | Soft-delete a file (history preserved) |
| `workspace_history` | Version history with timestamps, or diff between two versions |
| `workspace_glob` | Find files matching a glob pattern |
| `workspace_grep` | Search file contents with context lines |
| `workspace_kv` | Key-value store (get/set/list/delete with optional TTL) |
| `workspace_links` | File links and knowledge graph (get or add links) |
| `workspace_chunks` | Chunk outline or read a specific chunk by index |
| `workspace_semantic_search` | Vector similarity search (requires `SAYOU_EMBEDDING_PROVIDER`) |

## Python API

```python
import asyncio
from sayou import Workspace

async def main():
    async with Workspace() as ws:
        # Write a file with YAML frontmatter
        await ws.write("notes/hello.md", """\
---
status: active
tags: [demo, quickstart]
---
# Hello from sayou
This file is versioned and searchable.
""")

        # Read it back
        doc = await ws.read("notes/hello.md")
        print(doc["content"])

        # Search by frontmatter
        results = await ws.search(filters={"status": "active"})
        print(f"Found {results['total']} active files")

asyncio.run(main())
```

See [`examples/quickstart.py`](examples/quickstart.py) for a runnable version.

## CLI

```bash
# File operations
sayou file read notes/hello.md
sayou file write notes/hello.md "# Hello World"
sayou file list /
sayou file search --query "hello" --filter status=active

# KV store
sayou kv set config.theme '"dark"'
sayou kv get config.theme

# Diagnostics
sayou init      # Initialize local setup
sayou status    # Show diagnostic info
```

## Examples

| Example | What it shows |
|---------|---------------|
| [`quickstart.py`](examples/quickstart.py) | Hello World — write, read, search, list in 30 lines |
| [`kv_config.py`](examples/kv_config.py) | KV store for config, feature flags, caching with TTL |
| [`version_control.py`](examples/version_control.py) | Version history, diff, time-travel reads |
| [`file_operations.py`](examples/file_operations.py) | Move, copy, binary files, glob patterns |
| [`multi_agent.py`](examples/multi_agent.py) | Multi-agent collaboration with shared workspace |
| [`research_agent.py`](examples/research_agent.py) | All methods exercised — the comprehensive reference |

## Installation Options

```bash
# Basic (MCP server + CLI + SQLite)
pip install sayou

# With REST API support
pip install sayou[api]

# With S3 storage
pip install sayou[s3]

# Full installation (all features)
pip install sayou[all]
```

## Production Deployment

For team/production use with MySQL + S3:

```json
{
  "mcpServers": {
    "sayou": {
      "command": "sayou",
      "env": {
        "SAYOU_ORG_ID": "my-org",
        "SAYOU_USER_ID": "alice",
        "SAYOU_DATABASE_URL": "mysql+aiomysql://user:pass@host/sayou",
        "SAYOU_S3_BUCKET_NAME": "my-bucket",
        "SAYOU_S3_ACCESS_KEY_ID": "...",
        "SAYOU_S3_SECRET_ACCESS_KEY": "..."
      }
    }
  }
}
```

Install with all backends: `pip install sayou[all]`

## Storage Backends

| Backend | Config | Use case |
|---------|--------|----------|
| **SQLite + local disk** (default) | No config needed | Local dev, single-machine agents, MCP server |
| **MySQL + S3** | Set `database_url`, S3 credentials | Production, multi-agent, shared workspaces |

## What sayou is NOT

- **Not a vector database.** Pinecone, Weaviate, and Chroma store embeddings for similarity search. sayou stores structured files that agents read, write, and reason over.
- **Not a memory layer.** Mem0 and similar tools store conversation snippets. sayou stores work product — research, client records, project documentation — that compounds over time.
- **Not a sandbox.** E2B provides ephemeral execution environments. sayou provides persistent storage that outlives any single execution.
- **Not a filesystem.** AgentFS intercepts syscalls to virtualize file operations. A knowledge workspace with versioning and indexing.

## Philosophy

Read [PHILOSOPHY.md](./PHILOSOPHY.md) for the founding vision and design principles.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache 2.0 — See [LICENSE](./LICENSE)
