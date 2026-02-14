# sayou: Founding Philosophy

## The Name

**sayou** (채움) is the Korean noun form of "to fill" (채우다). It means "filling up" — the act of making something full, complete, substantial.

We chose this name because it captures what the project does at its core: agents fill a workspace with knowledge, and over time that workspace becomes full — rich, complete, and deeply useful. Each file written is an act of 채움. The workspace is never "done"; it is always being filled.

---

## Vision

Two observations drive this project.

### 1. Every enterprise SaaS is a database wrapper

Salesforce, Notion, Jira, HubSpot, Asana, ServiceNow, Monday — strip away the UI and they are all structured databases with specialized schemas. A CRM is a database of contacts, deals, and activities. A project management tool is a database of tasks, statuses, and assignments. A legal case manager is a database of matters, documents, and deadlines.

Organizations pay tens of thousands per month across dozens of tools, each locking data into proprietary tables that don't talk to each other. The "integrations" between them are fragile bridges between walled gardens.

With LLMs that can dynamically create, query, and manage structured knowledge, you don't need those databases anymore. An agent that can read and write files, maintain indexes, and answer questions about accumulated knowledge replaces the database layer of every SaaS.

A contact is a file. A project is a folder of task files. A case is a folder of evidence and notes. A product listing is a file. A policy document is a file. The folder structure is the schema. YAML frontmatter is the structured fields. The Markdown body is the context an agent needs. No proprietary tables. No vendor lock-in.

**sayou is that database layer — but made of files, not tables.**

### 2. AI agents are brilliant amnesiacs

Today's AI agents can research, analyze, write, and reason at superhuman levels. But when the conversation ends, everything the agent learned disappears. The next conversation starts from zero.

There is no persistent, enterprise-controlled place for agents to accumulate organizational knowledge. Memory products store conversation snippets. Vector databases store embeddings. Neither stores the actual *work product* — the research reports, client profiles, project plans, policy documents, and institutional knowledge that compound over time.

**sayou gives agents a workspace that grows smarter over time** — auto-indexed, context-aware, semantically searchable, fully auditable, and sovereign to the enterprise.

### The combination

Agents that DO the work (Pixell) + a persistent workspace where work product ACCUMULATES (sayou) = every SaaS replaced by a single intelligent workspace.

The agent does the research and stores the findings. It manages client records and updates deal stages. It tracks projects and maintains institutional knowledge. The next agent reads what the last one produced. Knowledge compounds. Operational data stays current. The workspace fills up.

### Honest boundary

sayou replaces the database layer of SaaS across every domain — CRMs, project management, legal, engineering, analytics, HR, you name it. But we are precise about scope.

Genuinely transactional systems — banking ledgers, payment processing, inventory counts — still need ACID-compliant relational databases for the ledger itself. A double-entry accounting system that processes thousands of concurrent transactions needs serializable isolation guarantees that a file-based workspace does not provide.

But even transactional SaaS is 80% knowledge work. The categorization rules, the approval workflows, the compliance reports, the customer communication templates, the analytics dashboards — all of that is knowledge work that sayou handles. The ledger is the 20% that remains relational.

---

## Core Principles

### 1. Files are the unit of knowledge

Not rows in a database. Not embeddings in a vector store. Not nodes in a knowledge graph. **Files in folders.**

This is a deliberate choice. Files are:
- **Human-readable** — Open them in any editor, any OS, any decade from now
- **LLM-native** — Language models process text naturally; no serialization/deserialization overhead
- **Composable** — A folder is a namespace. A subfolder is a sub-namespace. The hierarchy is the schema.
- **Portable** — Copy the folder tree to any system and the knowledge works
- **Structurable** — YAML frontmatter carries structured fields (status, priority, owner, tags). The Markdown body carries context. One file holds what a SaaS splits across a database row, a notes field, an activity log, and three linked tables.

This applies equally to research (a market report is a file), operational data (a client profile is a file), and assets (a design file with metadata). The folder structure replaces the database schema: `clients/` is the "clients table," `projects/q3-migration/` is the "project record," `policies/` is the "policy repository." But unlike database tables, these are self-describing, version-controlled, and readable by any agent without a schema definition.

