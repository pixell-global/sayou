# sayou

**The persistent workspace for AI agents. Replaces the database layer of every SaaS.**

sayou is an open-source workspace layer that gives AI agents persistent, structured, enterprise-controlled storage. Client records, project plans, research reports, operational data — everything that today lives scattered across dozens of SaaS databases lives in one workspace. Agents write files. Files accumulate. Knowledge compounds.

## What sayou Does

- **Persistent file workspace** — Agents create, read, and update versioned files organized in folders. Research, operational records, project documentation — all in one place. Survives beyond any single conversation.
- **Structured data in files** — YAML frontmatter for queryable fields (`status: active`, `owner: platform-team`, `priority: high`). Markdown body for context. One file replaces a database row, a notes field, and an activity log.
- **Hierarchical auto-indexing** — Every write triggers index regeneration up the folder tree. Agents navigate thousands of files in 3-4 reads, like a B-tree for knowledge.
- **Context-aware retrieval** — Every read accepts a `token_budget`. The system never overwhelms an agent — it returns summaries with pointers when content exceeds the budget.
- **Append-only mutation log** — No updates, no deletes. Every change is a new row. Full version history, time-travel, audit trail, and recovery for free.
- **MCP-first interface** — Built as an MCP server. Tool descriptions are the documentation. Any MCP-compatible agent can connect immediately.

## What sayou Is NOT

- **Not a vector database.** Pinecone, Weaviate, and Chroma store embeddings for similarity search. sayou stores structured files that agents read, write, and reason over. Semantic search is one capability, not the whole product.
- **Not a memory layer.** Mem0 and similar tools store conversation snippets. sayou stores work product and operational data — research, client records, project documentation, institutional knowledge — that compounds over time.
- **Not a sandbox.** E2B provides ephemeral execution environments. sayou provides persistent storage that outlives any single execution.
- **Not a filesystem.** AgentFS intercepts syscalls to virtualize file operations. sayou is a knowledge workspace with versioning, indexing, and context-aware retrieval built in.

## Relationship to Pixell

sayou is to Pixell what Postgres is to every SaaS application. Pixell agents do the work. sayou is where the work product accumulates. sayou is open-source and standalone — any agent framework can use it. Pixell is the commercial platform that builds the best agent experiences on top of it.

## Learn More

Read [PHILOSOPHY.md](./PHILOSOPHY.md) for the founding vision, core principles, and design philosophy behind sayou.

## License

Apache 2.0 — See [LICENSE](./LICENSE)
