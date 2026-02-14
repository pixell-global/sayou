# sayou MVP: Build Spec

This document defines what to build, how to know it works, and how to know it failed. It is a companion to [PHILOSOPHY.md](./PHILOSOPHY.md) — that document defines the beliefs, this one defines the experiment that tests them.

---

## 1. The Minimal Implementation

### 1.1 MCP Tools (6 tools, no more)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `workspace_write` | Create or update a file. If path exists, creates a new version. | `path` (str), `content` (str), optional `source` (agent ID) |
| `workspace_read` | Read a file's current version. | `path` (str), optional `token_budget` (int, default 4000) |
| `workspace_list` | List folder contents. Includes `_index.md` content if present. | `path` (str), optional `recursive` (bool, default false) |
| `workspace_search` | Search by frontmatter fields or full-text. | `query` (str) and/or `filters` (dict) |
| `workspace_delete` | Soft-delete: catalog pointer removed, S3 object preserved. | `path` (str) |
| `workspace_history` | Version history of a file. | `path` (str), optional `limit` (int, default 20) |

Six tools is the ceiling for MVP. Every additional tool increases cognitive load for the LLM and testing surface for us. If an operation can't be expressed through these six, it waits.

**Maps to:** Principle 7 (MCP is the primary interface). Tool descriptions ARE the documentation — an agent reads the schema and knows how to use the workspace.

### 1.2 Storage Backend

Reuses the proven S3 patterns from `pixell-api/app/services/storage.py`:
- `upload_version()` — content upload with checksum calculation
- `download_file()` — content retrieval by S3 key
- `calculate_checksum()` — SHA-256 for content deduplication detection

**S3 key structure:**

```
{org_id}/sayou/{workspace_id}/v/{version_uuid}
```

This differs from the existing file storage key structure (`{org_id}/files/{file_id}/versions/{version_id}/{filename}`) intentionally — sayou versions are addressed by UUID alone, not by file ID. The filename is metadata in the catalog, not part of the storage path.

**Local development:** MinIO with the same S3-compatible API. The existing `StorageService` already supports custom endpoints via `settings.s3_endpoint_url` — no code changes needed for local dev.

**Maps to:** Principle 6 (cloud-native by default, local by choice). S3 is the source of truth. MinIO is the local mirror. Same code, same interface.

### 1.3 Catalog Schema

Six tables in the existing pixell-api MySQL database. Separate from the existing `files`/`file_versions`/`local_files` tables — clean separation, no coupling with the file editor feature.

**`sayou_workspaces`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | char(36) | UUID primary key |
| `org_id` | char(36) | FK to organizations.id, NOT NULL |
| `name` | varchar(255) | Human-readable name (e.g., "Engineering", "HR") |
| `slug` | varchar(255) | URL-safe identifier, unique within org |
| `created_by` | varchar(128) | User who created the workspace |
| `created_at` | timestamp | |

Indexes:
- `UNIQUE (org_id, slug)` — one workspace per slug per org

Every org gets a `default` workspace on first sayou interaction. Additional workspaces are created explicitly.

**`sayou_workspace_members`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | char(36) | UUID primary key |
| `workspace_id` | char(36) | FK to sayou_workspaces.id, NOT NULL |
| `user_id` | varchar(128) | FK to users.id, NOT NULL |
| `role` | varchar(20) | `reader`, `writer`, `admin` |
| `created_at` | timestamp | |

Indexes:
- `UNIQUE (workspace_id, user_id)` — one role per user per workspace
- `(user_id)` — "which workspaces can this user access?"

Roles:
- **reader** — `workspace_read`, `workspace_list`, `workspace_search`, `workspace_history`
- **writer** — everything a reader can do, plus `workspace_write`, `workspace_delete`
- **admin** — everything a writer can do, plus workspace management (invite members, change roles)

The org creator is automatically `admin` on the `default` workspace. Access check runs on every MCP tool call — no membership row means no access.

