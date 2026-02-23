"""E2E integration test: simulates an OpenCode agent using sayou via MCP.

Tests the EXACT code path an OpenCode user would hit:
  1. OpenCode connects sayou as MCP server
  2. Plugin calls workspace_context on session.created
  3. Plugin injects result into system prompt via experimental.chat.system.transform
  4. User says "I don't like camelCase" → agent calls workspace_write
  5. New session → workspace_context returns the preference
  6. Agent follows the preference without user repeating themselves

Unlike test_preference_e2e.py (which tests WorkspaceService directly),
this test calls through the MCP server's call_tool() — the same interface
any MCP client (OpenCode, Cline, aider, generic) would use.
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sayou.catalog.models import Base
from sayou.server import _format_context_result, create_server


# ── Fixtures ─────────────────────────────────────────────────


class InMemoryStorage:
    """In-memory storage that replaces S3 for testing."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def generate_key(self, org_id, workspace_id, version_id):
        return f"{org_id}/sayou/{workspace_id}/{version_id}"

    def calculate_checksum(self, content):
        import hashlib
        return hashlib.sha256(content).hexdigest()

    async def upload_version(self, content, org_id, workspace_id, version_id, content_type="text/markdown"):
        key = self.generate_key(org_id, workspace_id, version_id)
        content_hash = self.calculate_checksum(content)
        self._store[key] = content
        return key, "test-bucket", len(content), content_hash

    async def download_version(self, s3_key, bucket=None):
        return self._store[s3_key]

    async def ensure_bucket(self):
        pass

    async def close(self):
        pass