The metadata catalog indexes the file tree for fast queries, but the files in storage are the source of truth. If the catalog disappears, rebuild it by scanning the files. If the files disappear, you've lost the data — because the files ARE the data.

### 2. Everything is an append

Never UPDATE a content row. Never DELETE a content row. Every mutation is a new row with a new version number.

This gives us for free:
- **Full version history** — Every state the file has ever been in is preserved
- **Audit trail** — Who changed what, when, and the exact content before and after
- **Time travel** — "What did our competitive analysis say on January 15th?"
- **Recovery** — Bad data? Roll back to any previous version
- **Conflict resolution** — Concurrent writes both succeed; the version chain shows what happened

The only mutable state is the `current_version` pointer in the metadata catalog, and even that is an atomic swap, not an in-place edit.

### 3. Context-aware retrieval

Every read operation accepts a `token_budget` parameter. The system never dumps 50,000 tokens on an agent that can only handle 4,000.

When content exceeds the budget:
- Return a **summary** of the content
- Include **pointers** to the full content (file paths, section references)
- Let the agent decide what to drill into

This principle extends to indexes, search results, and folder listings. The workspace always fits within the agent's context window, regardless of how large the workspace grows.

### 4. Indexes grow upward

When an agent writes a file, the system triggers asynchronous index regeneration up the folder tree:
1. The file is written to `research/trends/2025-02-14.md`
2. `research/trends/_index.md` is regenerated to reflect the new file
3. `research/_index.md` is regenerated to reflect the updated `trends/` summary
4. The root `_index.md` is regenerated to reflect the updated `research/` summary

The root `_index.md` is always kept under 500 tokens — a compressed map of the entire workspace. An agent can read it and know where everything is. Then drill into any branch with one more read.

This makes the workspace navigable like a B-tree. An agent can find any piece of knowledge in 3-4 reads, regardless of whether the workspace contains 100 files or 100,000 files.

### 5. Two storage tiers, one interface

**Files** — Versioned, indexed, searchable. For knowledge that accumulates and compounds. Research reports, analyses, templates, institutional knowledge.

**Key-Value** — Fast, TTL-capable, not indexed. For transient state. Agent preferences, cursor positions, session flags, rate limit counters.

Same workspace. Same authentication. Same API. Different characteristics. An agent doesn't need to think about which storage system to use — files for knowledge, KV for state.

### 6. Cloud-native by default, local by choice

The architecture has two layers:

- **Object storage** (S3, MinIO, GCS, Azure Blob) — stores file content. This is where the actual knowledge lives. Durable, cheap, scales infinitely.
- **Relational database** (MySQL, PostgreSQL, SQLite) — stores the metadata catalog. This is the index, not the content.

If the catalog disappears, rebuild it from object storage. If object storage disappears, the data is gone. The catalog is expendable; the files are not.

The design center is cloud — object storage + a relational database, serving multiple agents across an organization. This is where the hard problems live: concurrent access, consistency, index propagation, access control.

Local development uses MinIO + SQLite (or any SQL database), running identically to cloud. A developer can run the full system on a laptop. But we don't design for local-first and then try to make it work in the cloud — we design for cloud-native and make sure it also works locally.

### 7. MCP is the primary interface

The Model Context Protocol (MCP) server is the first-class interface. Not a REST API. Not a Python library. An MCP server that any compatible agent can connect to immediately.

Why MCP first:
- **Tool descriptions are documentation** — An agent reads the tool schema and knows how to use the workspace. No SDK to install, no docs to read.
- **Framework-agnostic** — Works with Claude, GPT, open-source models, any agent framework that supports MCP.
- **Natural fit** — Agents calling tools is the native interaction pattern. A REST API is one level of indirection removed.

The REST API exists for programmatic access, dashboards, and admin tools. The Python library exists for deep integration. But the MCP server is where design energy is focused.

---

## Scenarios

These scenarios ground the principles in real-world use. They deliberately span different industries and use cases — because sayou is infrastructure, not a vertical product.

### A. Knowledge that compounds over time

An agent runs daily industry research for an organization. Day 1, it writes `research/market/2025-02-14.md`. Day 30, it has 30 daily reports.