**`sayou_files`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | char(36) | UUID primary key |
| `org_id` | char(36) | FK to organizations.id, NOT NULL |
| `workspace_id` | char(36) | FK to sayou_workspaces.id, NOT NULL |
| `path` | varchar(1024) | Full path within workspace (e.g., `research/trends/2025-02-14.md`) |
| `folder_path` | varchar(1024) | Parent folder (e.g., `research/trends/`). Extracted from `path` for folder queries. |
| `filename` | varchar(255) | Filename without path |
| `content_type` | varchar(127) | MIME type, default `text/markdown` |
| `frontmatter` | JSON | Extracted YAML frontmatter as queryable JSON |
| `current_version_id` | char(36) | FK to sayou_file_versions.id, nullable (null = soft-deleted) |
| `version_count` | int | Denormalized count for fast history queries |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |
| `deleted_at` | timestamp | Nullable. Soft delete. |

Indexes:
- `UNIQUE (org_id, workspace_id, path)` — one file per path per workspace
- `(org_id, workspace_id, folder_path)` — folder listing queries
- `(org_id, workspace_id, deleted_at)` — active file queries

**`sayou_file_versions`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | char(36) | UUID primary key |
| `file_id` | char(36) | FK to sayou_files.id, NOT NULL |
| `version_number` | int | Auto-incrementing per file, starting at 1 |
| `s3_key` | varchar(512) | Storage pointer |
| `s3_bucket` | varchar(255) | Bucket name |
| `size_bytes` | bigint | Content size |
| `content_hash` | varchar(64) | SHA-256 checksum |
| `created_by` | varchar(128) | Agent or user ID who created this version |
| `created_at` | timestamp | Immutable — set once, never updated |

Indexes:
- `UNIQUE (file_id, version_number)` — version ordering guarantee
- `(file_id, created_at)` — history queries

Follows the same append-only pattern as `pixell-api/app/models/file_version.py`: versions are immutable rows. The only mutable pointer is `sayou_files.current_version_id`.

**Maps to:** Principle 2 (everything is an append). Never UPDATE a content row. Never DELETE a content row.

**`sayou_index_cache`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | char(36) | UUID primary key |
| `org_id` | char(36) | FK to organizations.id, NOT NULL |
| `workspace_id` | char(36) | FK to sayou_workspaces.id, NOT NULL |
| `folder_path` | varchar(1024) | The folder this index describes |
| `content` | text | Pre-computed `_index.md` content |
| `file_count` | int | Number of files summarized |
| `updated_at` | timestamp | Last regeneration time |

Indexes:
- `UNIQUE (org_id, workspace_id, folder_path)`

**`sayou_mutation_log`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | bigint | Auto-increment primary key (not UUID — high-volume, sequential) |
| `org_id` | char(36) | NOT NULL |
| `workspace_id` | char(36) | NOT NULL |
| `agent_id` | varchar(128) | Who performed the action |
| `action` | varchar(20) | `write`, `delete`, `revert` |
| `file_path` | varchar(1024) | Target file |
| `version_id` | char(36) | Nullable. The version created (for writes). |
| `created_at` | timestamp | |

Indexes:
- `(org_id, workspace_id, created_at)` — audit queries
- `(org_id, agent_id, created_at)` — per-agent audit

**Maps to:** Scenario I (audit and transparency). Every action is recorded. Every agent's work is attributable.

### 1.4 Index Generation (MVP Simplifications)

PHILOSOPHY.md describes asynchronous index propagation up the full folder tree (Principle 4). The MVP implements a simplified version:

| Aspect | Philosophy | MVP |
|--------|-----------|-----|
| Timing | Asynchronous | **Synchronous** — inside `workspace_write`, before returning |
| Propagation | Full chain to root | **One level up only** — regenerates immediate parent folder's `_index.md` |
| Root index | Always current | Regenerated **on schedule** — every N writes, or on explicit `workspace_list` of root |
| Content | LLM-generated summaries | **Template-based** — structured table from file metadata |

Template output for a folder index:

```markdown
# research/trends/

Last updated: 2025-02-14T15:30:00Z | 12 files

| File | Status | Tags | Updated |
|------|--------|------|---------|
| 2025-02-14.md | draft | [market, asia] | 2025-02-14 |
| 2025-02-13.md | published | [market, competitors] | 2025-02-13 |
| ...  | | | |
```

Frontmatter fields are extracted dynamically — the template includes whatever fields exist across the folder's files. No hardcoded field list.

This is **deterministic, fast, and free**. No LLM API calls. The trade-off: indexes are less useful than LLM-generated summaries. We accept this trade-off for MVP and add LLM summaries as a fast follow when we have usage data to justify the cost.

