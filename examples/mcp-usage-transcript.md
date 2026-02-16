# Sayou in Action — Claude Code Transcript

This shows what it looks like when Claude Code uses sayou as persistent memory.

---

**User:** Research competitor pricing for our enterprise tier and save your findings.

**Claude Code:** I'll research this and save my findings to the workspace.

*[Uses workspace_write to save research/competitor-pricing.md]*

> Saved research to `research/competitor-pricing.md` with frontmatter:
> - status: draft
> - topic: competitor-pricing
> - date: 2025-02-16

---

**User (next day, new session):** What did we learn about competitor pricing?

**Claude Code:** Let me check our workspace.

*[Uses workspace_search with query "competitor pricing"]*

> Found `research/competitor-pricing.md` (saved yesterday)
>
> Key findings:
> - Competitor A: $99/seat/month (annual)
> - Competitor B: $149/seat/month (includes support)
> - Competitor C: $79/seat/month (limited features)

---

**User:** Update the status to "reviewed" and add my notes.

**Claude Code:** *[Uses workspace_read to get current content, then workspace_write to create new version]*

> Updated `research/competitor-pricing.md` (version 2)
> - Changed status: draft → reviewed
> - Added your review notes

---

**User:** Show me the diff between the original and updated version.

**Claude Code:** *[Uses workspace_history with version_a=1, version_b=2]*

> ```diff
> - status: draft
> + status: reviewed
> + reviewer_notes: |
> +   Competitor B is closest to our positioning.
> +   Consider matching their support inclusion.
> ```

---

**User:** Find all files tagged as "reviewed" across the workspace.

**Claude Code:** *[Uses workspace_search with filters {"status": "reviewed"}]*

> Found 3 reviewed files:
> - research/competitor-pricing.md
> - research/market-analysis.md
> - planning/q2-roadmap.md

---

**User:** Save the current API config as a KV setting so we remember it.

**Claude Code:** *[Uses workspace_kv action="set" key="config.api_tier" value="enterprise"]*

> Set config.api_tier = "enterprise"

---

## What's happening under the hood

1. Every `workspace_write` creates a new **version** — nothing is ever overwritten
2. YAML **frontmatter** (the `---` block) is automatically indexed for search
3. Files persist in `~/.sayou/` across sessions — no setup needed
4. The agent chooses which tool to use based on the task at hand