On day 30, the agent reads `research/market/_index.md` — a 400-token summary of all 30 reports with key themes, emerging trends, and notable shifts. It uses this accumulated context to write a monthly synthesis that references specific daily findings.

Without sayou, day 30's agent starts from scratch. With sayou, it builds on 30 days of accumulated intelligence. This applies whether the research is market trends, legal precedents, security vulnerabilities, or academic literature.

### B. Operational records as files

A consulting firm manages 200 active client engagements. Today this lives across a CRM, a project management tool, and a document management system. In sayou, each client is a file:

```markdown
---
company: Acme Corp
status: active
engagement_type: strategy
lead_partner: Sarah Chen
start_date: 2025-01-15
contract_value: $240,000
renewal_date: 2025-07-15
---

# Acme Corp

## Engagement Context
- Hired us for go-to-market strategy in Southeast Asia
- CEO is former McKinsey, expects structured deliverables
- Key stakeholder: VP Strategy (reports directly to CEO)

## Deliverables
- Market entry analysis (delivered Feb 1)
- Competitive landscape (in progress)
- Channel strategy (scheduled March)

## Meeting Notes
- 2025-02-10: Reviewed market entry draft, client wants deeper Indonesia analysis
- 2025-01-20: Kickoff meeting, aligned on scope and timeline
```

The structured frontmatter (`status`, `contract_value`, `renewal_date`) is queryable. The unstructured body (relationship context, meeting notes, engagement history) is what makes an agent effective — context that no database row can capture. An agent preparing for a client meeting reads one file and has everything: the deal terms, the relationship dynamics, and the full history.

### C. Multiple agents sharing a workspace

A research agent writes analysis to `research/`. A drafting agent reads it to produce deliverables in `deliverables/`. A communications agent reads deliverables and sends them to clients. A tracking agent monitors outcomes and writes to `metrics/`. A planning agent reads everything and maintains `strategy/`.

No message bus. No event system. No API integrations between agents. They coordinate through the file system — the oldest, most reliable coordination mechanism in computing. Agent B reads what Agent A wrote. If Agent A hasn't written yet, Agent B sees an empty folder and knows to wait or ask.

### D. Ten thousand files

A workspace has accumulated 10,000 files over two years. A new agent needs to find the Q3 competitive analysis.

1. Read root `_index.md` (400 tokens) — sees `research/` contains competitive analysis
2. Read `research/_index.md` (350 tokens) — sees `competitors/` organized by quarter
3. Read `research/competitors/_index.md` (300 tokens) — sees Q3 section with file list
4. Read `research/competitors/q3-2025-synthesis.md` — found it

Four reads. Under 2,000 tokens of navigation overhead. The agent didn't scan 10,000 files. It navigated a hierarchy. This works identically whether the workspace holds legal case files, engineering documentation, or sales records.

### E. Structured records with context

A file can represent any entity that today lives in a SaaS database. The pattern is always the same: YAML frontmatter for queryable fields, Markdown body for context.

**A sales contact:**
```markdown
---
name: James Park
company: Meridian Health
role: VP Engineering
stage: proposal_sent
deal_size: $180,000
last_contact: 2025-02-12
---
## Notes
- Evaluated three competitors before talking to us
- Technical team is skeptical, needs proof of concept
- Budget approved through Q3, decision by April
```

**An engineering component:**
```markdown
---
name: auth-service
language: go
owner: platform-team
status: production
dependencies: [user-service, token-store]
last_deploy: 2025-02-13
---
## Architecture Decisions
- Chose JWT over sessions for stateless scaling (ADR-017)
- Rate limiting at gateway level, not service level
## Known Issues
- Token refresh race condition under high concurrency (#1247)
```

**A legal matter:**
```markdown
---
case_number: 2025-CV-0847
client: Meridian Health
type: patent_infringement
status: discovery
assigned_attorney: Maria Santos
filing_date: 2025-01-22
---
## Case Strategy
- Focus on prior art from 2019 patent filing
- Expert witness: Dr. Kim (Stanford, agreed to testify)
## Key Deadlines
- Discovery cutoff: April 30, 2025
- Expert reports due: May 15, 2025
```