**Why synchronous:** Correctness over performance. An agent that writes a file and immediately lists the folder should see the updated index. Async propagation introduces a consistency window where the index is stale. For MVP write volumes, synchronous is fast enough.

**Why one level up:** Full chain propagation is an optimization for large workspaces. With MVP file counts (sub-1000), a stale root index is an inconvenience, not a failure. The root regenerates on demand when an agent lists `/`.

### 1.5 MCP Server

Uses the `mcp` Python package with `FastMCP`:

```
sayou/
  sayou/
    server/
      __init__.py       # FastMCP instance, 6 tool registrations
    core/
      __init__.py       # Business logic: write, read, list, search, delete, history
      index.py          # Index generation logic
      frontmatter.py    # YAML frontmatter parser (maximally lenient)
    storage/
      __init__.py       # Thin wrapper on StorageService patterns
    catalog/
      __init__.py       # SQLAlchemy models and queries
```

~200-300 lines for the MCP server layer. Each tool is a thin function that validates parameters, calls into `sayou/core/`, and returns results.

**Transport modes:**
- **stdio** — for Claude Code. User adds sayou to their MCP config, Claude Code spawns it as a subprocess.
- **streamable-http** — for programmatic access and future pixell-one integration.

**Auth in MVP:** The MCP server receives `org_id` and `user_id` via configuration (environment variable or MCP initialization). All operations are scoped to that org and checked against `sayou_workspace_members` for the target workspace. Full JWT validation is deferred — MVP trusts the process boundary (Claude Code runs locally, the user is the org). But workspace-level access is enforced: a user without a membership row for a workspace cannot read or write to it.

### 1.6 What is Explicitly Deferred

| Feature | Why deferred | When it matters |
|---------|-------------|-----------------|
| KV store | Principle 5, but no agent needs transient state yet | When agents need session flags or rate limiting |
| Vector/semantic search | SQL LIKE + frontmatter filters may be sufficient for MVP file counts | When search quality becomes a validated bottleneck |
| LLM-powered index summaries | Template-based is free and deterministic | When we have cost data and user feedback on index quality |
| Async index propagation | Synchronous is correct and fast enough for MVP volumes | When write latency exceeds 1s due to index regen |
| Full upward index chain | One level is sufficient for <1000 files | When workspaces grow past 1000 files |
| ~~Multi-workspace~~ | ~~Moved to MVP~~ | N/A — included |
| ~~Workspace-level permissions~~ | ~~Moved to MVP~~ | N/A — included |
| REST API | MCP is the interface; REST is for dashboards | When we build admin UI or programmatic access patterns |
| CLI tools | MCP via Claude Code is the UX | When non-agent users need direct workspace access |
| Binary file support | Markdown-only for MVP | When agents need to store images, PDFs, etc. |
| Conflict detection/resolution | Last-write-wins with full history | When concurrent multi-agent writes cause user-visible issues |
| Retention policies | All versions kept forever | When storage costs become material |
| SQLite/local-only mode | MinIO + MySQL locally is equivalent | When open-source users need zero-dependency local mode |
| PER executor integration | Agents access sayou via MCP, not PER tools | Fast follow after MVP validates the workspace model |

Each deferral is a bet: we believe MVP can prove the thesis without this feature. If we're wrong, the failure criteria (Section 3) will tell us.

### 1.7 Build Order

1. **Catalog schema + Alembic migrations** — Tables, indexes, constraints. Run `alembic upgrade head` to verify.
2. **Storage adapter** — Thin wrapper reusing `StorageService.upload_version()`, `download_file()`, `calculate_checksum()` patterns. New key structure: `{org_id}/sayou/{workspace_id}/v/{version_uuid}`.
3. **Core logic** — `write()`, `read()`, `list()`, `search()`, `delete()`, `history()`. Index generation in `write()`. Frontmatter parser.
4. **MCP server** — FastMCP with 6 tools, each calling core logic. stdio transport.
5. **Integration tests** — Write-read cycle, version history, search, index generation, org isolation, workspace access control.

Each step is independently testable. Step 1 produces a migration that can be run and rolled back. Step 2 produces functions that can be unit-tested against MinIO. Steps 3-4 compose into an end-to-end MCP flow.

---

## 2. Success Criteria

### Technical Success (it works)

