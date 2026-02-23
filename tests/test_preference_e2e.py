"""E2E test: user preference persistence loop.

Validates the core use case from user feedback:
  "I don't like this … please change it" → Agent remembers for next time

Simulates the full loop:
  1. Session 1: User expresses a preference → agent writes to preferences/
  2. Session 2: workspace_context returns that preference at session start
  3. Agent can read the preference and follow it without user repeating themselves

Also validates:
  - Multiple preferences accumulate across sessions
  - Preferences update (overwrite) when user corrects themselves
  - workspace_context output format includes preference content
  - Server instructions mention preference persistence
"""

import pytest

from sayou.server import _format_context_result


ORG = "test-org"
USER = "test-user"
SLUG = "default"


# ── Scenario 1: Single preference round-trip ─────────────────


@pytest.mark.asyncio
async def test_preference_persists_across_sessions(workspace_service):
    """User says 'I prefer snake_case' → agent saves it → next session loads it."""

    # ── Session 1: User expresses preference, agent writes it ──
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/naming-convention.md",
        "---\ntype: preference\ncategory: code-style\n---\n"
        "Always use snake_case for Python variables and functions.\n"
        "Never use camelCase in Python code.\n",
    )

    # ── Session 2: New session starts, agent calls workspace_context ──
    context = await workspace_service.get_context(ORG, USER, SLUG)

    # Preference is loaded
    assert len(context["preferences"]) == 1
    pref = context["preferences"][0]
    assert pref["path"] == "preferences/naming-convention.md"
    assert "snake_case" in pref["content"]
    assert "camelCase" in pref["content"]
    assert pref["frontmatter"]["type"] == "preference"
    assert pref["frontmatter"]["category"] == "code-style"


# ── Scenario 2: Multiple preferences accumulate ──────────────


@pytest.mark.asyncio
async def test_multiple_preferences_accumulate(workspace_service):
    """User corrects agent multiple times → each preference persists."""

    # Session 1: "I don't like tabs, use spaces"
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/indentation.md",
        "---\ntype: preference\ncategory: formatting\n---\n"
        "Use 4 spaces for indentation, never tabs.\n",
    )

    # Session 2: "Always add type hints"
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/type-hints.md",
        "---\ntype: preference\ncategory: code-style\n---\n"
        "Always add type hints to function signatures.\n"
        "Use `from __future__ import annotations` at the top of files.\n",
    )

    # Session 3: "Use pytest, not unittest"
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/testing.md",
        "---\ntype: preference\ncategory: testing\n---\n"
        "Use pytest for all tests. Never use unittest.TestCase.\n"
        "Prefer fixtures over setup/teardown methods.\n",
    )

    # Session 4: Agent starts, loads all accumulated preferences
    context = await workspace_service.get_context(ORG, USER, SLUG)

    assert len(context["preferences"]) == 3
    contents = {p["path"]: p["content"] for p in context["preferences"]}
    assert "4 spaces" in contents["preferences/indentation.md"]
    assert "type hints" in contents["preferences/type-hints.md"]
    assert "pytest" in contents["preferences/testing.md"]


# ── Scenario 3: User updates a preference ────────────────────


@pytest.mark.asyncio
async def test_preference_updates_on_correction(workspace_service):
    """User says 'actually, use 2 spaces not 4' → preference is updated."""

    # Session 1: Original preference
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/indentation.md",
        "---\ntype: preference\n---\nUse 4 spaces for indentation.\n",
    )

    # Session 2: User corrects themselves
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/indentation.md",
        "---\ntype: preference\n---\nUse 2 spaces for indentation.\n",
    )

    # Session 3: Only the updated version is loaded
    context = await workspace_service.get_context(ORG, USER, SLUG)

    assert len(context["preferences"]) == 1
    assert "2 spaces" in context["preferences"][0]["content"]
    assert "4 spaces" not in context["preferences"][0]["content"]


# ── Scenario 4: Formatted output includes preferences ────────


@pytest.mark.asyncio
async def test_formatted_output_includes_preferences(workspace_service):
    """The MCP tool output string contains preference content for the LLM."""

    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/error-handling.md",
        "---\ntype: preference\n---\n"
        "Never use bare except clauses. Always catch specific exceptions.\n",
    )

    context = await workspace_service.get_context(ORG, USER, SLUG)
    output = _format_context_result(context)

    # The formatted output that the LLM sees must contain the preference
    assert "**Preferences:**" in output
    assert "preferences/error-handling.md" in output
    assert "bare except" in output


# ── Scenario 5: Preferences + work files coexist ─────────────


