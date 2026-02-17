"""Full evaluation of sayou-agent with detailed scoring.

Scores each capability out of 10 across multiple criteria.

Run:
    python -m sayou.agent  (in another terminal)
    python -m sayou.agent.benchmarks.eval_full
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field

import httpx

AGENT_URL = "http://localhost:9008"


@dataclass
class Score:
    name: str
    points: float
    max_points: float
    notes: str = ""

    @property
    def pct(self) -> float:
        return (self.points / self.max_points * 10) if self.max_points else 0


@dataclass
class EvalResult:
    test_name: str
    scores: list[Score] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    elapsed: float = 0.0
    content: str = ""

    def add(self, name: str, points: float, max_points: float, notes: str = ""):
        self.scores.append(Score(name, points, max_points, notes))

    @property
    def total_score(self) -> float:
        total_pts = sum(s.points for s in self.scores)
        total_max = sum(s.max_points for s in self.scores)
        return (total_pts / total_max * 10) if total_max else 0

    def print_report(self):
        print(f"\n{'─' * 50}")
        print(f"  {self.test_name}  —  {self.total_score:.1f}/10  ({self.elapsed:.1f}s)")
        print(f"{'─' * 50}")
        for s in self.scores:
            status = "✓" if s.points == s.max_points else "△" if s.points > 0 else "✗"
            print(f"  {status} {s.name}: {s.points}/{s.max_points}" + (f"  ({s.notes})" if s.notes else ""))


async def stream_chat(
    messages: list[dict], session_id: str = "eval"
) -> tuple[list[dict], str, float]:
    """Returns (events, full_content, elapsed_seconds)."""
    events = []
    content_parts = []
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
                    except json.JSONDecodeError:
                        pass

    elapsed = time.time() - t0
    content = "".join(content_parts)
    return events, content, elapsed


def get_tool_uses(events: list[dict], tool_name: str) -> list[dict]:
    return [e for e in events if e.get("type") == "tool_use" and e.get("name") == tool_name]


def get_tool_results(events: list[dict], tool_name: str) -> list[dict]:
    return [e for e in events if e.get("type") == "tool_result" and e.get("name") == tool_name]


def has_error(events: list[dict]) -> bool:
    return any(e.get("type") == "error" for e in events)


def has_complete(events: list[dict]) -> bool:
    return any(e.get("type") == "complete" for e in events)


# ═════════════════════════════════════════════════════════════════════
# TEST 1: DIRECT CHAT
# ═════════════════════════════════════════════════════════════════════

async def eval_direct_chat() -> EvalResult:
    r = EvalResult("1. Direct Chat")

    # 1a: Simple greeting
    print("\n  1a: Simple greeting...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": "Hi there!"}], "eval-1a"
    )
    r.elapsed += elapsed

    # Should respond without tools
    tool_uses = [e for e in events if e.get("type") == "tool_use"]
    r.add("No unnecessary tools", 2 if len(tool_uses) == 0 else 0, 2,
          f"{len(tool_uses)} tool calls" if tool_uses else "clean")
    r.add("Has response", 1 if len(content) > 10 else 0, 1)
    r.add("No errors", 1 if not has_error(events) else 0, 1)
    r.add("Completes", 1 if has_complete(events) else 0, 1)

    # 1b: Follow-up conversation (multi-turn)
    print("  1b: Multi-turn conversation...")
    events, content, elapsed = await stream_chat(
        [
            {"role": "user", "content": "My name is Alex and I work at a startup."},
            {"role": "assistant", "content": "Nice to meet you, Alex! What does your startup do?"},
            {"role": "user", "content": "We build developer tools. What's my name?"},
        ],
        "eval-1b",
    )
    r.elapsed += elapsed

    remembers_name = "alex" in content.lower()
    r.add("Remembers context", 2 if remembers_name else 0, 2, "remembered name" if remembers_name else "forgot name")
    r.add("Coherent response", 1 if len(content) > 5 else 0, 1)

    # 1c: Ambiguous request — should NOT do web search for general chat
    print("  1c: Ambiguous question (should not search)...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": "Tell me a joke about programming."}], "eval-1c"
    )
    r.elapsed += elapsed

    tool_uses = [e for e in events if e.get("type") == "tool_use"]
    r.add("No tools for joke", 2 if len(tool_uses) == 0 else 1 if len(tool_uses) <= 1 else 0, 2,
          f"{len(tool_uses)} tools" if tool_uses else "clean")

    r.content = content
    return r


# ═════════════════════════════════════════════════════════════════════
# TEST 2: WEB SEARCH
# ═════════════════════════════════════════════════════════════════════

async def eval_web_search() -> EvalResult:
    r = EvalResult("2. Web Search")

    # 2a: Explicit search request
    print("\n  2a: Explicit web search...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": "Search the web for the latest developments in quantum computing in 2026."}],
        "eval-2a",
    )
    r.elapsed += elapsed

    ws = get_tool_uses(events, "web_search")
    ws_results = get_tool_results(events, "web_search")
    r.add("Uses web_search", 2 if len(ws) >= 1 else 0, 2)
    r.add("Search succeeds", 1 if ws_results and "Error" not in (ws_results[0].get("result", "")) else 0, 1)
    r.add("No errors", 1 if not has_error(events) else 0, 1)

    # Check response quality
    has_urls = "http" in content.lower() or ".com" in content.lower() or ".org" in content.lower()
    has_substance = len(content) > 200
    has_structure = content.count("\n") >= 3 or "**" in content or "1." in content
    r.add("Cites sources/URLs", 1 if has_urls else 0, 1, "has URLs" if has_urls else "no URLs")
    r.add("Substantial response", 1 if has_substance else 0, 1, f"{len(content)} chars")
    r.add("Structured output", 1 if has_structure else 0, 1)

    # 2b: Implicit search need (current events)
    print("  2b: Implicit search need...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": "What happened at the latest Apple keynote?"}],
        "eval-2b",
    )
    r.elapsed += elapsed

    ws = get_tool_uses(events, "web_search")
    r.add("Searches for current events", 2 if len(ws) >= 1 else 0, 2, f"{len(ws)} searches")

    r.content = content
    return r


# ═════════════════════════════════════════════════════════════════════
# TEST 3: RESEARCH + STORE
# ═════════════════════════════════════════════════════════════════════

async def eval_research_store() -> EvalResult:
    r = EvalResult("3. Research + Store")

    # 3a: Research and save
    print("\n  3a: Research and store to workspace...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": (
            "Research the top 3 MCP (Model Context Protocol) server implementations in 2026. "
            "Save your findings to the workspace as a structured file."
        )}],
        "eval-3a",
    )
    r.elapsed += elapsed

    # Check web search happened
    ws = get_tool_uses(events, "web_search")
    r.add("Did web research", 1 if len(ws) >= 1 else 0, 1, f"{len(ws)} searches")

    # Check file was written
    writes = get_tool_uses(events, "workspace_write")
    write_results = get_tool_results(events, "workspace_write")
    r.add("Wrote file", 2 if len(writes) >= 1 else 0, 2)

    write_success = any("Successfully wrote" in (wr.get("result", "")) for wr in write_results)
    r.add("Write succeeded", 1 if write_success else 0, 1)

    # Check file content quality (from the tool_use arguments)
    if writes:
        args = writes[0].get("arguments", "{}")
        try:
            parsed = json.loads(args)
            file_content = parsed.get("content", "")
            file_path = parsed.get("path", "")

            # Frontmatter check
            has_frontmatter = file_content.startswith("---") and "---" in file_content[3:]
            r.add("Has YAML frontmatter", 1 if has_frontmatter else 0, 1,
                  "present" if has_frontmatter else "missing")

            # Metadata quality
            has_date = "date:" in file_content
            has_topics = "topics:" in file_content
            has_tags = "tags:" in file_content
            meta_score = sum([has_date, has_topics, has_tags])
            r.add("Metadata quality", meta_score, 3,
                  f"date={has_date} topics={has_topics} tags={has_tags}")

            # Section headings
            headings = [l for l in file_content.split("\n") if l.startswith("## ")]
            r.add("Section headings", min(len(headings), 2), 2,
                  f"{len(headings)} headings")

            # Path convention
            good_path = file_path.startswith("observations/") and file_path.endswith(".md")
            r.add("Path convention", 1 if good_path else 0, 1,
                  file_path if good_path else f"bad path: {file_path}")

            # Store for later
            r.content = file_path

        except json.JSONDecodeError:
            r.add("Has YAML frontmatter", 0, 1, "couldn't parse args")
            r.add("Metadata quality", 0, 3)
            r.add("Section headings", 0, 2)
            r.add("Path convention", 0, 1)
    else:
        r.add("Has YAML frontmatter", 0, 1, "no write")
        r.add("Metadata quality", 0, 3)
        r.add("Section headings", 0, 2)
        r.add("Path convention", 0, 1)

    r.add("No errors", 1 if not has_error(events) else 0, 1)

    return r


# ═════════════════════════════════════════════════════════════════════
# TEST 4: RETRIEVE
# ═════════════════════════════════════════════════════════════════════

async def eval_retrieve(stored_path: str) -> EvalResult:
    r = EvalResult("4. Retrieve")

    # 4a: Search for stored content
    print("\n  4a: Search for stored content...")
    events, content, elapsed = await stream_chat(
        [{"role": "user", "content": "What MCP servers did you find in your research? Check the workspace."}],
        "eval-4a",
    )
    r.elapsed += elapsed

    # Should search workspace
    searches = get_tool_uses(events, "workspace_search")
    r.add("Uses workspace_search", 2 if len(searches) >= 1 else 0, 2)

    # Should read the file
    reads = get_tool_uses(events, "workspace_read")
    r.add("Uses workspace_read", 1 if len(reads) >= 1 else 0, 1)

    # Response should reference the stored content
    mentions_mcp = "mcp" in content.lower()
    r.add("References stored content", 1 if mentions_mcp else 0, 1)

    # Response quality
    has_substance = len(content) > 100
    r.add("Substantial answer", 1 if has_substance else 0, 1, f"{len(content)} chars")
    r.add("No errors", 1 if not has_error(events) else 0, 1)

    # 4b: Query that should NOT find results
    print("  4b: Query with no matching content...")
    events2, content2, elapsed2 = await stream_chat(
        [{"role": "user", "content": "What do I have stored about underwater basket weaving?"}],
        "eval-4b",
    )
    r.elapsed += elapsed2

    # Should search and gracefully handle no results
    searches2 = get_tool_uses(events2, "workspace_search")
    r.add("Searches for missing topic", 1 if len(searches2) >= 1 else 0, 1)

    # Should NOT hallucinate content
    no_hallucination = (
        "no " in content2.lower()
        or "don't have" in content2.lower()
        or "not found" in content2.lower()
        or "couldn't find" in content2.lower()
        or "no matching" in content2.lower()
        or "no results" in content2.lower()
        or "nothing" in content2.lower()
        or "empty" in content2.lower()
        or len(content2) < 300  # short response = didn't hallucinate long content
    )
    r.add("Handles missing gracefully", 2 if no_hallucination else 0, 2,
          "honest" if no_hallucination else "may have hallucinated")

    r.content = content
    return r


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

async def main():
    # Health check
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{AGENT_URL}/health")
            resp.raise_for_status()
    except Exception as e:
        print(f"Agent not reachable at {AGENT_URL}: {e}")
        print("Start: python -m sayou.agent")
        sys.exit(1)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║         sayou-agent  FULL EVALUATION                    ║")
    print("╚══════════════════════════════════════════════════════════╝")

    results: list[EvalResult] = []

    # Run evals sequentially (3 depends on stored file for 4)
    r1 = await eval_direct_chat()
    r1.print_report()
    results.append(r1)

    r2 = await eval_web_search()
    r2.print_report()
    results.append(r2)

    r3 = await eval_research_store()
    r3.print_report()
    results.append(r3)

    # Pass stored file path to retrieve eval
    stored_path = r3.content or ""
    r4 = await eval_retrieve(stored_path)
    r4.print_report()
    results.append(r4)

    # Final summary
    print("\n" + "═" * 58)
    print("  FINAL SCORES")
    print("═" * 58)
    total_weighted = 0
    for r in results:
        score = r.total_score
        total_weighted += score
        bar = "█" * int(score) + "░" * (10 - int(score))
        print(f"  {r.test_name:<25} {bar}  {score:.1f}/10  ({r.elapsed:.1f}s)")

    avg = total_weighted / len(results)
    print(f"\n  {'OVERALL':<25} {'█' * int(avg) + '░' * (10 - int(avg))}  {avg:.1f}/10")
    total_time = sum(r.elapsed for r in results)
    print(f"  Total eval time: {total_time:.1f}s")
    print()

    return avg >= 7.0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
