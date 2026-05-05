# Multi-Agent Coordination Patterns

Three patterns for coordinating multiple agents on a shared sayou workspace, ordered by complexity. All use features that already exist — no new APIs needed.

---

## Pattern 1: Namespace Isolation

**When to use:** Multiple agents working on independent tasks that a coordinator synthesizes later. This is the default — start here.

Each agent writes to its own folder prefix. A coordinator agent reads across namespaces to synthesize results. No conflicts are possible because write paths never overlap.

```
workspace/
  agents/
    researcher/       ← research-agent writes here
      market-trends.md
      competitor-analysis.md
    analyst/          ← analyst-agent writes here
      strategic-brief.md
      risk-assessment.md
    coordinator/      ← coordinator reads all, writes summaries
      weekly-synthesis.md
```

### Example

```python
from sayou import Workspace

# Each agent uses its own namespace
async with Workspace(source="research-agent", ...) as ws:
    await ws.write("agents/researcher/market-trends.md", """\
---
status: complete
topic: market-trends
---
# Market Trends
Key finding: Agent adoption grew 300% in 2025.
""")

# Coordinator reads across namespaces
async with Workspace(source="coordinator", ...) as ws:
    # See what each agent has produced
    researcher_files = await ws.list("agents/researcher/")
    analyst_files = await ws.list("agents/analyst/")

    # Read and synthesize
    trends = await ws.read("agents/researcher/market-trends.md")
    brief = await ws.read("agents/analyst/strategic-brief.md")

    await ws.write("agents/coordinator/weekly-synthesis.md", """\
---
based_on: [agents/researcher/market-trends.md, agents/analyst/strategic-brief.md]
---
# Weekly Synthesis
(Combined insights from research and analysis agents)
""")
```

### Tradeoffs

| Pro | Con |
|-----|-----|
| Zero conflict by design | Requires a coordinator to combine results |
| Simple mental model | Duplicate data if agents need shared state |
| Each agent's work is independently auditable | Folder structure grows with agent count |

---

## Pattern 2: Advisory Locks via KV Store

**When to use:** Multiple agents need to edit the same files, and you need to prevent concurrent writes from clobbering each other.

The KV store supports TTL (time-to-live), which makes it a natural fit for advisory locks. An agent acquires a lock by setting a KV key with a TTL, checks the lock before writing, and releases it after. If an agent crashes, the TTL auto-expires the lock.

This is an **advisory** lock — agents must cooperate by checking the lock before writing. It doesn't prevent writes at the storage level.

### Protocol

```
1. CHECK:   kv_get("lock:{path}") — if held by another agent, back off
2. ACQUIRE: kv_set("lock:{path}", agent_id, ttl_seconds=300)
3. WRITE:   workspace_write(path, content)
4. RELEASE: kv_delete("lock:{path}")
```

### Race condition caveat

Steps 1-2 are not atomic. Between CHECK and ACQUIRE, another agent could also see the lock as free and acquire it. Both agents would think they hold the lock.

In practice this is safe for AI agents, which operate in sequential turns with seconds between operations. The race window is milliseconds. But if you have truly concurrent agents hitting the same path at high frequency, this pattern is insufficient — use namespace isolation instead.

### Example

```python
from sayou import Workspace

LOCK_TTL = 300  # 5 minutes — auto-expires if agent crashes

async def acquire_lock(ws: Workspace, path: str, agent_id: str) -> bool:
    """Try to acquire an advisory lock. Returns True if acquired."""
    lock_key = f"lock:{path}"
    existing = await ws.kv_get(lock_key)

    if existing and existing.get("value") is not None:
        holder = existing["value"]
        if holder != agent_id:
            return False  # Someone else holds the lock

    await ws.kv_set(lock_key, agent_id, ttl_seconds=LOCK_TTL)
    return True

async def release_lock(ws: Workspace, path: str) -> None:
    """Release an advisory lock."""
    await ws.kv_delete(f"lock:{path}")

# Usage
async with Workspace(source="agent-a", ...) as ws:
    path = "shared/report.md"

    if await acquire_lock(ws, path, "agent-a"):
        try:
            doc = await ws.read(path)
            await ws.write(path, updated_content)
        finally:
            await release_lock(ws, path)
    else:
        print(f"Skipping {path} — locked by another agent")
```