These are binary pass/fail tests. Run them after building each component.

**S1: Write-read cycle.** Write a Markdown file with YAML frontmatter to `research/test.md`. Read it back. Content is byte-identical. Version number is 1. Frontmatter is parsed and stored in catalog JSON column. File appears in `sayou_files` with correct path, folder_path, filename, and frontmatter.

**S2: Index generation produces navigable output.** Write 10 files across 3 folders (`research/trends/`, `research/competitors/`, `clients/`). Each folder's `_index.md` cache accurately lists all files in that folder with their frontmatter fields. `workspace_list("research/")` returns subfolder names and the index content.

**S3: Search finds files by frontmatter.** Write 5 files, 3 with `status: active` and 2 with `status: archived` in frontmatter. `workspace_search(filters={"status": "active"})` returns exactly the 3 matching files. Full-text `workspace_search(query="competitive analysis")` returns files containing that phrase.

**S4: Version history is preserved.** Write to the same path 5 times with different content. `workspace_history("path")` returns 5 versions in order. Each version has the correct `version_number`, `content_hash`, `created_by`, and `created_at`. Reading the current version returns the 5th write's content. The `sayou_files.version_count` is 5.

**S5: Org isolation enforced.** Two different org_ids write to the identical path `research/test.md`. Each org has its own independent file. Listing, searching, and reading for org A never returns org B's data. S3 keys are in separate key namespaces (`{org_a}/sayou/...` vs `{org_b}/sayou/...`).

**S6: Workspace isolation enforced.** User A is a member of workspace "engineering" but not "hr". User A's `workspace_read`, `workspace_list`, `workspace_search` calls against "hr" are rejected. User B, who is a member of "hr", can access it normally. A `reader` cannot call `workspace_write`. An `admin` can do everything.

**S7: Claude Code can connect and use the workspace.** The MCP server runs via stdio. A user adds sayou to their Claude Code MCP config. Claude Code discovers the 6 tools. The user instructs Claude to save research findings — Claude calls `workspace_write`. The user asks "what research do we have?" — Claude calls `workspace_list` and/or `workspace_search` and returns relevant results.

**S8: Write latency under 1 second.** A `workspace_write` call — including S3 upload, catalog insert, frontmatter extraction, one-level index regeneration — completes in under 1 second for files up to 50KB. Measured end-to-end from MCP tool call to response, on local development stack (MinIO + MySQL).

### Thesis Validation (the model is right)

These require qualitative assessment after a week of real usage, not automated testing.

**S9: Knowledge compounds across sessions.** An agent in session 2 reads and builds upon findings from session 1, without access to session 1's chat history. The workspace bridges the gap. Evidence: the agent's output in session 2 references specific content from session 1's files.

**S10: Indexes enable efficient navigation.** A workspace with 50+ files is navigable in 3 reads from root: read root index, read subfolder index, read target file. An agent does not need to list every file or guess at paths.

**S11: Agents naturally adopt the workspace.** Given the 6 tools and a brief system prompt mention ("You have access to a persistent workspace via sayou. Use it to save and retrieve research, findings, and work product."), an agent voluntarily saves work in at least 6 out of 10 tasks without the user explicitly saying "save this." Evidence: mutation log shows agent-initiated writes across diverse tasks.

**S12: Structured frontmatter is useful.** At least 70% of agent-written files have non-trivial frontmatter (3 or more fields). Evidence: query `sayou_files` where `JSON_LENGTH(frontmatter) >= 3` and compare against total files. If agents write bare Markdown without frontmatter, the structured data thesis needs rethinking.

---

## 3. Failure Criteria

Failures are categorized by what they tell us. Architecture failures mean the approach is wrong. Implementation failures mean we built the wrong thing. Both are valuable signals.

### Architecture Failures (the approach is fundamentally wrong)

**F1: MCP tools too chatty.** Agents need 4+ tool calls for a single logical operation (e.g., write a file, then list to verify, then search to confirm indexing, then read to double-check). This means the tool surface is wrong — operations should be more atomic or return richer responses. *Mitigation:* Each tool returns enough context to avoid follow-up calls (e.g., `workspace_write` returns the version number and confirms index update).

