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

## Quick Start

### Claude Code (recommended)

From within Claude Code:

```
/plugin install sayou@pixell-global
```

Or from the terminal:

```bash
claude plugin install sayou@pixell-global
```

One command. This installs the plugin with lifecycle hooks (workspace context on session start, passive activity capture, session summaries) and skills (`/ws`, `/save`, `/recall`). If `sayou` isn't installed yet, the plugin auto-installs it on first run.

> **Cloud mode**: To sync your workspace via [Sayou Drive](https://drive.sayou.dev), run `sayou auth` after installing and paste your API key from [Settings](https://drive.sayou.dev/settings).

### pip install

```bash
pip install sayou && sayou init --claude
```

This installs sayou and configures `~/.claude/mcp.json`. You get the 11 MCP tools but no hooks or skills. You can also use `--cursor` or `--windsurf`, or run `sayou init` without flags to get the config snippet to paste manually.

To verify either method, run `sayou status` — you should see your workspace path, database location, and `11 tools registered`. If you see errors, jump to [Troubleshooting](#troubleshooting).

## Try It

Open Claude Code and paste any of these prompts. Each one triggers a different MCP tool — no setup beyond the Quick Start above.

| Prompt | What happens | Tool |
|--------|-------------|------|
| "Save a note about our Q1 goals with status: draft" | Creates a versioned file with YAML frontmatter | `workspace_write` |
| "What files are in my workspace?" | Lists all files and subfolders | `workspace_list` |
| "Search for anything tagged status: draft" | Filters files by frontmatter metadata | `workspace_search` |
| "Read the Q1 goals note" | Retrieves file content with token-budget awareness | `workspace_read` |
| "Update the status to reviewed" | Writes a new version (old version preserved) | `workspace_write` |
| "Show me the diff between versions" | Compares two versions with unified diff | `workspace_history` |
| "Store a setting: theme = dark" | Saves a key-value pair (with optional TTL) | `workspace_kv` |
| "Find all markdown files in research/" | Matches files by glob pattern | `workspace_glob` |
| "Search file contents for the word 'budget'" | Grep-style content search with context | `workspace_grep` |

Every write creates a new version. Nothing is overwritten. You can always go back.

## What It Looks Like

A short conversation showing sayou in action across sessions:

---

**You:** Research competitor pricing for our enterprise tier and save your findings.

**Claude Code:** I'll research this and save my findings to the workspace.

*[Uses `workspace_write` to create `research/competitor-pricing.md`]*

> Saved to `research/competitor-pricing.md` with frontmatter:
> status: draft, topic: competitor-pricing

---

**You** *(next day, new session):* What did we learn about competitor pricing?

**Claude Code:** Let me check our workspace.

*[Uses `workspace_search` with query "competitor pricing"]*

> Found `research/competitor-pricing.md` (saved yesterday):
> - Competitor A: $99/seat/month
> - Competitor B: $149/seat/month (includes support)
> - Competitor C: $79/seat/month (limited features)

---

**You:** Update the status to "reviewed" and show me the diff.

**Claude Code:** *[Uses `workspace_write` to create version 2, then `workspace_history` to diff]*

> ```diff
> - status: draft
> + status: reviewed
> + reviewer_notes: |
> +   Competitor B is closest to our positioning.
> ```

---

The key insight: Claude Code remembered the research **across sessions** because sayou persisted it as a versioned file — not a chat message that disappears.

## Setup for Other Editors

### Cursor

```bash
sayou init --cursor
```

This adds sayou to `.cursor/mcp.json` in your current working directory.

### Windsurf

```bash
sayou init --windsurf
```

This adds sayou to `~/.codeium/windsurf/mcp_config.json`.

### Any MCP-compatible client

sayou is a standard MCP server. Run `sayou init` (no flag) to get the config snippet, then paste it into your editor's MCP config. The entry is always the same — just `"command": "sayou"`.

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

# Cloud authentication
sayou auth            # Connect to Sayou Drive (interactive)
sayou auth status     # Show current mode (cloud/local)
sayou auth logout     # Disconnect from Sayou Drive

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

## Reference Agent

sayou ships with a reference agent server — a multi-turn assistant that can search, read, write, and research using your workspace. It's a complete working example of building an agent on sayou.

### Quick start

```bash
# Install with agent dependencies
pip install sayou[agent]

# Configure (copy and fill in your OpenAI key)
cp agent/.env.example .env

# Run the agent server
python -m sayou.agent
```

The agent runs on `http://localhost:9008` with a streaming SSE endpoint at `POST /chat/stream`.

### What the agent can do

| Capability | How it works |
|------------|-------------|
| **Answer questions** | Searches workspace first, falls back to web search |
| **Research topics** | Multiple web searches, extracts facts, saves structured findings |
| **Store knowledge** | Writes files with YAML frontmatter, section headings, source citations |
| **Execute code** | Optional E2B sandbox for Python and bash (set `SAYOU_AGENT_E2B_API_KEY`) |

### Evaluate the agent

```bash
# Start agent in one terminal
python -m sayou.agent

# Quick pass/fail eval
python -m sayou.agent.benchmarks.eval

# Detailed scoring (0-10 per capability)
python -m sayou.agent.benchmarks.eval_full
```

### Architecture

```
Client → FastAPI (port 9008)
         ↓
      Orchestrator
         ├─ LLMProvider (OpenAI streaming + tool calls)
         ├─ ToolFactory
         │  ├─ workspace_search/read/list/write (→ sayou SDK)
         │  ├─ web_search (→ Tavily API, optional)
         │  └─ execute_bash/python (→ E2B sandbox, optional)
         └─ SandboxManager (per-session isolation, auto-cleanup)
```

## SAMB: Structured Agent Memory Benchmark

sayou includes SAMB — an open benchmark for evaluating memory systems on real agentic workflows. Existing benchmarks (LOCOMO, LongMemEval, DMR) test conversation recall. SAMB tests what agents actually need: recalling decisions, retrieving artifact contents, and connecting knowledge across sessions.

### What SAMB measures

| Dimension | What it tests |
|-----------|---------------|
| **Decision reasoning** | "Why was bcrypt chosen over Argon2?" |
| **Artifact content** | "What endpoints are in the API docs?" |
| **Cross-session** | "How does session 3's auth decision affect session 5's implementation?" |
| **Fact recall** | "What was the monthly GCP cost estimate?" |
| **Temporal** | "What changed between the first and second architecture review?" |

10 scenarios, 62 sessions, 131 QA pairs across 7 question types. Each scenario simulates a multi-session professional project (auth system design, cloud migration, email campaigns, incident response, etc.) with realistic conversations, decisions, and artifacts.

### Run the benchmark

```bash
# Prerequisites: pip install sayou mem0ai zep-cloud
# Requires: OPENAI_API_KEY (for judge/answer models)
#           ZEP_API_KEY (for zep adapter)

# Run all adapters on all scenarios
python -m benchmarks.runner.cli

# Specific adapters
python -m benchmarks.runner.cli --adapter sayou mem0

# Specific scenarios
python -m benchmarks.runner.cli --adapter sayou --scenario 01 03 08

# Verbose output (per-question scores)
python -m benchmarks.runner.cli --verbose

# Override judge/answer models
python -m benchmarks.runner.cli --judge-model gpt-4o --answer-model gpt-4o
```

Results are saved to `benchmarks/results/` as JSON with full per-question breakdowns.

### Available adapters

| Adapter | System | Retrieval approach |
|---------|--------|-------------------|
| `sayou` | sayou workspace | FTS5 + grep + file read (agentic, multi-tool) |
| `mem0` | mem0 | LLM fact extraction + embedding search (agentic) |
| `zep` | Zep Cloud | Knowledge graph + temporal edges (agentic) |
| `oracle` | Baseline | Direct access to source sessions (upper bound) |
| `no_memory` | Baseline | No retrieval (lower bound) |

### Methodology

Each adapter uses agentic retrieval — an LLM generates multiple search queries rather than a single-shot lookup. This gives every system a fair chance at finding relevant information.

Scoring: LLM-judged (gpt-4o-mini) on a 0–3 scale, normalized to percentage. Task-type questions add holistic scoring (1–5) and evidence coverage (per-item FOUND/MISSING). Statistical significance via bootstrap confidence intervals with Bonferroni correction.

Full methodology: [`benchmarks/dataset/METHODOLOGY.md`](benchmarks/dataset/METHODOLOGY.md)
Dataset card: [`benchmarks/dataset/DATASET_CARD.md`](benchmarks/dataset/DATASET_CARD.md)

## Installation Options

```bash
# Basic (MCP server + CLI + SQLite)
pip install sayou

# With REST API support
pip install sayou[api]

# With S3 storage
pip install sayou[s3]

# With reference agent server
pip install sayou[agent]

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

## Troubleshooting

### Verify your setup

```bash
sayou status
```

This shows your workspace path, database location, storage backend, and tool count. If everything is working, you'll see `11 tools registered`.

### Common issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Claude Code doesn't see sayou tools | MCP config not loaded | Restart Claude Code after editing `~/.claude/mcp.json` |
| `sayou: command not found` | Not on PATH | Run `pip install sayou` again, or use full path in MCP config: `"command": "/path/to/sayou"` |
| `sayou status` shows 0 tools | Server didn't initialize | Run `sayou init` first, then check for errors in output |
| Files not persisting | Wrong workspace path | Check `sayou status` for the workspace path — default is `~/.sayou/` |
| Import errors on startup | Missing optional dependency | Install the extra you need: `pip install sayou[api]`, `sayou[s3]`, or `sayou[all]` |

### Get help

- [GitHub Issues](https://github.com/pixell-global/sayou/issues) — bug reports and feature requests
- [CONTRIBUTING.md](./CONTRIBUTING.md) — development setup and contribution guide

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

<!-- mcp-name: io.github.pixell-global/sayou -->