See [`examples/advisory_locks.py`](../examples/advisory_locks.py) for a complete runnable example.

### Tradeoffs

| Pro | Con |
|-----|-----|
| Prevents concurrent write conflicts | Advisory only — agents must cooperate |
| TTL prevents deadlocks from crashed agents | CHECK + ACQUIRE is not atomic (see caveat above) |
| Uses existing KV store — no new infrastructure | Adds latency (lock check before every write) |

---

## Pattern 3: Event Log + Reduce

**When to use:** Multiple agents produce observations or updates about the same topic, and you need a single consolidated view.

Each agent writes entries to its **own** log file. A reducer agent periodically reads all agent logs and writes a consolidated summary. This avoids conflicts entirely — each agent only writes to files it owns.

```
workspace/
  logs/
    customer-feedback/
      support-agent.md     ← support-agent writes here
      sales-agent.md       ← sales-agent writes here
  summaries/
    customer-feedback.md   ← reducer writes consolidated view
```

**Why per-agent log files?** A single shared log file would require read-modify-write to "append," which races under concurrent access — the second writer overwrites the first's entry. Per-agent files are true isolation (like Pattern 1 applied to logs).

### Example

```python
from sayou import Workspace
from datetime import datetime, timezone

# Each agent writes to its own log file
async with Workspace(source="support-agent", ...) as ws:
    log_path = "logs/customer-feedback/support-agent.md"

    # Read existing entries (or start fresh)
    try:
        doc = await ws.read(log_path)
        existing = doc["content"]
    except Exception:
        existing = "# Support Agent — Customer Feedback\n"

    # Append new entry (safe — only this agent writes this file)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    entry = f"\n## [{now}]\n- Customer reported slow search on large workspaces\n- Priority: high\n"
    await ws.write(log_path, existing + entry)

# Reducer reads all agent logs and writes a consolidated summary
async with Workspace(source="reducer", ...) as ws:
    agent_logs = await ws.glob("logs/customer-feedback/*.md")

    all_entries = []
    for log_file in agent_logs.get("files", []):
        doc = await ws.read(log_file["path"])
        all_entries.append(doc["content"])

    # Parse, deduplicate, prioritize across all agent logs...
    await ws.write("summaries/customer-feedback.md", """\
---
type: summary
sources: logs/customer-feedback/
entry_count: 12
---
# Customer Feedback Summary

## High Priority
- Slow search on large workspaces (3 reports)

## Medium Priority
- Request for bulk export (2 reports)
""")
```

### Using KV to track reducer progress

The reducer can track which version of each agent log it last processed:

```python
async with Workspace(source="reducer", ...) as ws:
    agent_logs = await ws.glob("logs/customer-feedback/*.md")

    for log_file in agent_logs.get("files", []):
        path = log_file["path"]
        kv_key = f"reducer:last_version:{path}"

        last = await ws.kv_get(kv_key)
        last_version = int(last["value"]) if last and last.get("value") is not None else 0

        doc = await ws.read(path)
        current_version = doc.get("version_number", 1)

        if current_version > last_version:
            # Process new entries from this agent's log...
            await ws.kv_set(kv_key, current_version)
```

### Tradeoffs

| Pro | Con |
|-----|-----|
| No conflicts — each agent writes its own file | Requires a reducer to merge views |
| Full history of every observation | Summary can lag behind real-time entries |
| Agents don't need to know about each other | More files than a single shared log |

---

## Choosing a Pattern

| Scenario | Recommended Pattern |
|----------|-------------------|
| Agents work on independent tasks | **Namespace Isolation** |
| Agents edit the same files | **Advisory Locks** |
| Agents produce observations on shared topics | **Event Log + Reduce** |
| You're not sure | **Namespace Isolation** — it's the simplest and handles most cases |

These patterns compose. You might use namespace isolation for most agent work, advisory locks for a shared configuration file, and event logs for aggregating observations.
