"""
CLI agent backed by OpenAI tool-use for a sayou workspace.

The LLM decides which workspace tools to call based on your
natural language input — reading, writing, searching, listing,
and deleting files all happen conversationally.

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/seed_data.py   # seed data first
    python examples/ask.py

Examples:
    "what competitors have we analyzed?"
    "add a competitor analysis for Shopify"
    "list all product files"
    "delete the mobile app product spec"
    "summarize our fundraising strategy"
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI

from sayou import Workspace

# Must match seed_data.py configuration
DATA_DIR = Path(__file__).parent / ".data"
DB_PATH = DATA_DIR / "sayou.db"
STORAGE_PATH = DATA_DIR / "storage"

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
ORG_ID = "example-org"
USER_ID = "researcher"


# ── Tool definitions for OpenAI ──────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a workspace folder. Use '/' to list all top-level folders, or a folder name like 'competitors/' to list files in it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Folder path to list (e.g. '/', 'competitors/', 'trends/')",
                        "default": "/",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list all files recursively including subfolders",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a file by its path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (e.g. 'competitors/notion.md')",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files by content keyword or frontmatter filters. Use this to find relevant files before reading them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Full-text search query (searches file content and frontmatter)",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Frontmatter key-value filters (e.g. {\"status\": \"active\", \"priority\": \"high\"})",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search file contents for a specific term and return matching lines with context. More precise than search_files for finding exact phrases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for in file contents",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or update a file in the workspace. Use YAML frontmatter (delimited by ---) at the top for metadata. Creates a new version if the file already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (e.g. 'competitors/shopify.md', 'notes/meeting.md')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content including optional YAML frontmatter",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the workspace. Only use when the user explicitly asks to delete or remove a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to delete",
                    },
                },
                "required": ["path"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a research assistant with access to a persistent workspace of files.
You can read, write, search, list, and delete files to help the user.

Guidelines:
- Use tools to look up information before answering questions.
- When writing files, use YAML frontmatter for metadata (title, status, tags, etc.).
- Follow the existing folder structure: competitors/, trends/, products/, insights/, strategy/.
  Create new folders if the content doesn't fit existing ones.
- Cite file paths when referencing specific information.
- Be concise and direct.
- When asked to add or save something, write it as a file in the workspace.
- When asked to remove or delete something, use delete_file.
"""


async def execute_tool(ws: Workspace, name: str, args: dict) -> str:
    """Execute a workspace tool and return the result as a string."""
    try:
        if name == "list_files":
            result = await ws.list(args.get("path", "/"), recursive=args.get("recursive", False))
            files = result.get("files", [])
            if not files:
                return "No files found."
            lines = []
            for f in files:
                fm = f.get("frontmatter", {})
                label = fm.get("title") or fm.get("company") or ""
                suffix = f" — {label}" if label else ""
                lines.append(f"  {f['path']}{suffix}")
            return f"{result['file_count']} files:\n" + "\n".join(lines)

        elif name == "read_file":
            result = await ws.read(args["path"], token_budget=3000)
            return f"--- {result['path']} (v{result['version_number']}) ---\n{result['content']}"

        elif name == "search_files":
            result = await ws.search(
                query=args.get("query"),
                filters=args.get("filters"),
            )
            hits = result.get("results", [])
            if not hits:
                return "No files matched the search."
            lines = [f"  {f['path']}" for f in hits]
            return f"{result['total']} matches:\n" + "\n".join(lines)

        elif name == "grep_files":
            result = await ws.grep(args["query"])
            if not result.get("results"):
                return f"No matches for '{args['query']}'."
            parts = []
            for r in result["results"]:
                for m in r["matches"]:
                    parts.append(f"  {r['path']}:{m['line_number']}: {m['context'].strip()}")
            return f"{result['total_files']} files matched:\n" + "\n".join(parts[:20])

        elif name == "write_file":
            result = await ws.write(args["path"], args["content"])
            return f"Wrote {result['path']} (v{result['version_number']}, {result['size_bytes']} bytes)"

        elif name == "delete_file":
            await ws.delete(args["path"])
            return f"Deleted {args['path']}"

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error: {e}"


async def agent_turn(client: AsyncOpenAI, ws: Workspace, messages: list) -> str:
    """Run the agent loop: call LLM, execute tools, repeat until done."""
    max_iterations = 10

    for _ in range(max_iterations):
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=messages,
            tools=TOOLS,
        )

        choice = response.choices[0]

        # If no tool calls, we're done — return the text response
        if not choice.message.tool_calls:
            return choice.message.content or ""

        # Add assistant message with tool calls
        messages.append(choice.message)

        # Execute each tool call
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            print(f"  [{tc.function.name}] {json.dumps(args, ensure_ascii=False)[:80]}")
            result = await execute_tool(ws, tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return "(Reached maximum tool iterations)"


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set.")
        print()
        print("  export OPENAI_API_KEY=sk-...")
        print("  python examples/ask.py")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"Error: No database found at {DB_PATH}")
        print()
        print("  Run seed_data.py first:")
        print("  python examples/seed_data.py")
        sys.exit(1)

    client = AsyncOpenAI()

    async with Workspace(
        org_id=ORG_ID,
        user_id=USER_ID,
        database_url=DATABASE_URL,
        storage_path=str(STORAGE_PATH),
        source="ask-agent",
    ) as ws:
        all_files = await ws.glob("**/*")
        print(f"Workspace loaded: {all_files['total']} files")
        print("Ask anything — I can read, write, search, and manage files.")
        print("Type 'quit' to exit.\n")

        # Conversation history persists across turns
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        while True:
            try:
                user_input = input("ask> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            messages.append({"role": "user", "content": user_input})

            print()
            answer = await agent_turn(client, ws, messages)
            messages.append({"role": "assistant", "content": answer})

            print()
            print(answer)
            print()


if __name__ == "__main__":
    asyncio.run(main())