The folder is the table. The frontmatter is the schema. The body is what no database captures — the context that makes an agent (or a human) effective.

### F. Bad data recovery

An agent writes incorrect data to a file — it hallucinated a figure, mangled a date, or overwrote important context. The error is discovered days later.

Query the version history: "Show me all versions of this file." See that version 3 introduced the error. Roll back to version 2. The file is restored to its correct state. Version 3 still exists in history for audit purposes — nothing is deleted.

### G. Concurrent writes

Two agents write to the same file simultaneously. Agent A is updating a contact's deal stage. Agent B is adding notes from a call with that contact.

Both writes succeed. The file now has two recent versions. The last write wins as the current version, but the other version is preserved. An agent (or human) can review both versions and merge them. No data is lost. No write fails.

This is a deliberate trade-off: we choose availability and simplicity over strict consistency. For workspace data, last-write-wins with full history is the right trade-off. This isn't a bank processing concurrent payments — it's a workspace managing organizational knowledge.

### H. New agent onboarding

A new agent is added to the workspace. It has never seen this organization's data before.

1. Read root `_index.md` — learns the workspace structure and what exists
2. Drill into any section's `_index.md` — understands what data is there and how recent it is
3. Read relevant files — gets the full context it needs

Three reads and the agent understands the workspace topology, what knowledge exists, and how to contribute. It's productive immediately because the workspace is self-describing.

### I. Audit and transparency

Someone asks: "What did our AI agents do last month?"

Query the mutation log: all writes, by which agent, to which files, with timestamps. Diff any two versions of any file to see exactly what changed. Filter by agent to see one agent's contributions. Filter by folder to see all activity in a domain.

Every action is recorded. Every change is reversible. Every agent's work is attributable. The workspace is fully transparent.

---

## What sayou Is / What sayou Is NOT

### sayou IS:
- A **persistent file workspace** where AI agents accumulate organizational knowledge and manage operational data
- An **auto-indexed hierarchical store** that scales from 10 files to 100,000 files
- A **version-controlled knowledge base** with full history, audit trail, and rollback
- A **structured data store** where YAML frontmatter replaces database columns and folders replace tables
- An **MCP server** that any compatible agent can connect to immediately
- An **open-source infrastructure layer** that any agent framework can build on
- A **replacement for the database layer** of any SaaS — domain-agnostic by design

### sayou is NOT:
- A **vector database** — Semantic search is one feature, not the architecture
- A **conversation memory** — We store work product, not chat history snippets
- A **sandbox / runtime** — We store knowledge, not execute code
- A **filesystem** — We don't intercept syscalls; we provide a knowledge-aware workspace API
- A **replacement for ACID databases** — Banking ledgers, payment processing, and inventory counts still need relational databases for the transactional core
- A **monolithic SaaS** — sayou is infrastructure; applications are built on top of it

---

## Architecture Philosophy

### Why cloud-native?

The interesting problems in agent workspaces are multi-agent, multi-tenant cloud problems: concurrent access, index consistency, access control, storage efficiency at scale. Designing for local-first and trying to retrofit cloud support leads to architectural compromises. We design for the hard case first.

### Why Markdown files (even for structured data)?

Markdown is the lingua franca of LLMs. Every model can read it. Every model can write it. It's structured enough to be parseable, flexible enough to represent any knowledge, and human-readable without any tooling. When the AI landscape changes (and it will), Markdown files will still be readable.

But what about structured, operational data — client records, project trackers, inventory lists? This is where YAML frontmatter shines. A client profile has structured fields (`status: active`, `contract_value: $240,000`, `renewal_date: 2025-07-15`) in the frontmatter that the catalog can index and query, AND unstructured context (relationship notes, meeting history, strategic decisions) in the Markdown body that an agent reads for decision-making. A database row can only store the structured fields. A file stores everything — the data AND the context — in a single, versioned, human-readable unit.

### Why MCP-first?

MCP is becoming the standard protocol for agent-tool interaction. By building the MCP server first, we ensure that any agent on any framework can use sayou without installing an SDK or reading documentation. The tool descriptions are the documentation.

### Why insert-only?