**F2: Index generation too slow or too expensive.** Write latency exceeds 2 seconds due to index regeneration. Or, when LLM summaries are added later, index generation costs more than $0.001 per write. *Mitigation for MVP:* Template-based generation is effectively free and runs in milliseconds. This failure would only surface when upgrading to LLM-based summaries.

**F3: File abstraction provides no value over raw S3.** Agents use random file names, ignore folder structure, skip frontmatter, and never read indexes. The workspace is "just S3 with metadata." This means files-as-knowledge-units is the wrong abstraction, and we should consider structured databases or knowledge graphs instead. *Detection:* Review mutation log and file naming patterns after 100+ files.

**F4: Append-only creates unacceptable storage growth.** Frequent updates to the same file create linear storage growth. *Reality check:* A 10KB file updated 1,000 times = 10MB = $0.0002/month at S3 Standard pricing. This is almost certainly a non-issue, but worth monitoring. Retention policies (deferred) are the mitigation if it becomes material.

**F5: Agents don't naturally adopt workspace patterns.** The existential risk. If agents ignore the workspace unless explicitly told "save this" every time, the thesis fails. The workspace becomes a fancy clipboard — useful only when the user remembers to invoke it. *Implication:* If this happens, workspace may need automatic injection into the agent loop (save-on-every-response) rather than optional tool use. This would be a fundamental architecture change, not a tweak.

### Implementation Failures (we built the wrong thing)

**F6: Frontmatter parsing is fragile.** Agents write messy YAML — inconsistent indentation, unquoted strings with colons, missing closing `---`. If more than 5% of writes fail on parse errors, the parser is too strict. *Mitigation:* Parser must be maximally lenient. Accept missing closing `---`. Accept bare key-value pairs. Fall back to empty frontmatter on parse failure rather than rejecting the write. The file content is always saved regardless of frontmatter quality.

**F7: Search useless without vector embeddings.** SQL `LIKE` queries and frontmatter JSON filters return irrelevant results, and agents stop using `workspace_search`. *Detection:* Search usage drops to near zero in mutation log while `workspace_list` + `workspace_read` (manual navigation) stays high. *Implication:* Vector search moves from "deferred" to "required for MVP v2."

**F8: Single-level index regen insufficient.** Root folder doesn't know about files in deeply nested subdirectories. Navigation model breaks because the root `_index.md` is always stale or empty. *Mitigation:* Root index regeneration on `workspace_list("/")` calls. If agents frequently list root and get stale data, upgrade to full-chain propagation.

**F9: MVP too minimal to prove anything.** If honest assessment after building is "this is just S3 with metadata and a YAML parser," we cut too deep. The differentiating features — indexes, version history, frontmatter queries, agent attribution — must be tangibly useful, not just technically present. *Detection:* After a week of usage, can you point to a specific moment where the workspace enabled something that raw file storage couldn't?

### Operational Risks

**F10: Performance degrades non-linearly.** Catalog queries slow down at 1,000+ files due to missing or inadequate SQL indexes. Full table scans on `sayou_files` for folder listings or searches. *Mitigation:* Indexes on `(org_id, workspace_id, folder_path)` and `(org_id, workspace_id, path)` are in the schema from day one. Run `EXPLAIN` on all catalog queries during integration testing with 1,000 synthetic files.

---

## 4. Mapping to Philosophy

Every MVP decision traces back to a PHILOSOPHY.md principle or explicitly notes the deferral.

| MVP Decision | Philosophy Principle | Status |
|-------------|---------------------|--------|
| 6 MCP tools | P7: MCP is the primary interface | Implemented |
| Markdown files with YAML frontmatter | P1: Files are the unit of knowledge | Implemented |
| Append-only versions | P2: Everything is an append | Implemented |
| `token_budget` on read | P3: Context-aware retrieval | Implemented |
| Template-based indexes | P4: Indexes grow upward | Simplified (template, not LLM; one level, not full chain) |
| No KV store | P5: Two storage tiers | Deferred (no agent needs it yet) |
| S3 + MySQL | P6: Cloud-native by default | Implemented |
| MCP server (not REST) | P7: MCP is the primary interface | Implemented |
| Org + workspace isolation | Multi-tenancy section | Implemented (org boundary + workspace membership with reader/writer/admin roles) |
| Mutation log | Scenario I: Audit and transparency | Implemented |
| Separate tables from existing files | — | Architectural choice for clean separation |
