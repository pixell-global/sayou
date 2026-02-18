"""Post-session conversation observer.

Runs after each conversation turn to extract observations and write them
to the workspace. This is a passive process — it never interrupts the
agent's response to the user.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import openai

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are a conversation analyst. Given a conversation turn between a user and an AI assistant, \
extract DETAILED observations that preserve ALL specific information.

Rules:
- Only extract from the CURRENT TURN. The history is provided for context only.
- Classify each observation as one of: decision, discovery, preference, fact
  - decision: user made a choice or the assistant recommended an approach that was accepted
  - discovery: new information was found (from search, research, analysis)
  - preference: user expressed a preference about tools, workflows, style, or approach
  - fact: a concrete fact was stated or confirmed (names, dates, numbers, definitions)
- Skip trivial conversations (greetings, simple Q&A with no lasting value, "hello", "thanks")
- Assign confidence: 1.0=explicitly stated, 0.7=clearly implied, 0.5=inferred
- If the assistant wrote files to the workspace, describe each artifact briefly
- Return valid JSON

CRITICAL — Be exhaustively detailed:
- ALWAYS preserve exact numbers, versions, costs, percentages, durations, sizes, and counts. \
Losing specifics defeats the entire purpose of observation extraction.
- ALWAYS include the reasoning or rationale behind decisions, not just the decision itself.
- ALWAYS capture configuration values, parameter settings, and technical specifications verbatim.
- Use the "key_facts" array to list every specific data point from the observation.

BAD observation (too vague, loses critical details):
  "content": "Decided to use token-based authentication"

GOOD observation (preserves all specifics):
  "content": "Decided to use JWT tokens with 15-minute access token expiry and refresh tokens \
stored in HttpOnly cookies with 7-day expiry. Using RS256 algorithm with 2048-bit keys. Chose \
JWT over session-based auth for stateless API scalability.",
  "key_facts": ["JWT access tokens", "15-minute expiry", "refresh tokens in HttpOnly cookies", \
"7-day refresh expiry", "RS256 algorithm", "2048-bit keys"]

BAD observation:
  "content": "GCP is cheaper than AWS for this workload"

GOOD observation:
  "content": "GCP estimated monthly cost is $612 vs AWS at $847 for the same workload. GCP \
egress is $0.08/GB vs AWS $0.12/GB. GCP offers $100K startup credit. Team has 2 engineers \
with GCP experience.",
  "key_facts": ["GCP $612/month", "AWS $847/month", "GCP egress $0.08/GB", "AWS egress \
$0.12/GB", "$100K GCP startup credit", "2 engineers with GCP experience"]

Output format:
{
  "is_trivial": false,
  "summary": "One sentence summarizing this turn",
  "topics": ["topic-a", "topic-b"],
  "observations": [
    {
      "type": "decision|discovery|preference|fact",
      "content": "Detailed description preserving ALL specific values and reasoning",
      "key_facts": ["specific-value-1", "specific-value-2"],
      "confidence": 0.7,
      "topics": ["relevant-topic"]
    }
  ],
  "artifact_descriptions": [
    {
      "path": "artifacts/2026-02-18-research.md",
      "description": "Research notes on MCP servers"
    }
  ]
}

If the conversation is trivial (greeting, thanks, simple factual Q&A), return:
{"is_trivial": true, "summary": "", "topics": [], "observations": [], "artifact_descriptions": []}
"""