Mutable state is the source of most data system bugs: lost updates, phantom reads, inconsistent caches. Insert-only storage eliminates these categories of bugs entirely. The cost is storage space, which is cheap and getting cheaper. The benefit is a system that is correct by construction.

---

## System Architecture

The principles above describe *what* sayou values. This section describes *how* it works as a system — what each layer does, where data lives, and how the pieces connect.

### Object Storage (the source of truth)

All file content lives in object storage — Markdown files, binary assets, version snapshots. Every version of every file is an immutable object. "Deleting" a file means removing the catalog pointer, not the object.

Key structure:

```
{org_id}/{workspace_id}/versions/{version_id}
```

Data is org-isolated at the storage level. Even with a catastrophic catalog failure, one organization's data cannot leak into another's key namespace.

For Pixell: S3 (`pixell-agents` bucket, already in use). For local development: MinIO. For open-source users: any S3-compatible store.

Object storage is NOT the EC2 filesystem — that's ephemeral, dies with the instance, has no redundancy. File content always lives in object storage, never on a compute instance's local disk.

### Relational Database (the metadata catalog)

The database does NOT store file content. It stores pointers and metadata — the catalog that makes the file store queryable, navigable, and fast.

What the catalog holds:

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| **files** | path, workspace_id, current_version_id, content_type, frontmatter fields | File records — the index entry for each file. Frontmatter fields are extracted and stored as columns for structured queries. |
| **file_versions** | version_number, storage_key (S3 pointer), size_bytes, content_hash, created_by (agent ID), created_at | Version records — every version of every file, each pointing to an immutable object in storage. |
| **workspaces** | workspace_id, organization_id, name | Workspace records — logical containers within an organization. |
| **index_cache** | folder_path, workspace_id, content | Pre-computed `_index.md` content — avoids regeneration on every read. |
| **kv_store** | key, value, workspace_id, ttl | Key-value store — transient agent state (Principle 5). |
| **mutation_log** | agent_id, action, file_path, version_id, timestamp | Audit trail — who changed what, when (Principle 2). |

For Pixell: MySQL on RDS (same instance as pixell-api — no new database infrastructure). For open-source users: any SQL database. The catalog schema uses standard SQL with no vendor-specific features.

The catalog is **rebuildable**. Scan object storage, parse frontmatter from each file, reconstruct the index. Losing the catalog is an inconvenience (downtime while rebuilding), not a disaster (data loss).

### MCP Server (the interface)

A thin layer that translates MCP tool calls into catalog queries + object storage operations. The MCP server is stateless — all state lives in the catalog and object storage.

Deployment modes:
- **Standalone service** — runs as its own process, connects to its own database and object storage
- **Module inside an existing API** — shares the host's database connection, auth middleware, and object storage client
- **Sidecar process** — runs alongside an agent, communicating over stdio or local socket

For Pixell: runs inside pixell-api as a module. This reuses the existing auth middleware, MySQL connection, S3 client, and deployment infrastructure. No new services to deploy or monitor.

---

## Multi-Tenancy and Data Isolation

sayou is designed for multi-tenant deployment from day one. Data isolation is architectural, not policy-based — the system makes cross-tenant access impossible, not just forbidden.

### Organization = tenant boundary

Every table has `organization_id`. Every query filters by it. No exceptions.

An agent's JWT carries `org_id`. All sayou operations are scoped to that org's data. There is no API that returns data across organizations. Cross-org access is architecturally impossible — the query layer enforces tenant isolation, and the storage layer partitions by org in the key namespace.

S3 keys are prefixed with `org_id`:

```
{org_id}/{workspace_id}/versions/{version_id}
```

Even at the storage level, one tenant's data lives in a completely separate key space from another's.

### Workspace = logical boundary within an org

An organization can have multiple workspaces — `marketing`, `engineering`, `legal`, `executive`. Workspaces provide logical separation, not security isolation. Users within an org can be granted access to multiple workspaces.

Agents are granted workspace-level access. A research agent might access the `research` workspace but not `hr`. A communications agent might read from `marketing` and write to `outreach`. Workspace scoping controls what an agent can see and modify without requiring separate authentication.

### Agent = identity within a workspace