@pytest.mark.asyncio
async def test_preferences_separate_from_work_files(workspace_service):
    """Preferences don't pollute recent_files and vice versa."""

    # Agent saves user preference
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/style.md",
        "---\ntype: preference\n---\nPrefer functional style.\n",
    )

    # Agent also saves research/decisions from the session
    await workspace_service.write(
        ORG, USER, SLUG,
        "research/api-design.md",
        "---\ntype: decision\n---\n# API Design\nUse REST not GraphQL.\n",
    )
    await workspace_service.write(
        ORG, USER, SLUG,
        "notes/meeting.md",
        "# Meeting Notes\nDiscussed architecture.\n",
    )

    context = await workspace_service.get_context(ORG, USER, SLUG)

    # Preferences are in preferences section only
    pref_paths = {p["path"] for p in context["preferences"]}
    assert pref_paths == {"preferences/style.md"}

    # Work files are in recent_files only (preferences filtered out)
    recent_paths = {f["path"] for f in context["recent_files"]}
    assert "research/api-design.md" in recent_paths
    assert "notes/meeting.md" in recent_paths
    assert "preferences/style.md" not in recent_paths


# ── Scenario 6: Empty workspace shows onboarding ─────────────


@pytest.mark.asyncio
async def test_empty_workspace_onboarding_message(workspace_service):
    """Brand new user sees helpful onboarding, not a blank screen."""

    context = await workspace_service.get_context(ORG, USER, SLUG)
    output = _format_context_result(context)

    assert "empty" in output.lower()
    assert "workspace_write" in output
    assert "preferences/" in output


# ── Scenario 7: Server instructions guide preference behavior ─


def test_server_instructions_mention_preferences():
    """Server instructions tell the agent HOW to persist preferences."""
    from sayou.server import create_server

    server, _ = create_server()

    # FastMCP stores instructions on the server object
    instructions = server.instructions

    assert instructions is not None
    assert "preferences/" in instructions
    assert "workspace_context" in instructions
    assert "Do not ask permission" in instructions


# ── Scenario 8: Full agent simulation ────────────────────────


@pytest.mark.asyncio
async def test_full_agent_simulation(workspace_service):
    """Simulate 3 sessions of an agent learning user preferences.

    Session 1: User works, agent saves a decision.
    Session 2: User says "I don't like long variable names." Agent persists.
    Session 3: New session starts. Agent loads context, sees both the
               decision and the preference. Can act on the preference
               without user repeating themselves.
    """

    # ── Session 1: Agent saves work product ──
    await workspace_service.write(
        ORG, USER, SLUG,
        "decisions/auth-strategy.md",
        "---\ntype: decision\nstatus: approved\n---\n"
        "# Auth Strategy\nUse JWT with refresh tokens.\n",
    )

    ctx1 = await workspace_service.get_context(ORG, USER, SLUG)
    assert len(ctx1["recent_files"]) == 1
    assert ctx1["preferences"] == []

    # ── Session 2: User expresses preference ──
    # "I don't like long variable names, keep them short"
    # Agent detects this is a preference and saves it
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/variable-naming.md",
        "---\ntype: preference\ncategory: code-style\n---\n"
        "Keep variable names short and concise.\n"
        "Prefer: `resp` over `api_response`, `cfg` over `configuration`.\n"
        "Exception: domain-specific terms should remain descriptive.\n",
    )

    ctx2 = await workspace_service.get_context(ORG, USER, SLUG)
    assert len(ctx2["preferences"]) == 1
    assert len(ctx2["recent_files"]) == 1  # decisions/ file

    # ── Session 3: Fresh session, everything is loaded ──
    # Agent adds another preference
    await workspace_service.write(
        ORG, USER, SLUG,
        "preferences/comments.md",
        "---\ntype: preference\ncategory: code-style\n---\n"
        "Don't add obvious comments. Code should be self-documenting.\n",
    )

    ctx3 = await workspace_service.get_context(ORG, USER, SLUG)

    # Both preferences are available
    assert len(ctx3["preferences"]) == 2
    pref_paths = {p["path"] for p in ctx3["preferences"]}
    assert "preferences/variable-naming.md" in pref_paths
    assert "preferences/comments.md" in pref_paths

    # Work file is still there
    assert len(ctx3["recent_files"]) == 1
    assert ctx3["recent_files"][0]["path"] == "decisions/auth-strategy.md"

    # Formatted output contains everything the agent needs
    output = _format_context_result(ctx3)
    assert "short and concise" in output  # preference 1
    assert "self-documenting" in output   # preference 2
    assert "decisions/auth-strategy.md" in output  # work file
    assert ctx3["file_count"] == 3  # 2 prefs + 1 decision
