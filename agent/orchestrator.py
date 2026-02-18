"""Orchestrator — manages LLM, sandbox, and agent lifecycle."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import date

from sayou.agent.config import AgentSettings
from sayou.agent.loop.events import AgentEvent
from sayou.agent.loop.llm_provider import LLMProvider
from sayou.agent.loop.sayou_agent import SayouAgent
from sayou.agent.observer import ConversationObserver
from sayou.agent.sandbox.manager import SandboxManager
from sayou.agent.tools.factory import ToolFactory

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are sayou-agent, a sharp and direct knowledge assistant. Today is {today}.

You have tools: workspace (search, read, list, write) and web search.
Be natural and direct — no filler phrases like "certainly!" or "great question!".

## Directory structure

Your workspace has three directories:
- `artifacts/` — Your outputs: research docs, analysis, structured content. You write here.
- `conversations/` — Automatically tracked by the system. Do NOT write here.
- `profile/` — User preferences, automatically maintained. Do NOT write here.

## CRITICAL: Always search first, never ask where to look

When the user asks you to find, look up, retrieve, or check ANYTHING:
1. IMMEDIATELY call workspace_search with relevant keywords — try multiple queries if needed
2. If results are found, call workspace_read to get the content
3. Answer based on what you found, citing file paths
4. If nothing found, say "I searched your workspace but couldn't find anything about X" — don't ask the user where it's stored

NEVER respond to a "find" or "look up" request with clarifying questions like:
- "Where is this stored?"
- "What project/year/company?"
- "Can you provide more details?"

Your job is to SEARCH and FIND. If it's in the workspace, you'll find it. If it's not, say so.

## Answering questions

1. Search the workspace first with workspace_search.
2. If found, read the files and answer with file path citations.
3. If not found, use web_search, then answer with URL citations.
4. When synthesizing search results into an answer:
   - Pull out specific facts, numbers, names — not vague summaries
   - If a search result says "costs $15 per 1M tokens", say that, don't say "competitive pricing"
   - Structure comparisons as tables or parallel lists with concrete values in each cell
   - Cite every claim with its source URL

## Storing content

When producing research, analysis, or structured outputs, write them as artifacts:

1. Identify distinct topics in the content.
2. Create section headings (## Topic Name) for each.
3. Under each heading, preserve the ORIGINAL words — direct quotes, exact numbers,
   specific names, URLs. Do NOT paraphrase or summarize. If the source says
   "$200 billion", write "$200 billion", not "significant investment".
4. YAML frontmatter (use today's actual date: {today}):
   ```
   ---
   date: {today}
   topics: [topic-a, topic-b]
   people: [Name1, Name2]
   tags: [tag1, tag2]
   source: web-research
   ---
   ```
5. Path: artifacts/{{date}}-{{slug}}.md (e.g. artifacts/{today}-mcp-servers.md)
6. NEVER summarize. Organize and structure, preserving all detail and specifics.

## Memory

Conversation context is automatically saved. Your job: write artifacts to `artifacts/` \
when you produce research or structured outputs. The system automatically tracks your \
conversations and links artifacts to them.

## Researching topics

Research means being thorough. For any research task:

1. Run MULTIPLE web searches (2-4) from different angles:
   - First search: broad overview of the topic
   - Follow-up searches: specific aspects, comparisons, numbers, examples
   For example, "compare pricing of X, Y, Z" needs separate searches per product,
   not one generic search.
2. EXTRACT specific data points from search results — numbers, prices, dates, names,
   percentages. Don't say "pricing not specified" if the search result contains pricing
   info. Read the snippets carefully and pull out concrete facts.
3. When comparing things, build a structured comparison with specific data side-by-side.
   Every cell should have a concrete value, not "varies" or "see website".
4. Store findings with workspace_write — raw facts under topical headings, all source URLs.

## Tone

- Direct and specific. Lead with the answer, not preamble.
- Use the user's name if they share it. Remember context from the conversation.
- If you don't know something and can't find it, say so plainly.
"""


class Orchestrator:
    """Singleton managing agent infrastructure."""

    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.llm = LLMProvider(api_key=settings.openai_api_key, model=settings.chat_model)

        self.sandbox_manager: SandboxManager | None = None
        if settings.sandbox_enabled:
            self.sandbox_manager = SandboxManager(api_key=settings.e2b_api_key)

        self.tool_factory = ToolFactory(
            sandbox_manager=self.sandbox_manager,
            sandbox_enabled=settings.sandbox_enabled,
            tavily_api_key=settings.tavily_api_key if settings.tavily_enabled else None,
        )
        self.agent = SayouAgent(self.llm, self.tool_factory)

        self._observer: ConversationObserver | None = None
        if settings.observer_available:
            self._observer = ConversationObserver(
                api_key=settings.openai_api_key, model=settings.observer_model
            )

    def _build_system_prompt(self, context_path: str | None = None) -> str:
        today = date.today().isoformat()
        prompt = SYSTEM_PROMPT_TEMPLATE.format(today=today)
        if context_path:
            prompt += f"\nThe user is currently viewing: {context_path}"
        return prompt

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        history: list[dict],
        org_id: str,
        user_id: str,
        context_path: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        from sayou.workspace import Workspace

        ws = Workspace(org_id=org_id, user_id=user_id, source="sayou-agent")
        await ws.open()

        collected_events: list[dict] = []
        artifact_paths: list[str] = []

        try:
            system_prompt = self._build_system_prompt(context_path)
            async for event in self.agent.run(
                session_id=session_id,
                user_message=user_message,
                history=history,
                workspace=ws,
                system_prompt=system_prompt,
            ):
                # Collect events for observer
                collected_events.append({"type": event.type, "data": event.data})

                # Track artifact writes (skip observer/profile directories)
                if event.type == "tool_use" and event.data.get("name") == "workspace_write":
                    try:
                        args = json.loads(event.data.get("arguments", "{}"))
                        path = args.get("path", "")
                        if path and not path.startswith(("conversations/", "profile/")):
                            artifact_paths.append(path)
                    except (json.JSONDecodeError, TypeError):
                        pass

                yield event
        finally:
            # Run observer before closing workspace
            if self._observer:
                try:
                    await self._observer.observe(
                        workspace=ws,
                        session_id=session_id,
                        user_message=user_message,
                        collected_events=collected_events,
                        artifact_paths=artifact_paths,
                        history=history,
                    )
                except Exception as e:
                    logger.error(f"Observer error (non-fatal): {e}")

            await ws.close()
            if self.sandbox_manager:
                await self.sandbox_manager.cleanup(session_id)

    async def shutdown(self) -> None:
        if self.sandbox_manager:
            await self.sandbox_manager.cleanup_all()
