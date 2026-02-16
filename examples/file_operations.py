"""
File operations — move, copy, binary files, and glob patterns.

Simulates an agent organizing a research workspace:
  - Writing files to an inbox
  - Moving files to appropriate folders
  - Copying files for different purposes
  - Handling binary content
  - Finding files with glob patterns

Runs fully in-memory (SQLite + temp directory) so it leaves no artifacts.

Usage:
    python examples/file_operations.py
"""

import asyncio
import base64
import tempfile

from sayou import Workspace


async def main() -> None:
    storage_dir = tempfile.mkdtemp(prefix="sayou-ops-")

    async with Workspace(
        org_id="acme-corp",
        user_id="file-agent",
        database_url="sqlite+aiosqlite://",
        storage_path=storage_dir,
        source="file-agent",
    ) as ws:

        # ── 1. Write files to inbox ──────────────────────────────
        print("1) WRITE — create files in an inbox folder\n")

        await ws.write("inbox/meeting-notes.md", """\
---
type: notes
date: "2026-02-15"
attendees: [alice, bob, charlie]
---
# Sprint Planning Meeting
- Discussed auth system timeline
- Bob to handle SSO integration
- Next meeting: Friday
""")

        await ws.write("inbox/competitor-report.md", """\
---
type: report
company: Acme Corp
status: draft
---
# Acme Corp Competitive Analysis
Initial research on their product offering.
""")

        await ws.write("inbox/api-design.md", """\
---
type: spec
status: review
---
# REST API Design
Endpoint naming conventions and versioning strategy.
""")

        files = await ws.list("inbox/")
        print(f"   inbox/ has {files['file_count']} files:")
        for f in files["files"]:
            print(f"     - {f['path']}")
        print()

        # ── 2. Move — organize files into folders ─────────────────
        print("2) MOVE — organize files from inbox to proper folders\n")

        r1 = await ws.move("inbox/meeting-notes.md", "meetings/2026-02-15-sprint.md")
        print(f"   moved: {r1['source']} → {r1['destination']}")

        r2 = await ws.move("inbox/competitor-report.md", "research/competitors/acme.md")
        print(f"   moved: {r2['source']} → {r2['destination']}")

        r3 = await ws.move("inbox/api-design.md", "specs/api-design.md")
        print(f"   moved: {r3['source']} → {r3['destination']}")

        # Verify inbox is empty
        inbox = await ws.list("inbox/")
        print(f"\n   inbox/ now has {inbox['file_count']} files (should be 0)")
        print()

        # ── 3. Copy — duplicate for different purposes ────────────
        print("3) COPY — create a copy for a different team\n")

        r4 = await ws.copy("specs/api-design.md", "shared/api-design-review.md")
        print(f"   copied: {r4['source']} → {r4['destination']}")

        # Verify both exist
        orig = await ws.read("specs/api-design.md")
        copy = await ws.read("shared/api-design-review.md")
        print(f"   original: {orig['path']} (v{orig['version_number']})")
        print(f"   copy:     {copy['path']} (v{copy['version_number']})")
        print()

        # ── 4. Binary files — store non-text content ──────────────
        print("4) BINARY — write and read binary content\n")

        # Create a minimal 1x1 red PNG (67 bytes)
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
        )

        r5 = await ws.write(
            "assets/logo.png",
            png_data,
            content_type="image/png",
        )
        print(f"   wrote {r5['path']} ({r5['size_bytes']} bytes, {r5['content_type']})")

        # Read it back
        binary_read = await ws.read("assets/logo.png")
        print(f"   read back: {binary_read['path']}")
        print(f"   content_type: {binary_read['content_type']}")
        print(f"   encoding: {binary_read.get('encoding', 'text')}")
        print()

        # ── 5. Glob — find files by pattern ───────────────────────
        print("5) GLOB — find files matching patterns\n")

        all_md = await ws.glob("**/*.md")
        print(f"   **/*.md → {all_md['total']} files:")
        for f in all_md["files"]:
            print(f"     - {f['path']}")

        all_png = await ws.glob("**/*.png")
        print(f"\n   **/*.png → {all_png['total']} files:")
        for f in all_png["files"]:
            print(f"     - {f['path']}")
        print()

        # ── 6. List — show the organized workspace ────────────────
        print("6) LIST — final workspace structure\n")

        root = await ws.list("/", recursive=True)
        print(f"   total files: {root['file_count']}")
        for f in root["files"]:
            ct = f.get("content_type", "text/markdown")
            label = " (binary)" if not ct.startswith("text/") else ""
            print(f"     {f['path']}{label}")
        print()

    print("Done. All file operations demonstrated successfully.")


if __name__ == "__main__":
    asyncio.run(main())
