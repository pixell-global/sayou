# Sayou Architecture Roadmap — Pre-Drive Polish

## Steinberger Lens Applied

Peter Steinberger (steipete) — bootstrapped PSPDFKit to €116M exit, created OpenClaw (145k+ GitHub stars), now at OpenAI. His philosophy distills to: **zero friction first run, CLI-first, context window economics, and tool minimalism**.

### What He'd Champion About This Plan
- Zero-config local defaults → core to his "sensible defaults" principle
- CLI improvements → "Agents are really, really good at calling CLIs"
- `sayou init` / `sayou status` → his MCP best practices explicitly require "at least one info sub-command"
- Markdown/frontmatter storage → OpenClaw uses the exact same pattern for memory
- Auto-migrations → invisible infrastructure > manual setup steps

### What He'd Add (Critical Gaps)

**1. Tool Count Is a Crisis (23 tools!)**

The original plan said "8 tools is the right number." Sayou now has **23 MCP tools**. Steinberger explicitly warns:

> "Adding more tools means less space for actual code and reasoning. Every additional tool creates a tragedy of the commons in your context window."

Each tool description consumes ~100-200 tokens. 23 tools = ~3,000-4,600 tokens just for tool schemas before any actual work happens. This is the single biggest architectural problem.

**Fix:** Consolidate to ≤12 tools. Group related operations:
- Merge `workspace_move`, `workspace_copy`, `workspace_diff`, `workspace_read_section` → subcommands of existing tools or remove from MCP (keep in CLI/API only)
- Merge `workspace_chunks`, `workspace_search_chunks`, `workspace_chunk` → single `workspace_chunks` with mode parameter
- Merge `workspace_kv_get`, `workspace_kv_set`, `workspace_kv_list`, `workspace_kv_delete` → single `workspace_kv` with action parameter
- Consider: do `workspace_schema`, `workspace_generate_metadata`, `workspace_bulk_metadata` need to be MCP tools? Agents rarely invoke these proactively. CLI-only.

**2. Tool Description Quality**

From his MCP best practices: "Comprehensive, human-friendly descriptions for all tools and parameters." Current tool descriptions are functional but not optimized for LLM comprehension. Each tool needs:
- When to use (and when NOT to use)
- What the output looks like
- Common patterns

**3. Beta Release Before Production**

He advocates "first done with a beta tag." v0.2.0 should ship as v0.2.0b1 first.

### What He'd Eliminate

**1. Semantic Search as Default**
OpenClaw deliberately avoids vector databases. Sayou already built it, but it should be strictly optional — not loaded unless `SAYOU_EMBEDDING_PROVIDER` is set. Don't register the MCP tool at all if no provider configured.

**2. Auto-Metadata as Default**
Same logic. Don't register `workspace_generate_metadata` or `workspace_bulk_metadata` tools unless `SAYOU_METADATA_PROVIDER` is configured. Fewer tools = better agent performance.

**3. REST API Marketing (For Now)**
He'd say: "Don't market what doesn't work." REST API exists but isn't battle-tested. Remove from top-level README features, add as "experimental" section.

---

## Refined Roadmap

### P0: Unblock First-Time Users

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 0.1 | Zero-config local defaults (auto org_id, user_id, SQLite) | Small | Unblocks all first-time users |
| 0.2 | Auto-run migrations on startup | Medium | Eliminates silent first-run failures |
| 0.3 | `sayou init` + `sayou status` commands | Medium | Golden path + diagnostics |
| 0.4 | Tool consolidation (23→≤12 tools) | Medium | Context window savings, better agent perf |
| 0.5 | Simple MCP config in README | Tiny | Removes biggest friction point |

### P1: Package & CLI Polish

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1.1 | Dependency cleanup (fastapi/httpx → optional) | Small | Lighter install |
| 1.2 | CLI default identity from config | Medium | Usable CLI without flags |
| 1.3 | Conditional tool registration (hide unused features) | Small | Cleaner tool surface |
| 1.4 | Tool description optimization for LLMs | Medium | Better agent comprehension |

### P2: Error Handling & Diagnostics

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 2.1 | Config validation at startup | Medium | Fail fast, not fail confusingly |
| 2.2 | Actionable error messages in MCP tools | Medium | Self-service troubleshooting |

### P3: Launch Readiness

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 3.1 | PyPI keywords + metadata | Tiny | Discoverability |
| 3.2 | 60-second quickstart guide | Small | Launch content |
| 3.3 | MCP directory submissions | Small | Distribution |
| 3.4 | MCP usage transcript example | Small | Shows the "aha moment" |

### Eliminated From Original Plan
- ~~"Don't add semantic/vector search"~~ → Already built, keep as optional feature but don't register tools unless configured
- REST API cleanup → Deferred to sayou-drive, just remove from top-level marketing
- Web dashboard → sayou-drive territory
- Authentication → sayou-drive territory