Every write records which agent made it — the `created_by` field in the version record and the `agent_id` in the mutation log. This is the audit foundation: you can always answer "which agent changed this file, and when?"

Agents authenticate via JWT, the same way users do. Agent permissions can be scoped:
- **Read-only** — can read files and indexes, cannot write
- **Read-write** — can read and write files within granted workspaces
- **Admin** — can manage workspaces, configure indexes, view mutation logs

### Auth flow

sayou reuses Pixell's existing authentication model:

```
Agent/User → Firebase Auth → JWT (contains user_id, org_id)
           → sayou validates JWT
           → Scopes all operations to org_id
           → Checks workspace-level permissions
```

For open-source deployments: pluggable auth interface. Bring your own JWT issuer — sayou validates the token signature, extracts `org_id` and `user_id`, and enforces scoping. The auth contract is: "give me a valid JWT with org_id, and I'll handle the rest."

---

## Agent Integration

How do agents actually connect to sayou? Two modes, used together.

### LLM-driven (MCP tools)

The agent's LLM has sayou tools in its tool set: `workspace_read`, `workspace_write`, `workspace_search`, `workspace_list`. When the LLM decides it needs workspace data, it calls these tools. The MCP client in the agent forwards the call to the sayou MCP server.

This mode is for **dynamic decisions** — the LLM reasoning about what knowledge to retrieve or store:
- "Let me check what research we already have on this competitor"
- "I should save these findings for future reference"
- "What's the current status of the Q3 project?"

The LLM sees the tool descriptions, understands what the workspace contains (via `_index.md`), and decides when to read, write, or search. No hardcoded logic tells it when to use the workspace.

### Code-driven (REST API / Python client)

The agent's orchestrator code makes deterministic calls — things that should always happen, not LLM judgment calls:
- "Always save research results after completing a task"
- "Load the brand context at the start of every conversation"
- "Write the final deliverable to the workspace before responding"

This uses sayou's REST API or Python client library directly from the orchestrator, bypassing the LLM. These are programmatic operations that don't need reasoning — just execution.

### Concrete integration in Pixell

**pixell-one (PER):** sayou tools are registered alongside Slack and E2B tools in the tool executor. The agent loop calls them the same way it calls any other tool — the LLM decides, the tool executor dispatches, the result flows back into the conversation.

**Standalone agents (reddit-agent, data-agent, channels-agent):** The pixell-sdk includes a sayou client. The agent's orchestrator wires it in during initialization, the same way it wires in the OAuth client or any other service dependency.

**Auth:** The agent gets a JWT from pixell-api (the same flow it already uses for OAuth tokens), and passes it to sayou. sayou validates the JWT, extracts `org_id`, and scopes all operations. This is identical to the existing pattern where agents call `GET /api/v1/oauth/{provider}/token` — same auth model, different service.

---

## Open Source Philosophy

### Why open source?

Infrastructure should be a shared standard, not a proprietary moat. HTTP, SQL, Git, Docker, Kubernetes — the infrastructure layers that win are the ones that become open standards. sayou aims to be the open standard for agent persistent storage.

If sayou succeeds, every agent framework will support it. That's better for Pixell (more agents using the infrastructure we know best) and better for the ecosystem (agents become more capable when they can persist knowledge).

### Apache 2.0

We chose Apache 2.0 because it's the most permissive license that still provides patent protection. Companies can use sayou in commercial products without restriction. We want adoption, not licensing revenue.

### Relationship to Pixell

**sayou is to Pixell what Postgres is to every SaaS application.** Postgres is open source. Thousands of companies build on it. Some companies (like Supabase, Neon, Crunchy Data) build commercial products around it. But Postgres itself is free and open.

sayou is the storage layer. Pixell is the application layer — the agents, the UI, the workflows, the integrations that make agent workspaces useful for specific business problems. Pixell's moat is not the storage; it's the intelligence and experience built on top of it.

### Community building

We start with a clear philosophy (this document), clean architecture, and comprehensive documentation. We build in public, accept contributions, and maintain a high bar for quality. The goal is a project that developers trust enough to build on — because the principles are clear, the code is clean, and the governance is transparent.
