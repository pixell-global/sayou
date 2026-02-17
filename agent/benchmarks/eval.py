"""Eval script — tests sayou-agent end-to-end.

Run the agent server first:
    python -m sayou.agent

Then run this script:
    python -m sayou.agent.benchmarks.eval
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx

AGENT_URL = "http://localhost:9008"


async def stream_chat(messages: list[dict], session_id: str = "eval-session") -> list[dict]:
    """Send a chat request and collect all SSE events."""
    events = []
    content_parts = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        async with client.stream(
            "POST",
            f"{AGENT_URL}/chat/stream",
            json={
                "messages": messages,
                "session_id": session_id,
                "org_id": "eval-org",
                "user_id": "eval-user",
            },
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)

                        t = event.get("type")
                        if t == "content":
                            text = event.get("text", "")
                            content_parts.append(text)
                            print(text, end="", flush=True)
                        elif t == "tool_use":
                            print(f"\n  [tool] {event.get('name')}({event.get('arguments', '{}')[:80]}...)")
                        elif t == "tool_result":
                            result = event.get("result", "")
                            print(f"  [result] {result[:120]}{'...' if len(result) > 120 else ''}")
                        elif t == "error":
                            print(f"\n  [ERROR] {event.get('message')}")
                        elif t == "complete":
                            pass
                    except json.JSONDecodeError:
                        pass

    print()  # newline after streaming
    return events


def check_events(events: list[dict], checks: dict) -> dict:
    """Run checks on collected events. Returns {check_name: pass/fail}."""
    results = {}

    if "has_tool" in checks:
        tool_name = checks["has_tool"]
        found = any(e.get("type") == "tool_use" and e.get("name") == tool_name for e in events)
        results[f"used_{tool_name}"] = found

    if "has_content" in checks:
        content = "".join(e.get("text", "") for e in events if e.get("type") == "content")
        results["has_content"] = len(content) > 10

    if "has_complete" in checks:
        results["has_complete"] = any(e.get("type") == "complete" for e in events)

    if "no_error" in checks:
        results["no_error"] = not any(e.get("type") == "error" for e in events)

    if "wrote_file" in checks:
        results["wrote_file"] = any(
            e.get("type") == "tool_use" and e.get("name") == "workspace_write"
            for e in events
        )

    if "write_success" in checks:
        # Check that workspace_write tool result was successful
        results["write_success"] = any(
            e.get("type") == "tool_result"
            and e.get("name") == "workspace_write"
            and "Successfully wrote" in (e.get("result") or "")
            for e in events
        )

    return results


async def run_eval():
    # Check health first
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{AGENT_URL}/health")
            resp.raise_for_status()
            print(f"Agent health: {resp.json()}\n")
    except Exception as e:
        print(f"Agent not reachable at {AGENT_URL}: {e}")
        print("Start the agent first: python -m sayou.agent")
        sys.exit(1)

    all_results = {}

    # ── Test 1: Direct chat (no tools) ───────────────────────────────
    print("=" * 60)
    print("TEST 1: Direct chat — should respond without tools")
    print("=" * 60)
    t0 = time.time()
    events = await stream_chat([{"role": "user", "content": "Hello, what can you help me with?"}], "eval-1")
    elapsed = time.time() - t0
    results = check_events(events, {"has_content": True, "has_complete": True, "no_error": True})
    results["time_s"] = round(elapsed, 1)
    all_results["direct_chat"] = results
    print(f"  Results: {results}\n")

    # ── Test 2: Web search ───────────────────────────────────────────
    print("=" * 60)
    print("TEST 2: Web search — should use web_search tool")
    print("=" * 60)
    t0 = time.time()
    events = await stream_chat(
        [{"role": "user", "content": "Search the web for the latest news about MCP (Model Context Protocol) in 2026."}],
        "eval-2",
    )
    elapsed = time.time() - t0
    results = check_events(events, {
        "has_tool": "web_search",
        "has_content": True,
        "has_complete": True,
        "no_error": True,
    })
    results["time_s"] = round(elapsed, 1)
    all_results["web_search"] = results
    print(f"  Results: {results}\n")

    # ── Test 3: Research + Store ─────────────────────────────────────
    print("=" * 60)
    print("TEST 3: Research + Store — should web_search then workspace_write")
    print("=" * 60)
    t0 = time.time()
    events = await stream_chat(
        [{"role": "user", "content": (
            "Research the current state of AI agents in 2026 — "
            "what are the main frameworks and trends? "
            "Save your findings to the workspace."
        )}],
        "eval-3",
    )
    elapsed = time.time() - t0
    results = check_events(events, {
        "has_tool": "web_search",
        "has_content": True,
        "has_complete": True,
        "no_error": True,
        "wrote_file": True,
        "write_success": True,
    })
    results["time_s"] = round(elapsed, 1)
    all_results["research_and_store"] = results
    print(f"  Results: {results}\n")

    # ── Test 4: Retrieve stored content ──────────────────────────────
    print("=" * 60)
    print("TEST 4: Retrieve — should find the file we just stored")
    print("=" * 60)
    t0 = time.time()
    events = await stream_chat(
        [{"role": "user", "content": "What do you know about AI agent frameworks? Check the workspace."}],
        "eval-4",
    )
    elapsed = time.time() - t0
    results = check_events(events, {
        "has_tool": "workspace_search",
        "has_content": True,
        "has_complete": True,
        "no_error": True,
    })
    results["time_s"] = round(elapsed, 1)
    all_results["retrieve"] = results
    print(f"  Results: {results}\n")

    # ── Summary ──────────────────────────────────────────────────────
    print("=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    total_pass = 0
    total_checks = 0
    for test_name, results in all_results.items():
        checks = {k: v for k, v in results.items() if k != "time_s"}
        passed = sum(1 for v in checks.values() if v is True)
        total = len(checks)
        total_pass += passed
        total_checks += total
        status = "PASS" if passed == total else "FAIL"
        print(f"  {status}  {test_name}: {passed}/{total} checks ({results.get('time_s', '?')}s)")

    print(f"\nTotal: {total_pass}/{total_checks} checks passed")
    return total_pass == total_checks


if __name__ == "__main__":
    success = asyncio.run(run_eval())
    sys.exit(0 if success else 1)
