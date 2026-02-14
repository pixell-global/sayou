"""
Research agent example — exercises all 8 Workspace methods.

Runs fully in-memory (SQLite + temp directory) so it leaves no artifacts.

Usage:
    python examples/research_agent.py
"""

import asyncio
import tempfile

from sayou import Workspace


async def main() -> None:
    storage_dir = tempfile.mkdtemp(prefix="sayou-example-")

    async with Workspace(
        org_id="acme-corp",
        user_id="research-agent",
        database_url="sqlite+aiosqlite://",
        storage_path=storage_dir,
        source="research-agent",
    ) as ws:

        # ── 1. Write ────────────────────────────────────────────
        print("1) WRITE — store two competitor research files\n")

        r1 = await ws.write(
            "competitors/glossier.md",
            """\
---
company: Glossier
status: active
sector: beauty
founded: 2014
---

# Glossier Competitive Analysis

Direct-to-consumer skincare brand known for minimalist packaging.

## Key Products
- Boy Brow — cult-favorite brow gel
- Cloud Paint — liquid blush
- Milky Jelly Cleanser

## Observations
Revenue estimated at $200M ARR. Strong community-driven marketing.
""",
        )
        print(f"   wrote competitors/glossier.md  (v{r1['version_number']}, {r1['size_bytes']} bytes)")

        r2 = await ws.write(
            "competitors/drunk-elephant.md",
            """\
---
company: Drunk Elephant
status: active
sector: beauty
founded: 2012
---

# Drunk Elephant Competitive Analysis

Clean skincare brand acquired by Shiseido in 2019.

## Key Products
- Protini Polypeptide Cream
- C-Firma Vitamin C Serum
- Beste No. 9 Jelly Cleanser

## Observations
Premium price point ($60-90 per SKU). Strong Sephora distribution.
""",
        )
        print(f"   wrote competitors/drunk-elephant.md  (v{r2['version_number']}, {r2['size_bytes']} bytes)")
        print()

        # ── 2. Read ─────────────────────────────────────────────
        print("2) READ — read back Glossier file\n")

        doc = await ws.read("competitors/glossier.md")
        print(f"   path:        {doc['path']}")
        print(f"   version:     {doc['version_number']}")
        print(f"   frontmatter: {doc['frontmatter']}")
        print(f"   truncated:   {doc['truncated']}")
        print(f"   content preview: {doc['content'][:80]}...")
        print()

        # ── 3. List ─────────────────────────────────────────────
        print("3) LIST — list the competitors/ folder\n")

        listing = await ws.list("competitors/")
        print(f"   folder: {listing['path']}")
        print(f"   file_count: {listing['file_count']}")
        for f in listing["files"]:
            company = f["frontmatter"].get("company", "?")
            print(f"   - {f['path']}  ({company})")
        print()

        # ── 4. Glob ─────────────────────────────────────────────
        print("4) GLOB — find all markdown files\n")

        matches = await ws.glob("**/*.md")
        print(f"   pattern: {matches['pattern']}")
        print(f"   total:   {matches['total']}")
        for f in matches["files"]:
            print(f"   - {f['path']}")
        print()

        # ── 5. Grep ─────────────────────────────────────────────
        print("5) GREP — search for 'Cleanser' in file contents\n")

        hits = await ws.grep("Cleanser")
        print(f"   query: {hits['query']}")
        print(f"   files with matches: {hits['total_files']}")
        for result in hits["results"]:
            print(f"   {result['path']} ({result['match_count']} match(es)):")
            for m in result["matches"]:
                # Extract the matching line (marked with ">") from context
                matching = [
                    ln.split("> ", 1)[1]
                    for ln in m["context"].splitlines()
                    if "> " in ln
                ]
                line_text = matching[0] if matching else m["context"].strip()
                print(f"      line {m['line_number']}: {line_text}")
        print()

        # ── 6. Search ───────────────────────────────────────────
        print("6) SEARCH — find files where status=active and sector=beauty\n")

        found = await ws.search(filters={"status": "active", "sector": "beauty"})
        print(f"   total: {found['total']}")
        for f in found["results"]:
            print(f"   - {f['path']}  (company: {f['frontmatter'].get('company')})")
        print()

        # ── 7. History ──────────────────────────────────────────
        print("7) HISTORY — update Glossier file, then show version history\n")

        await ws.write(
            "competitors/glossier.md",
            """\
---
company: Glossier
status: active
sector: beauty
founded: 2014
updated_note: added 2025 revenue estimate
---

# Glossier Competitive Analysis (Updated)

Revenue now estimated at $275M ARR after international expansion.
""",
        )

        hist = await ws.history("competitors/glossier.md")
        print(f"   total versions: {hist['total']}")
        for v in hist["versions"]:
            print(f"   - v{v['version_number']}  {v['size_bytes']} bytes  (hash: {v['content_hash'][:12]}...)")
        print()

        # ── 8. Delete ───────────────────────────────────────────
        print("8) DELETE — soft-delete Drunk Elephant file, verify it's gone\n")

        await ws.delete("competitors/drunk-elephant.md")
        after = await ws.list("competitors/")
        remaining = [f["path"] for f in after["files"]]
        print(f"   files remaining in competitors/: {remaining}")
        print(f"   drunk-elephant.md deleted: {'competitors/drunk-elephant.md' not in remaining}")
        print()

    print("Done. All 8 methods exercised successfully.")


if __name__ == "__main__":
    asyncio.run(main())
