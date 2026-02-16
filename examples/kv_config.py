"""
KV store patterns — configuration, caching, and agent state.

Shows three real-world patterns:
  1. Agent configuration management
  2. Ephemeral cache with TTL
  3. Agent state checkpointing (last-run tracking)

Runs fully in-memory (SQLite + temp directory) so it leaves no artifacts.

Usage:
    python examples/kv_config.py
"""

import asyncio
import tempfile

from sayou import Workspace


async def main() -> None:
    storage_dir = tempfile.mkdtemp(prefix="sayou-kv-")

    async with Workspace(
        org_id="acme-corp",
        user_id="config-agent",
        database_url="sqlite+aiosqlite://",
        storage_path=storage_dir,
    ) as ws:

        # ── 1. Agent Configuration ───────────────────────────────
        print("1) AGENT CONFIGURATION — store and retrieve settings\n")

        await ws.kv_set("config.theme", "dark")
        await ws.kv_set("config.language", "en")
        await ws.kv_set("config.api_keys", {
            "openai": "sk-...",
            "anthropic": "sk-ant-...",
        })

        theme = await ws.kv_get("config.theme")
        print(f"   theme:    {theme['value']}")

        keys = await ws.kv_get("config.api_keys")
        print(f"   api_keys: {keys['value']}")

        # List all config keys
        config_keys = await ws.kv_list(prefix="config.")
        print(f"   all config keys ({config_keys['total']}):")
        for item in config_keys["items"]:
            print(f"     - {item['key']}")
        print()

        # ── 2. Feature Flags ──────────────────────────────────────
        print("2) FEATURE FLAGS — toggle features via KV\n")

        await ws.kv_set("flags.dark_mode", True)
        await ws.kv_set("flags.beta_search", False)
        await ws.kv_set("flags.max_retries", 3)

        flags = await ws.kv_list(prefix="flags.")
        print(f"   active flags ({flags['total']}):")
        for item in flags["items"]:
            print(f"     {item['key']} = {item['value']}")
        print()

        # ── 3. Ephemeral Cache with TTL ───────────────────────────
        print("3) EPHEMERAL CACHE — entries with TTL auto-expire\n")

        # Cache an API response for 300 seconds (5 minutes)
        await ws.kv_set("cache.user_profile", {
            "name": "Alice",
            "email": "alice@acme.com",
            "plan": "pro",
        }, ttl_seconds=300)

        # Cache a computed result for 60 seconds
        await ws.kv_set("cache.dashboard_stats", {
            "total_files": 1247,
            "active_users": 23,
        }, ttl_seconds=60)

        cached = await ws.kv_get("cache.user_profile")
        print(f"   cached profile: {cached['value']}")
        print(f"   expires_at:     {cached.get('expires_at', 'N/A')}")

        cache_keys = await ws.kv_list(prefix="cache.")
        print(f"   cache entries:  {cache_keys['total']}")
        print()

        # ── 4. Agent State Checkpointing ──────────────────────────
        print("4) AGENT STATE — track last-run and progress\n")

        # Simulate an agent recording its run state
        await ws.kv_set("agent.researcher.last_run", "2026-02-15T10:30:00Z")
        await ws.kv_set("agent.researcher.files_processed", 42)
        await ws.kv_set("agent.researcher.status", "idle")

        # Next run: check when we last ran
        last_run = await ws.kv_get("agent.researcher.last_run")
        processed = await ws.kv_get("agent.researcher.files_processed")
        print(f"   last run:        {last_run['value']}")
        print(f"   files processed: {processed['value']}")

        # List all agent state
        agent_keys = await ws.kv_list(prefix="agent.researcher.")
        print(f"   agent state keys ({agent_keys['total']}):")
        for item in agent_keys["items"]:
            print(f"     {item['key']} = {item['value']}")
        print()

        # ── 5. Cleanup ────────────────────────────────────────────
        print("5) CLEANUP — delete keys when no longer needed\n")

        await ws.kv_delete("cache.dashboard_stats")
        remaining = await ws.kv_list(prefix="cache.")
        print(f"   cache entries after delete: {remaining['total']}")
        print()

    print("Done. All KV store patterns demonstrated successfully.")


if __name__ == "__main__":
    asyncio.run(main())