@dataclass
class Observation:
    """A single extracted observation."""

    type: str  # decision, discovery, preference, fact
    content: str
    confidence: float = 0.7
    topics: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of LLM extraction from a conversation turn."""

    observations: list[Observation] = field(default_factory=list)
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    is_trivial: bool = True
    artifact_descriptions: list[dict[str, str]] = field(default_factory=list)


class ConversationObserver:
    """Extracts observations from conversation turns and writes them to the workspace."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def observe(
        self,
        workspace,
        session_id: str,
        user_message: str,
        collected_events: list[dict],
        artifact_paths: list[str],
        history: list[dict],
    ) -> None:
        """Main entry point. Called from orchestrator's finally block.

        Never raises — all errors are caught and logged.
        """
        try:
            if not user_message.strip() and not collected_events:
                return

            transcript = self._build_transcript(user_message, collected_events)

            result = await self._extract(transcript, history)
            if result.is_trivial:
                logger.debug("Trivial conversation, skipping observation write")
                return

            # Write conversation file
            conv_path = self._conversation_path(session_id)
            content = self._format_conversation_file(
                result, session_id, user_message, artifact_paths
            )
            await workspace.write(conv_path, content, source="observer")

            # Link artifacts to conversation
            for art_path in artifact_paths:
                try:
                    await workspace.add_link(
                        art_path, conv_path, link_type="parent", context="produced during conversation"
                    )
                except Exception as e:
                    logger.warning(f"Failed to link artifact {art_path} to {conv_path}: {e}")

            # Update preferences if any preference observations exist
            preference_obs = [o for o in result.observations if o.type == "preference"]
            if preference_obs:
                try:
                    await self._update_preferences(workspace, preference_obs)
                except Exception as e:
                    logger.warning(f"Failed to update preferences: {e}")

        except Exception as e:
            logger.error(f"Observer failed (non-fatal): {e}")

    def _build_transcript(self, user_message: str, collected_events: list[dict]) -> str:
        """Reconstruct a readable transcript from events."""
        parts: list[str] = []
        parts.append(f"User: {user_message}")
        parts.append("")

        content_parts: list[str] = []
        for event in collected_events:
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "content":
                text = data.get("text", "")
                if text:
                    content_parts.append(text)

            elif event_type == "tool_use":
                # Flush accumulated content before tool call
                if content_parts:
                    parts.append(f"Assistant: {''.join(content_parts)}")
                    parts.append("")
                    content_parts = []

                name = data.get("name", "unknown")
                args = data.get("arguments", "{}")
                # Truncate long arguments (10K chars, generous for most tool inputs)
                if len(args) > 10000:
                    args = args[:10000] + "..."
                parts.append(f"[Tool call: {name}({args})]")

            elif event_type == "tool_result":
                result_text = data.get("result", "")
                # Truncate long results (50K chars ≈ 12.5K tokens, well within 128K context)
                if len(result_text) > 50000:
                    result_text = result_text[:50000] + "..."
                parts.append(f"[Tool result: {result_text}]")
                parts.append("")

        # Flush remaining content
        if content_parts:
            parts.append(f"Assistant: {''.join(content_parts)}")

        return "\n".join(parts)

    async def _extract(self, transcript: str, history: list[dict]) -> ExtractionResult:
        """Call LLM to extract observations from the transcript."""
        try:
            # Build context from last 6 history messages
            context_messages: list[dict] = []
            recent_history = history[-6:] if len(history) > 6 else history
            for msg in recent_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    context_messages.append({"role": role, "content": content})

            messages = [
                {"role": "system", "content": EXTRACTION_PROMPT},
            ]

            if context_messages:
                history_text = "\n".join(
                    f"{m['role'].title()}: {m['content'][:500]}" for m in context_messages
                )
                messages.append(
                    {"role": "user", "content": f"CONVERSATION HISTORY (for context only):\n{history_text}"}
                )

            messages.append(
                {"role": "user", "content": f"CURRENT TURN (extract from this):\n{transcript}"}
            )

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
                max_tokens=16384,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            return self._parse_extraction(data)

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return ExtractionResult(is_trivial=True)

    def _parse_extraction(self, data: dict) -> ExtractionResult:
        """Parse LLM JSON response into ExtractionResult."""
        if data.get("is_trivial", True):
            return ExtractionResult(is_trivial=True)

        observations = []
        for obs_data in data.get("observations", []):
            obs = Observation(
                type=obs_data.get("type", "fact"),
                content=obs_data.get("content", ""),
                confidence=obs_data.get("confidence", 0.7),
                topics=obs_data.get("topics", []),
                key_facts=obs_data.get("key_facts", []),
            )
            if obs.content:
                observations.append(obs)

        return ExtractionResult(
            observations=observations,
            summary=data.get("summary", ""),
            topics=data.get("topics", []),
            is_trivial=False,
            artifact_descriptions=data.get("artifact_descriptions", []),
        )

    def _format_conversation_file(
        self,
        result: ExtractionResult,
        session_id: str,
        user_message: str,
        artifact_paths: list[str],
    ) -> str:
        """Build markdown content with YAML frontmatter."""
        now = datetime.now(timezone.utc)
        obs_types = sorted({o.type for o in result.observations})

        # Build frontmatter
        lines = ["---"]
        lines.append(f"date: {now.strftime('%Y-%m-%d')}")
        lines.append("type: conversation")
        lines.append(f"session: {session_id}")
        if result.topics:
            topics_str = ", ".join(result.topics)
            lines.append(f"topics: [{topics_str}]")
        if obs_types:
            types_str = ", ".join(obs_types)
            lines.append(f"observation_types: [{types_str}]")
        if artifact_paths:
            arts_str = ", ".join(artifact_paths)
            lines.append(f"artifacts: [{arts_str}]")
        lines.append("source: observer")
        lines.append(f"created_at: {now.isoformat()}")
        lines.append("---")
        lines.append("")

        # Summary
        if result.summary:
            lines.append(f"## Summary")
            lines.append("")
            lines.append(result.summary)
            lines.append("")

        # User prompt
        lines.append("## Prompt")
        lines.append("")
        lines.append(user_message)
        lines.append("")

        # Observations grouped by type
        grouped: dict[str, list[Observation]] = {}
        for obs in result.observations:
            grouped.setdefault(obs.type, []).append(obs)

        type_labels = {
            "decision": "Decisions",
            "discovery": "Discoveries",
            "preference": "Preferences",
            "fact": "Facts",
        }

        for obs_type in ["decision", "discovery", "preference", "fact"]:
            obs_list = grouped.get(obs_type, [])
            if not obs_list:
                continue
            label = type_labels.get(obs_type, obs_type.title())
            lines.append(f"## {label}")
            lines.append("")
            for obs in obs_list:
                confidence_marker = ""
                if obs.confidence < 1.0:
                    confidence_marker = f" (confidence: {obs.confidence})"
                lines.append(f"- {obs.content}{confidence_marker}")
                if obs.key_facts:
                    for kf in obs.key_facts:
                        lines.append(f"  - {kf}")
            lines.append("")

        # Artifact links
        if artifact_paths:
            lines.append("## Artifacts")
            lines.append("")
            for art_path in artifact_paths:
                desc = ""
                for ad in result.artifact_descriptions:
                    if ad.get("path") == art_path:
                        desc = f" — {ad['description']}"
                        break
                lines.append(f"- [{art_path}]({art_path}){desc}")
            lines.append("")

        return "\n".join(lines)

    def _conversation_path(self, session_id: str) -> str:
        """Generate conversation file path."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        short_id = session_id[:8]
        return f"conversations/{today}-{short_id}.md"

    async def _update_preferences(
        self, workspace, preferences: list[Observation]
    ) -> None:
        """Append new preference observations to profile/preferences.md."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prefs_path = "profile/preferences.md"

        # Try to read existing file
        existing_content = ""
        try:
            result = await workspace.read(prefs_path, token_budget=10000)
            existing_content = result.get("content", "")
        except Exception:
            pass

        if not existing_content:
            # Create new file with frontmatter
            lines = [
                "---",
                "type: profile",
                "source: observer",
                f"updated_at: {today}",
                "---",
                "",
                "# Preferences",
                "",
            ]
            existing_content = "\n".join(lines)

        # Append new preferences
        new_lines = [existing_content.rstrip(), ""]
        for pref in preferences:
            new_lines.append(f"- [{today}] {pref.content}")
        new_lines.append("")

        await workspace.write(prefs_path, "\n".join(new_lines), source="observer")
