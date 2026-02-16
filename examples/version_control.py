"""
Versioning & diff — the persistent, never-lose-data value proposition.

Shows:
  - Writing multiple versions of a document
  - Version history with timestamps
  - Diff between any two versions
  - Time-travel reads (read old versions)
  - Token-budget summarization with section pointers
  - Read-section drill-down

Runs fully in-memory (SQLite + temp directory) so it leaves no artifacts.

Usage:
    python examples/version_control.py
"""

import asyncio
import tempfile

from sayou import Workspace


async def main() -> None:
    storage_dir = tempfile.mkdtemp(prefix="sayou-vc-")

    async with Workspace(
        org_id="acme-corp",
        user_id="product-lead",
        database_url="sqlite+aiosqlite://",
        storage_path=storage_dir,
        source="product-lead",
    ) as ws:

        # ── 1. Write v1 — initial spec ───────────────────────────
        print("1) WRITE v1 — initial project spec\n")

        r1 = await ws.write("specs/auth-system.md", """\
---
title: Authentication System Spec
status: draft
author: product-lead
priority: high
---

# Authentication System

## Overview
Users authenticate via email/password or OAuth providers.

## Requirements
- Email/password registration and login
- OAuth support for Google and GitHub
- JWT tokens for API authentication
- Session expiry after 24 hours

## Technical Notes
- Use bcrypt for password hashing
- Store refresh tokens in database
- Rate limit login attempts to 5 per minute
""")
        print(f"   wrote v{r1['version_number']} ({r1['size_bytes']} bytes)")
        print()

        # ── 2. Write v2 — add MFA requirement ────────────────────
        print("2) WRITE v2 — add MFA and SSO requirements\n")

        r2 = await ws.write("specs/auth-system.md", """\
---
title: Authentication System Spec
status: in-review
author: product-lead
priority: high
---

# Authentication System

## Overview
Users authenticate via email/password, OAuth providers, or enterprise SSO.

## Requirements
- Email/password registration and login
- OAuth support for Google, GitHub, and Microsoft
- JWT tokens for API authentication
- Session expiry after 24 hours
- Multi-factor authentication (TOTP)
- SAML 2.0 SSO for enterprise customers

## MFA Implementation
- TOTP-based (Google Authenticator, Authy)
- Backup codes (10 single-use codes)
- MFA required for admin accounts
- Grace period: 7 days after enabling

## Technical Notes
- Use bcrypt for password hashing
- Store refresh tokens in database
- Rate limit login attempts to 5 per minute
- SAML assertion consumer service endpoint
- IdP metadata import for SSO configuration
""")
        print(f"   wrote v{r2['version_number']} ({r2['size_bytes']} bytes)")
        print()

        # ── 3. Write v3 — final approved version ─────────────────
        print("3) WRITE v3 — approved with timeline\n")

        r3 = await ws.write("specs/auth-system.md", """\
---
title: Authentication System Spec
status: approved
author: product-lead
priority: high
reviewer: cto
---

# Authentication System

## Overview
Users authenticate via email/password, OAuth providers, or enterprise SSO.
This system handles 100k+ daily active users.

## Requirements
- Email/password registration and login
- OAuth support for Google, GitHub, and Microsoft
- JWT tokens for API authentication
- Session expiry after 24 hours
- Multi-factor authentication (TOTP)
- SAML 2.0 SSO for enterprise customers

## MFA Implementation
- TOTP-based (Google Authenticator, Authy)
- Backup codes (10 single-use codes)
- MFA required for admin accounts
- Grace period: 7 days after enabling

## Technical Notes
- Use bcrypt for password hashing
- Store refresh tokens in database
- Rate limit login attempts to 5 per minute
- SAML assertion consumer service endpoint
- IdP metadata import for SSO configuration

## Timeline
- Phase 1 (Week 1-2): Email/password + OAuth
- Phase 2 (Week 3-4): MFA implementation
- Phase 3 (Week 5-6): SSO integration
- Phase 4 (Week 7): Security audit and launch
""")
        print(f"   wrote v{r3['version_number']} ({r3['size_bytes']} bytes)")
        print()

        # ── 4. History — view all versions ────────────────────────
        print("4) HISTORY — view all versions\n")

        hist = await ws.history("specs/auth-system.md")
        print(f"   total versions: {hist['total']}")
        for v in hist["versions"]:
            print(f"   - v{v['version_number']}  {v['size_bytes']:>4} bytes  "
                  f"(hash: {v['content_hash'][:12]}...)")
        print()

        # ── 5. Diff — compare v1 vs v3 ────────────────────────────
        print("5) DIFF — compare v1 (draft) vs v3 (approved)\n")

        diff_result = await ws.diff("specs/auth-system.md", 1, 3)
        print(f"   has_changes: {diff_result['has_changes']}")
        print(f"   diff (first 500 chars):")
        for line in diff_result["diff"][:500].splitlines():
            print(f"   {line}")
        if len(diff_result["diff"]) > 500:
            print(f"   ... ({len(diff_result['diff'])} chars total)")
        print()

        # ── 6. Time-travel read — read v1 ─────────────────────────
        print("6) TIME-TRAVEL — read the original v1\n")

        v1 = await ws.read("specs/auth-system.md", version=1)
        print(f"   version:     {v1['version_number']}")
        print(f"   status:      {v1['frontmatter'].get('status')}")
        print(f"   had MFA?     {'MFA' in v1['content']}")

        v3 = await ws.read("specs/auth-system.md")
        print(f"\n   latest version: {v3['version_number']}")
        print(f"   status:         {v3['frontmatter'].get('status')}")
        print(f"   has MFA?        {'MFA' in v3['content']}")
        print()

        # ── 7. Token budget — summarized read ─────────────────────
        print("7) TOKEN BUDGET — read with small budget for summary\n")

        summary = await ws.read("specs/auth-system.md", token_budget=200)
        print(f"   truncated: {summary['truncated']}")
        print(f"   content preview ({len(summary['content'])} chars):")
        for line in summary["content"][:300].splitlines():
            print(f"   {line}")
        if len(summary["content"]) > 300:
            print(f"   ...")
        print()

        # ── 8. Read section — drill into specific lines ───────────
        print("8) READ SECTION — drill into a specific section\n")

        section = await ws.read_section("specs/auth-system.md", line_start=1, line_end=10)
        print(f"   lines {section['line_start']}-{section['line_end']} "
              f"of {section['total_lines']}:")
        for line in section["content"].splitlines():
            print(f"   {line}")
        print()

    print("Done. All versioning features demonstrated successfully.")


if __name__ == "__main__":
    asyncio.run(main())
