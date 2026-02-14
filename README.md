# sayou

**The persistent workspace for AI agents.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)

sayou gives AI agents persistent, structured, enterprise-controlled storage. Agents write files. Files accumulate. Knowledge compounds.

- **Persistent file workspace** — Versioned files organized in folders. Survives beyond any single conversation.
- **Structured metadata** — YAML frontmatter for queryable fields (`status: active`, `priority: high`). Markdown body for context.
- **Hierarchical auto-indexing** — Every write triggers index regeneration up the folder tree. Agents navigate thousands of files in 3-4 reads.
- **Context-aware retrieval** — Every read accepts a `token_budget`. Returns summaries with pointers when content exceeds the budget.
- **Append-only version history** — No destructive updates. Every change is a new version. Full audit trail and time-travel for free.

## Quickstart: Python API

```bash
pip install sayou
```

```python
import asyncio
from sayou import Workspace

async def main():
    async with Workspace(org_id="my-org", user_id="alice") as ws:
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

        # List a folder
        folder = await ws.list("notes/")
        print(f"{folder['file_count']} files in notes/")

asyncio.run(main())
```

By default this creates a local SQLite database (`./sayou.db`) — zero config, nothing to install.

## Quickstart: MCP Server

Add sayou to Claude Code or any MCP-compatible client:

```json
{
  "mcpServers": {
    "sayou": {
      "command": "sayou",
      "env": {
        "SAYOU_ORG_ID": "my-org",
        "SAYOU_USER_ID": "alice"
      }
    }
  }
}
```

That's it. The agent gets 8 tools: `workspace_write`, `workspace_read`, `workspace_list`, `workspace_search`, `workspace_delete`, `workspace_history`, `workspace_glob`, `workspace_grep`.

## Quickstart: CLI Agent Example

Seed a workspace with sample data, then chat with it using an OpenAI-backed agent:

```bash
pip install sayou[examples]

python examples/seed_data.py      # writes ~28 files across 5 folders
python examples/ask.py            # natural language agent (needs OPENAI_API_KEY)
```

```
ask> what competitors have we analyzed?
  [list_files] {"path": "competitors/", "recursive": false}
  [read_file] {"path": "competitors/notion.md"}

We've analyzed 6 competitors: Notion, Linear, Airtable, Figma, Retool, and Vercel...

ask> add a competitor analysis for Shopify
  [write_file] {"path": "competitors/shopify.md", "content": "---\ncompany: Shopify\n..."}

Wrote competitors/shopify.md (v1, 1,204 bytes)
```

See [`examples/seed_data.py`](examples/seed_data.py) and [`examples/ask.py`](examples/ask.py) for the full source.

## API Reference

All methods are async. The `Workspace` class binds identity (`org_id`, `user_id`) once at construction.

| Method | Signature | Description |
|--------|-----------|-------------|
| `write` | `(path, content, *, source=None)` | Write or update a file. Returns version info. |
| `read` | `(path, *, token_budget=4000, version=None)` | Read latest (or specific) version of a file. |
| `list` | `(path="/", *, recursive=False)` | List files and subfolders with auto-generated index. |
| `search` | `(*, query=None, filters=None)` | Search by full-text query and/or frontmatter filters. |
| `glob` | `(pattern)` | Find files matching a glob pattern (`**/*.md`). |
| `grep` | `(query, *, path_pattern=None, context_lines=2)` | Search file contents for a string, with context. |
| `delete` | `(path, *, source=None)` | Soft-delete a file. Version history is preserved. |
| `history` | `(path, *, limit=20)` | Get version history with timestamps and hashes. |

## Storage Backends

| Backend | Config | Use case |
|---------|--------|----------|
| **SQLite + local disk** (default) | No config needed | Local dev, single-machine agents, MCP server |
| **MySQL + S3** | Set `database_url`, S3 credentials | Production, multi-agent, shared workspaces |

```python
# Local (default) — just works
async with Workspace() as ws: ...

# Production
async with Workspace(
    database_url="mysql+aiomysql://user:pass@host/sayou",
    s3_bucket="my-bucket",
    s3_access_key_id="...",
    s3_secret_access_key="...",
) as ws: ...
```

## What sayou is NOT

- **Not a vector database.** Pinecone, Weaviate, and Chroma store embeddings for similarity search. sayou stores structured files that agents read, write, and reason over.
- **Not a memory layer.** Mem0 and similar tools store conversation snippets. sayou stores work product — research, client records, project documentation — that compounds over time.
- **Not a sandbox.** E2B provides ephemeral execution environments. sayou provides persistent storage that outlives any single execution.
- **Not a filesystem.** AgentFS intercepts syscalls to virtualize file operations. sayou is a knowledge workspace with versioning, indexing, and context-aware retrieval built in.

## Philosophy

Read [PHILOSOPHY.md](./PHILOSOPHY.md) for the founding vision and design principles.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache 2.0 — See [LICENSE](./LICENSE)
