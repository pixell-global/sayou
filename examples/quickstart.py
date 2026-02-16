"""
Quickstart — the simplest possible sayou example.

Runs fully in-memory. Copy-paste and run in 10 seconds.

Usage:
    python examples/quickstart.py
"""

import asyncio

from sayou import Workspace


async def main() -> None:
    async with Workspace(database_url="sqlite+aiosqlite://") as ws:
        # Write a file with YAML frontmatter
        result = await ws.write("notes/hello.md", """\
---
status: active
tags: [demo, quickstart]
---
# Hello from sayou
This file is versioned and searchable.
""")
        print(f"Wrote {result['path']} (v{result['version_number']})")

        # Read it back
        doc = await ws.read("notes/hello.md")
        print(f"Content: {doc['content'][:40].strip()}...")
        print(f"Frontmatter: {doc['frontmatter']}")

        # Search by frontmatter
        results = await ws.search(filters={"status": "active"})
        print(f"Search: {results['total']} active file(s)")

        # List a folder
        folder = await ws.list("notes/")
        print(f"Folder: {folder['file_count']} file(s) in notes/")


if __name__ == "__main__":
    asyncio.run(main())
