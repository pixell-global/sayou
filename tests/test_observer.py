"""Tests for the post-session conversation observer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.observer import ConversationObserver, ExtractionResult, Observation


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def observer():
    """Observer with a mocked OpenAI client."""
    with patch("agent.observer.openai.AsyncOpenAI"):
        obs = ConversationObserver(api_key="test-key", model="gpt-4o-mini")
    return obs


@pytest.fixture
def mock_workspace():
    """Mocked Workspace with async methods."""
    ws = AsyncMock()
    ws.write = AsyncMock(return_value={"version_number": 1})
    ws.read = AsyncMock(return_value={"content": ""})
    ws.add_link = AsyncMock(return_value={"status": "ok"})
    return ws


# ── TestTranscriptBuilder ─────────────────────────────────────────────


class TestTranscriptBuilder:
    def test_builds_from_content_events(self, observer):
        events = [
            {"type": "content", "data": {"text": "Hello, "}},
            {"type": "content", "data": {"text": "how can I help?"}},
            {"type": "complete", "data": {"content": "Hello, how can I help?"}},
        ]
        transcript = observer._build_transcript("Hi there", events)
        assert "User: Hi there" in transcript
        assert "Assistant: Hello, how can I help?" in transcript

    def test_includes_tool_calls(self, observer):
        events = [
            {"type": "tool_use", "data": {"name": "workspace_search", "arguments": '{"query": "test"}'}},
            {"type": "tool_result", "data": {"name": "workspace_search", "result": "Found 2 files"}},
            {"type": "content", "data": {"text": "I found 2 files."}},
        ]
        transcript = observer._build_transcript("Find my notes", events)
        assert "[Tool call: workspace_search" in transcript
        assert "[Tool result: Found 2 files]" in transcript

    def test_truncates_long_arguments(self, observer):
        long_args = '{"query": "' + "x" * 15000 + '"}'
        events = [
            {"type": "tool_use", "data": {"name": "workspace_write", "arguments": long_args}},
            {"type": "tool_result", "data": {"name": "workspace_write", "result": "ok"}},
        ]
        transcript = observer._build_transcript("Write something", events)
        # Arguments should be truncated to ~10K chars
        tool_line = [l for l in transcript.split("\n") if "Tool call:" in l][0]
        # The args portion should end with ...
        assert "..." in tool_line
        assert len(tool_line) < 10200

    def test_truncates_long_results(self, observer):
        long_result = "x" * 60000
        events = [
            {"type": "tool_use", "data": {"name": "workspace_read", "arguments": '{"path": "a.md"}'}},
            {"type": "tool_result", "data": {"name": "workspace_read", "result": long_result}},
        ]
        transcript = observer._build_transcript("Read file", events)
        result_line = [l for l in transcript.split("\n") if "Tool result:" in l][0]
        assert "..." in result_line
        # Should be truncated to ~50K chars
        assert len(result_line) < 50200

    def test_empty_events(self, observer):
        transcript = observer._build_transcript("Hello", [])
        assert "User: Hello" in transcript


# ── TestConversationFileFormat ─────────────────────────────────────────


class TestConversationFileFormat:
    def test_correct_frontmatter(self, observer):
        result = ExtractionResult(
            observations=[Observation(type="decision", content="Use React", confidence=1.0, topics=["frontend"])],
            summary="Discussed frontend framework choice",
            topics=["frontend", "react"],
            is_trivial=False,
        )
        content = observer._format_conversation_file(result, "abc12345-xyz", "What framework?", [])
        assert "---" in content
        assert "type: conversation" in content
        assert "session: abc12345-xyz" in content
        assert "topics: [frontend, react]" in content
        assert "source: observer" in content
        assert "observation_types: [decision]" in content

    def test_observation_grouping(self, observer):
        result = ExtractionResult(
            observations=[
                Observation(type="decision", content="Use React", confidence=1.0),
                Observation(type="discovery", content="React 19 is out", confidence=0.7),
                Observation(type="preference", content="User prefers TypeScript", confidence=0.7),
                Observation(type="decision", content="Use Next.js", confidence=1.0),
            ],
            summary="Framework discussion",
            topics=["frontend"],
            is_trivial=False,
        )
        content = observer._format_conversation_file(result, "sess-1234", "Discuss frameworks", [])

        # Check sections exist and are in the right order
        lines = content.split("\n")
        decision_idx = next(i for i, l in enumerate(lines) if l == "## Decisions")
        discovery_idx = next(i for i, l in enumerate(lines) if l == "## Discoveries")
        preference_idx = next(i for i, l in enumerate(lines) if l == "## Preferences")
        assert decision_idx < discovery_idx < preference_idx

        # Check both decisions are under Decisions
        assert "- Use React" in content
        assert "- Use Next.js" in content

    def test_artifact_links(self, observer):
        result = ExtractionResult(
            observations=[Observation(type="fact", content="Something", confidence=1.0)],
            summary="Research",
            topics=["test"],
            is_trivial=False,
            artifact_descriptions=[
                {"path": "artifacts/2026-02-18-research.md", "description": "Research on MCP"}
            ],
        )
        content = observer._format_conversation_file(
            result, "sess-1234", "Research MCP", ["artifacts/2026-02-18-research.md"]
        )
        assert "## Artifacts" in content
        assert "[artifacts/2026-02-18-research.md]" in content
        assert "Research on MCP" in content

    def test_path_generation(self, observer):
        path = observer._conversation_path("abcdef12-3456-7890")
        assert path.startswith("conversations/")
        assert "abcdef12" in path
        assert path.endswith(".md")

    def test_confidence_markers(self, observer):
        result = ExtractionResult(
            observations=[
                Observation(type="fact", content="Explicit fact", confidence=1.0),
                Observation(type="fact", content="Implied fact", confidence=0.7),
            ],
            summary="Facts",
            topics=[],
            is_trivial=False,
        )
        content = observer._format_conversation_file(result, "sess-1234", "Tell me facts", [])
        # Confidence 1.0 should NOT have a marker
        assert "- Explicit fact\n" in content
        # Confidence < 1.0 should have a marker
        assert "(confidence: 0.7)" in content


# ── TestObserveFlow ────────────────────────────────────────────────────


class TestObserveFlow:
    @pytest.mark.asyncio
    async def test_skips_trivial_conversations(self, observer, mock_workspace):
        """Trivial conversations should not produce any writes."""
        # Mock extraction to return trivial
        observer._extract = AsyncMock(return_value=ExtractionResult(is_trivial=True))

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="Hello",
            collected_events=[{"type": "content", "data": {"text": "Hi there!"}}],
            artifact_paths=[],
            history=[],
        )

        mock_workspace.write.assert_not_called()
        mock_workspace.add_link.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_and_links_for_real_conversations(self, observer, mock_workspace):
        """Non-trivial conversations should produce a write and link artifacts."""
        result = ExtractionResult(
            observations=[Observation(type="decision", content="Use Python", confidence=1.0)],
            summary="Decided on Python",
            topics=["programming"],
            is_trivial=False,
        )
        observer._extract = AsyncMock(return_value=result)

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="What language should I use?",
            collected_events=[{"type": "content", "data": {"text": "I recommend Python."}}],
            artifact_paths=["artifacts/2026-02-18-comparison.md"],
            history=[],
        )

        # Should write conversation file
        mock_workspace.write.assert_called_once()
        write_args = mock_workspace.write.call_args
        assert write_args[0][0].startswith("conversations/")
        assert write_args[1]["source"] == "observer"

        # Should link artifact
        mock_workspace.add_link.assert_called_once()
        link_args = mock_workspace.add_link.call_args
        assert link_args[0][0] == "artifacts/2026-02-18-comparison.md"
        assert link_args[1]["link_type"] == "parent"

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self, observer, mock_workspace):
        """LLM failure should not crash — should be treated as trivial."""
        observer._extract = AsyncMock(side_effect=Exception("API timeout"))

        # Should not raise
        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="Something complex",
            collected_events=[{"type": "content", "data": {"text": "Response"}}],
            artifact_paths=[],
            history=[],
        )

        mock_workspace.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_preferences_file(self, observer, mock_workspace):
        """Preference observations should update profile/preferences.md."""
        result = ExtractionResult(
            observations=[
                Observation(type="preference", content="Prefers dark mode", confidence=0.7),
                Observation(type="decision", content="Use vim", confidence=1.0),
            ],
            summary="User preferences",
            topics=["preferences"],
            is_trivial=False,
        )
        observer._extract = AsyncMock(return_value=result)

        # Simulate no existing preferences file
        mock_workspace.read = AsyncMock(side_effect=Exception("Not found"))

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="I like dark mode",
            collected_events=[{"type": "content", "data": {"text": "Noted!"}}],
            artifact_paths=[],
            history=[],
        )

        # Should have 2 writes: conversation file + preferences file
        assert mock_workspace.write.call_count == 2
        pref_call = mock_workspace.write.call_args_list[1]
        assert pref_call[0][0] == "profile/preferences.md"
        assert "Prefers dark mode" in pref_call[0][1]

    @pytest.mark.asyncio
    async def test_appends_to_existing_preferences(self, observer, mock_workspace):
        """Should append to existing preferences file, not overwrite."""
        result = ExtractionResult(
            observations=[
                Observation(type="preference", content="Prefers tabs over spaces", confidence=1.0),
            ],
            summary="Coding preference",
            topics=[],
            is_trivial=False,
        )
        observer._extract = AsyncMock(return_value=result)

        existing = (
            "---\ntype: profile\nsource: observer\nupdated_at: 2026-02-17\n---\n\n"
            "# Preferences\n\n- [2026-02-17] Prefers dark mode\n"
        )
        mock_workspace.read = AsyncMock(return_value={"content": existing})

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="I use tabs",
            collected_events=[{"type": "content", "data": {"text": "Noted."}}],
            artifact_paths=[],
            history=[],
        )

        pref_call = mock_workspace.write.call_args_list[1]
        written_content = pref_call[0][1]
        # Should contain both old and new preferences
        assert "Prefers dark mode" in written_content
        assert "Prefers tabs over spaces" in written_content

    @pytest.mark.asyncio
    async def test_empty_transcript_skips(self, observer, mock_workspace):
        """Empty transcript (no events) should skip observation."""
        observer._extract = AsyncMock()

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="",
            collected_events=[],
            artifact_paths=[],
            history=[],
        )

        observer._extract.assert_not_called()
        mock_workspace.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_link_failure_doesnt_crash(self, observer, mock_workspace):
        """If linking fails, the conversation file should still be written."""
        result = ExtractionResult(
            observations=[Observation(type="fact", content="A fact", confidence=1.0)],
            summary="Some discussion",
            topics=[],
            is_trivial=False,
        )
        observer._extract = AsyncMock(return_value=result)
        mock_workspace.add_link = AsyncMock(side_effect=Exception("Link failed"))

        await observer.observe(
            workspace=mock_workspace,
            session_id="sess-1234",
            user_message="Discuss something",
            collected_events=[{"type": "content", "data": {"text": "Here's info."}}],
            artifact_paths=["artifacts/thing.md"],
            history=[],
        )

        # Conversation file should still have been written
        mock_workspace.write.assert_called_once()


# ── TestParseExtraction ────────────────────────────────────────────────


class TestParseExtraction:
    def test_parses_valid_response(self, observer):
        data = {
            "is_trivial": False,
            "summary": "Discussed architecture",
            "topics": ["architecture", "design"],
            "observations": [
                {"type": "decision", "content": "Use microservices", "confidence": 1.0, "topics": ["architecture"]},
                {"type": "discovery", "content": "K8s supports this", "confidence": 0.7, "topics": ["infra"]},
            ],
            "artifact_descriptions": [
                {"path": "artifacts/arch.md", "description": "Architecture doc"}
            ],
        }
        result = observer._parse_extraction(data)
        assert not result.is_trivial
        assert result.summary == "Discussed architecture"
        assert len(result.observations) == 2
        assert result.observations[0].type == "decision"
        assert result.observations[1].confidence == 0.7
        assert len(result.artifact_descriptions) == 1

    def test_trivial_response(self, observer):
        data = {"is_trivial": True, "summary": "", "topics": [], "observations": [], "artifact_descriptions": []}
        result = observer._parse_extraction(data)
        assert result.is_trivial
        assert len(result.observations) == 0

    def test_skips_empty_content_observations(self, observer):
        data = {
            "is_trivial": False,
            "summary": "Test",
            "topics": [],
            "observations": [
                {"type": "fact", "content": "", "confidence": 1.0},
                {"type": "fact", "content": "Real fact", "confidence": 1.0},
            ],
        }
        result = observer._parse_extraction(data)
        assert len(result.observations) == 1
        assert result.observations[0].content == "Real fact"
