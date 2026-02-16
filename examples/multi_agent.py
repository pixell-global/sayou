"""
Multi-agent collaboration — multiple agents sharing one workspace.

Shows sayou's core value proposition: persistent context across agents.
  - Agent "researcher" writes research files (identified by source)
  - Agent "analyst" reads and builds on the researcher's work
  - Audit log proves who wrote what and when

Agents share the same workspace and user identity but use different
`source` values for attribution in the audit trail.

Runs fully in-memory (SQLite + temp directory) so it leaves no artifacts.

Usage:
    python examples/multi_agent.py
"""

import asyncio
import os
import tempfile

from sayou import Workspace


async def main() -> None:
    storage_dir = tempfile.mkdtemp(prefix="sayou-multi-")
    db_path = os.path.join(storage_dir, "workspace.db")

    # Both agents share the same workspace — different `source` for attribution
    ws_kwargs = dict(
        org_id="acme-corp",
        user_id="agent-system",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        storage_path=storage_dir,
    )

    # ── Phase 1: Researcher writes findings ───────────────────
    print("═══ PHASE 1: Researcher agent writes findings ═══\n")

    async with Workspace(source="research-agent", **ws_kwargs) as researcher:

        await researcher.write("research/market-trends.md", """\
---
type: research
topic: AI agents
confidence: high
tags: [market, trends, AI]
---
# AI Agent Market Trends

## Key Findings
- Agent framework adoption grew 300% in 2025
- Enterprise spending on agent infrastructure: $5.2B
- Top use cases: code generation, data analysis, customer support
- Average agent handles 47 tasks per day in production

## Data Sources
- Gartner Q4 2025 report
- Internal customer interviews (n=50)
- GitHub trending analysis
""")
        print("   researcher wrote: research/market-trends.md")

        await researcher.write("research/competitor-agents.md", """\
---
type: research
topic: competitors
confidence: medium
tags: [competitors, agents, analysis]
---
# Competitor Agent Analysis

## Cursor
- AI code editor with agent capabilities
- 500k+ monthly active users
- Strong developer loyalty

## Devin
- Autonomous coding agent
- Enterprise-focused pricing
- Handles full PRs end-to-end

## Replit Agent
- Browser-based agent for app building
- Targets non-developers
- Freemium model with usage limits
""")
        print("   researcher wrote: research/competitor-agents.md")

        await researcher.write("research/user-feedback.md", """\
---
type: research
topic: user feedback
confidence: high
tags: [users, feedback, qualitative]
---
# User Feedback Summary

## Top Requests
1. "I want my agent to remember what we discussed last week"
2. "Can agents share context with each other?"
3. "I need audit trails for compliance"
4. "Version history saved me from a bad agent output"

## Satisfaction Scores
- Overall: 4.2/5
- Reliability: 4.5/5
- Speed: 3.8/5
- Context retention: 3.1/5 (biggest gap)
""")
        print("   researcher wrote: research/user-feedback.md")
        print()

    # ── Phase 2: Analyst reads and builds on research ─────────
    print("═══ PHASE 2: Analyst agent reads and writes analysis ═══\n")

    async with Workspace(source="analysis-agent", **ws_kwargs) as analyst:

        # Search for research files
        research = await analyst.search(filters={"type": "research"})
        print(f"   analyst found {research['total']} research files")

        # Read each research file
        trends = await analyst.read("research/market-trends.md")
        print(f"   read: {trends['path']} (topic: {trends['frontmatter'].get('topic')})")

        competitors = await analyst.read("research/competitor-agents.md")
        print(f"   read: {competitors['path']} (topic: {competitors['frontmatter'].get('topic')})")

        feedback = await analyst.read("research/user-feedback.md")
        print(f"   read: {feedback['path']} (topic: {feedback['frontmatter'].get('topic')})")

        # Write analysis based on all research
        await analyst.write("analysis/strategic-brief.md", """\
---
type: analysis
based_on: [research/market-trends.md, research/competitor-agents.md, research/user-feedback.md]
status: final
tags: [strategy, synthesis, actionable]
---
# Strategic Brief: Agent Workspace Opportunity

## Synthesis
Based on market research, competitor analysis, and user feedback,
there is a clear opportunity in persistent agent context.

## Key Insight
The market is growing at 300% YoY but users rate context retention
at only 3.1/5 — the biggest satisfaction gap. This is our opening.

## Recommendations
1. **Double down on persistence** — our core differentiator
2. **Multi-agent collaboration** — competitors don't offer this
3. **Audit trails** — enterprise requirement, user-requested
4. **Version history** — already loved, market it harder

## Competitive Position
- Cursor: code-only, no persistent workspace
- Devin: enterprise but no shared context layer
- Replit: consumer-focused, no enterprise features
- **Us: the persistent workspace layer for all agents**
""")
        print(f"\n   analyst wrote: analysis/strategic-brief.md")
        print()

    # ── Phase 3: Audit trail ──────────────────────────────────
    print("═══ PHASE 3: Audit trail — who wrote what and when ═══\n")

    async with Workspace(source="admin", **ws_kwargs) as admin:

        audit_log = await admin.audit(limit=10)
        print(f"   total audit entries: {audit_log['total']}")
        print()
        print(f"   {'Action':<8} {'Path':<40} {'Source':<16}")
        print(f"   {'─'*8} {'─'*40} {'─'*16}")
        for entry in audit_log["entries"]:
            action = entry.get("action", "?")
            path = entry.get("file_path", "?")
            source = entry.get("agent_id", entry.get("source", "?"))
            print(f"   {action:<8} {path:<40} {source:<16}")
        print()

        # Filter by specific agent
        researcher_actions = await admin.audit(agent_id="research-agent")
        print(f"   research-agent actions: {researcher_actions['total']}")

        analyst_actions = await admin.audit(agent_id="analysis-agent")
        print(f"   analysis-agent actions: {analyst_actions['total']}")
        print()

    print("Done. Multi-agent collaboration demonstrated successfully.")


if __name__ == "__main__":
    asyncio.run(main())