@pytest_asyncio.fixture
async def mcp_server():
    """Create a real MCP server with in-memory DB + storage.

    Returns (server, ws) where server.call_tool() is the same
    interface any MCP client would use.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def test_get_db():
        session = session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    storage = InMemoryStorage()

    # Patch get_db and create server
    with patch("sayou.core.workspace.get_db", test_get_db):
        server, ws = create_server()
        # Replace the WorkspaceService storage with our in-memory one
        ws.storage = storage
        ws._custom_get_db = test_get_db
        yield server, ws

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def extract_text(result) -> str:
    """Extract text content from MCP call_tool result.

    call_tool returns (list[ContentBlock], dict) or list[ContentBlock].
    """
    # Handle tuple return: (content_blocks, metadata)
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        for block in result:
            if hasattr(block, "text"):
                return block.text
    if isinstance(result, dict):
        return result.get("text", str(result))
    return str(result)


# ── Test: The Full OpenCode Agent Loop ───────────────────────


@pytest.mark.asyncio
async def test_opencode_full_loop(mcp_server):
    """Simulate 3 OpenCode sessions end-to-end via MCP call_tool().

    This is the EXACT flow an OpenCode user would experience:

    Session 1 (fresh install):
      - Plugin calls workspace_context → empty workspace
      - Plugin injects onboarding into system prompt
      - User works normally

    Session 2 (user expresses preference):
      - Plugin calls workspace_context → still no preferences
      - User says "I don't like camelCase, always use snake_case"
      - Agent calls workspace_write to persist preference
      - User says "also, never use print() for debugging, use logging"
      - Agent calls workspace_write for second preference

    Session 3 (preferences are loaded):
      - Plugin calls workspace_context → returns both preferences
      - Plugin injects them into system prompt
      - Agent follows preferences WITHOUT user repeating themselves
    """
    server, ws = mcp_server

    # ════════════════════════════════════════════════════════════
    # SESSION 1: Fresh workspace — agent sees onboarding message
    # ════════════════════════════════════════════════════════════

    result = await server.call_tool("workspace_context", {})
    session1_context = extract_text(result)

    # OpenCode plugin would inject this into system prompt
    assert "empty" in session1_context.lower()
    assert "workspace_write" in session1_context

    # Agent has no preferences to follow — this is fine

    # ════════════════════════════════════════════════════════════
    # SESSION 2: User expresses preferences during conversation
    # ════════════════════════════════════════════════════════════

    # Plugin loads context at session start
    result = await server.call_tool("workspace_context", {})
    session2_context = extract_text(result)
    # Still empty — no preferences yet
    assert "Preferences" not in session2_context

    # User says: "I don't like camelCase, always use snake_case in Python"
    # Agent detects this is a preference and saves it via MCP
    result = await server.call_tool("workspace_write", {
        "path": "preferences/naming-convention.md",
        "content": (
            "---\n"
            "type: preference\n"
            "category: code-style\n"
            "---\n"
            "Always use snake_case for Python variables, functions, and methods.\n"
            "Never use camelCase in Python code.\n"
            "Exception: class names should use PascalCase.\n"
        ),
    })
    write_result = extract_text(result)
    assert "Written" in write_result
    assert "preferences/naming-convention.md" in write_result

    # User says: "also, never use print() for debugging, use logging"
    result = await server.call_tool("workspace_write", {
        "path": "preferences/debugging.md",
        "content": (
            "---\n"
            "type: preference\n"
            "category: code-style\n"
            "---\n"
            "Never use print() for debugging. Always use the logging module.\n"
            "Configure logging at module level: logger = logging.getLogger(__name__)\n"
        ),
    })
    write_result = extract_text(result)
    assert "Written" in write_result

    # Agent also saves a decision from the conversation
    result = await server.call_tool("workspace_write", {
        "path": "decisions/api-design.md",
        "content": (
            "---\n"
            "type: decision\n"
            "status: approved\n"
            "---\n"
            "# API Design\n\n"
            "Use FastAPI with Pydantic v2 models.\n"
            "All endpoints return JSON with snake_case keys.\n"
        ),
    })
    assert "Written" in extract_text(result)

    # ════════════════════════════════════════════════════════════
    # SESSION 3: New session — preferences are auto-loaded
    # ════════════════════════════════════════════════════════════

    # This is the critical moment: OpenCode plugin calls workspace_context
    # on session.created, then injects result into system prompt
    result = await server.call_tool("workspace_context", {})
    session3_context = extract_text(result)

    # ── Verify preferences are present in the context ──
    assert "**Preferences:**" in session3_context
    assert "snake_case" in session3_context
    assert "camelCase" in session3_context
    assert "logging" in session3_context
    assert "print()" in session3_context

    # ── Verify work files are in recent files ──
    assert "decisions/api-design.md" in session3_context

    # ── Verify preferences are NOT in recent files (clean separation) ──
    # Extract lines between "**Recent files**" and the next "**" section
    import re
    recent_match = re.search(
        r"\*\*Recent files\*\*[^\n]*\n((?:[ \t]+- .+\n?)+)",
        session3_context,
    )
    assert recent_match, f"No 'Recent files' section found in:\n{session3_context}"
    recent_section_text = recent_match.group(1)
    assert "preferences/" not in recent_section_text
    assert "decisions/api-design.md" in recent_section_text

    # ── Simulate what OpenCode's system.transform would inject ──
    # This is what the LLM actually sees in its system prompt
    system_prompt_injection = (
        "## Workspace Context (from sayou)\n\n"
        + session3_context + "\n\n"
        + "Follow all preferences listed above. "
        + "When the user expresses new preferences, silently save them "
        + "using workspace_write to preferences/ with frontmatter type: preference."
    )

    # The system prompt now contains the user's preferences
    assert "snake_case" in system_prompt_injection
    assert "logging" in system_prompt_injection
    assert "decisions/api-design.md" in system_prompt_injection


@pytest.mark.asyncio
async def test_opencode_preference_update_via_mcp(mcp_server):
    """User corrects a preference → agent updates it → next session sees update."""
    server, ws = mcp_server

    # Session 1: Agent saves initial preference
    await server.call_tool("workspace_write", {
        "path": "preferences/indentation.md",
        "content": "---\ntype: preference\n---\nUse 4 spaces for indentation.\n",
    })

    # Verify it's loaded
    result = await server.call_tool("workspace_context", {})
    ctx = extract_text(result)
    assert "4 spaces" in ctx

    # Session 2: User says "actually, use 2 spaces"
    await server.call_tool("workspace_write", {
        "path": "preferences/indentation.md",
        "content": "---\ntype: preference\n---\nUse 2 spaces for indentation.\n",
    })

    # Session 3: Only updated preference is loaded
    result = await server.call_tool("workspace_context", {})
    ctx = extract_text(result)
    assert "2 spaces" in ctx
    assert "4 spaces" not in ctx


@pytest.mark.asyncio
async def test_opencode_tool_descriptions_guide_agent(mcp_server):
    """Verify tool descriptions contain enough guidance for any LLM.

    OpenCode (and any generic MCP client) surfaces tool descriptions
    to the LLM. These descriptions must be self-guiding enough that
    the agent knows WHAT to do without platform-specific hooks.
    """
    server, ws = mcp_server
    tools = await server.list_tools()
    tool_map = {t.name: t for t in tools}

    # workspace_context description must tell agent to call it first
    ctx_desc = tool_map["workspace_context"].description
    assert "beginning" in ctx_desc.lower() or "start" in ctx_desc.lower()
    assert "session" in ctx_desc.lower()
    assert "preferences" in ctx_desc.lower()
    assert "MUST" in ctx_desc or "IMPORTANT" in ctx_desc

    # workspace_write description must mention preference persistence
    write_desc = tool_map["workspace_write"].description
    assert "preferences/" in write_desc
    assert "preference" in write_desc.lower()

    # workspace_context description must tell agent to save preferences
    assert "save" in ctx_desc.lower() or "write" in ctx_desc.lower()
    assert "workspace_write" in ctx_desc


@pytest.mark.asyncio
async def test_opencode_server_instructions(mcp_server):
    """Verify server instructions exist (for clients that support them)."""
    server, ws = mcp_server

    assert server.instructions is not None
    assert "workspace_context" in server.instructions
    assert "preferences/" in server.instructions
    assert "Do not ask permission" in server.instructions


@pytest.mark.asyncio
async def test_opencode_incremental_rule_learning(mcp_server):
    """The core use case: agent incrementally learns user's rules.

    Simulates 5 sessions where user gradually teaches the agent:
    1. Naming conventions
    2. Error handling style
    3. Testing preferences
    4. Documentation style
    5. Verify ALL rules are loaded together
    """
    server, ws = mcp_server

    # Session 1: "I prefer snake_case"
    await server.call_tool("workspace_write", {
        "path": "preferences/naming.md",
        "content": "---\ntype: preference\ncategory: code-style\n---\nUse snake_case everywhere in Python.\n",
    })

    ctx = extract_text(await server.call_tool("workspace_context", {}))
    assert "snake_case" in ctx

    # Session 2: "Always catch specific exceptions"
    await server.call_tool("workspace_write", {
        "path": "preferences/error-handling.md",
        "content": "---\ntype: preference\ncategory: code-style\n---\nNever use bare except. Always catch specific exceptions.\n",
    })

    ctx = extract_text(await server.call_tool("workspace_context", {}))
    assert "snake_case" in ctx  # still there
    assert "bare except" in ctx  # new one added

    # Session 3: "Use pytest, not unittest"
    await server.call_tool("workspace_write", {
        "path": "preferences/testing.md",
        "content": "---\ntype: preference\ncategory: testing\n---\nUse pytest. Never use unittest.TestCase.\nPrefer fixtures over setUp/tearDown.\n",
    })

    ctx = extract_text(await server.call_tool("workspace_context", {}))
    assert "snake_case" in ctx
    assert "bare except" in ctx
    assert "pytest" in ctx

    # Session 4: "Don't write docstrings for obvious functions"
    await server.call_tool("workspace_write", {
        "path": "preferences/documentation.md",
        "content": "---\ntype: preference\ncategory: documentation\n---\nDon't add docstrings to obvious functions.\nOnly document non-obvious behavior and public APIs.\n",
    })

    ctx = extract_text(await server.call_tool("workspace_context", {}))
    assert "snake_case" in ctx
    assert "bare except" in ctx
    assert "pytest" in ctx
    assert "docstrings" in ctx

    # Session 5: Verify ALL 4 preferences load together
    result = await server.call_tool("workspace_context", {})
    final_context = extract_text(result)

    # All preferences accumulated across 4 sessions
    assert "**Preferences:**" in final_context
    assert "snake_case" in final_context
    assert "bare except" in final_context
    assert "pytest" in final_context
    assert "docstrings" in final_context

    # Count preference files shown
    pref_count = final_context.count("preferences/")
    assert pref_count >= 4, f"Expected 4+ preference references, got {pref_count}"


@pytest.mark.asyncio
async def test_opencode_workspace_context_then_search(mcp_server):
    """Agent can search workspace for past decisions after loading context."""
    server, ws = mcp_server

    # Build up some workspace content across "sessions"
    await server.call_tool("workspace_write", {
        "path": "decisions/database.md",
        "content": "---\ntype: decision\nstatus: approved\n---\n# Database\nUse PostgreSQL with SQLAlchemy async.\n",
    })
    await server.call_tool("workspace_write", {
        "path": "decisions/auth.md",
        "content": "---\ntype: decision\nstatus: approved\n---\n# Auth\nUse JWT with refresh tokens.\n",
    })
    await server.call_tool("workspace_write", {
        "path": "preferences/style.md",
        "content": "---\ntype: preference\n---\nPrefer composition over inheritance.\n",
    })

    # New session: load context
    ctx = extract_text(await server.call_tool("workspace_context", {}))
    assert "composition" in ctx  # preference loaded
    assert "decisions/database.md" in ctx  # decisions in recent files

    # Agent searches for past decisions
    search_result = extract_text(await server.call_tool("workspace_search", {
        "filters": {"type": "decision"},
    }))
    assert "database.md" in search_result
    assert "auth.md" in search_result

    # Agent reads a specific decision
    read_result = extract_text(await server.call_tool("workspace_read", {
        "path": "decisions/database.md",
    }))
    assert "PostgreSQL" in read_result
    assert "SQLAlchemy" in read_result
