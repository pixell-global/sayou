"""Capture full agent responses for manual quality scoring.

Run:
    python -m sayou.agent  (in another terminal)
    python -m sayou.agent.benchmarks.eval_responses
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx

AGENT_URL = "http://localhost:9008"


async def stream_chat(messages: list[dict], session_id: str) -> dict:
    """Returns full structured output of an agent run."""
    events = []
    content_parts = []
    tool_log = []
    t0 = time.time()

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
                        if event.get("type") == "content":
                            content_parts.append(event.get("text", ""))
                        elif event.get("type") == "tool_use":
                            tool_log.append(f"CALL: {event.get('name')}({event.get('arguments', '')[:200]})")
                        elif event.get("type") == "tool_result":
                            tool_log.append(f"RESULT [{event.get('name')}]: {event.get('result', '')[:300]}")
                    except json.JSONDecodeError:
                        pass

    return {
        "content": "".join(content_parts),
        "tool_log": tool_log,
        "events": events,
        "elapsed": round(time.time() - t0, 1),
    }


def print_response(label: str, prompt: str, result: dict):
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"  PROMPT: {prompt}")
    print(f"  TIME: {result['elapsed']}s")
    print(f"{'=' * 70}")
    if result["tool_log"]:
        print("\n  TOOL ACTIVITY:")
        for entry in result["tool_log"]:
            print(f"    {entry}")
    print(f"\n  RESPONSE:\n")
    # Print with indent
    for line in result["content"].split("\n"):
        print(f"    {line}")
    print()


async def main():
    # ── 1. DIRECT CHAT ───────────────────────────────────────────────
    print("\n" + "█" * 70)
    print("  CATEGORY 1: DIRECT CHAT")
    print("█" * 70)

    r = await stream_chat(
        [{"role": "user", "content": "Hi! What can you do?"}],
        "dc-1",
    )
    print_response("1a. Introduction", "Hi! What can you do?", r)

    r = await stream_chat(
        [
            {"role": "user", "content": "I'm planning a trip to Japan next month with my friend Sarah."},
            {"role": "assistant", "content": "That sounds wonderful! Japan is amazing. What aspects of the trip are you planning?"},
            {"role": "user", "content": "We're thinking about Tokyo and Kyoto. Can you remind me who I'm traveling with and where we're going?"},
        ],
        "dc-2",
    )
    print_response("1b. Context retention", "Remind me who I'm traveling with and where?", r)

    r = await stream_chat(
        [{"role": "user", "content": "What's the meaning of life?"}],
        "dc-3",
    )
    print_response("1c. Philosophical (no tools needed)", "What's the meaning of life?", r)

    # ── 2. WEB SEARCH ────────────────────────────────────────────────
    print("\n" + "█" * 70)
    print("  CATEGORY 2: WEB SEARCH")
    print("█" * 70)

    r = await stream_chat(
        [{"role": "user", "content": "What are the biggest AI announcements this week?"}],
        "ws-1",
    )
    print_response("2a. Current events", "What are the biggest AI announcements this week?", r)

    r = await stream_chat(
        [{"role": "user", "content": "Compare the pricing of Claude, GPT-4o, and Gemini as of 2026."}],
        "ws-2",
    )
    print_response("2b. Factual comparison", "Compare pricing of Claude, GPT-4o, Gemini in 2026", r)

    # ── 3. RESEARCH + STORE ──────────────────────────────────────────
    print("\n" + "█" * 70)
    print("  CATEGORY 3: RESEARCH + STORE")
    print("█" * 70)

    r = await stream_chat(
        [{"role": "user", "content": (
            "Research how companies are using AI agents in production in 2026. "
            "Find real examples and save a structured summary to the workspace."
        )}],
        "rs-1",
    )
    print_response("3a. Research + store", "Research AI agents in production, save to workspace", r)

    # Print the file content that was written
    writes = [e for e in r["events"] if e.get("type") == "tool_use" and e.get("name") == "workspace_write"]
    if writes:
        try:
            args = json.loads(writes[0].get("arguments", "{}"))
            print("  FILE WRITTEN:")
            print(f"    Path: {args.get('path', 'N/A')}")
            print(f"    Content ({len(args.get('content', ''))} chars):")
            for line in args.get("content", "")[:2000].split("\n"):
                print(f"      {line}")
            if len(args.get("content", "")) > 2000:
                print("      ... [truncated]")
        except json.JSONDecodeError:
            pass

    # ── 4. RETRIEVE ──────────────────────────────────────────────────
    print("\n" + "█" * 70)
    print("  CATEGORY 4: RETRIEVE")
    print("█" * 70)

    r = await stream_chat(
        [{"role": "user", "content": "What companies are using AI agents? Check what's in the workspace."}],
        "ret-1",
    )
    print_response("4a. Retrieve stored research", "What companies are using AI agents? Check workspace.", r)

    r = await stream_chat(
        [{"role": "user", "content": "Do I have anything stored about cryptocurrency?"}],
        "ret-2",
    )
    print_response("4b. Missing topic (honesty test)", "Do I have anything about cryptocurrency?", r)


if __name__ == "__main__":
    asyncio.run(main())
