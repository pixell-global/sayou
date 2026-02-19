---
name: save
description: Quick-save key findings, decisions, or notes to the sayou workspace
user_invocable: true
triggers:
  - "save this"
  - "remember this"
  - "save findings"
  - "save decision"
  - "save note"
  - "save what we learned"
---

# /save — Quick Save to Workspace

Save key knowledge from the current conversation to the sayou workspace as a structured, versioned file.

## Instructions

1. **Analyze the conversation** — identify the most important knowledge to save:
   - Decisions made (and their reasoning)
   - Research findings
   - Bug fixes and root causes
   - Architecture choices
   - Meeting notes or action items

2. **Choose a logical path** based on content type:
   - `decisions/` — architectural decisions, technology choices, design rationale
   - `research/` — competitive analysis, market research, technical investigation
   - `notes/` — meeting notes, brainstorms, general notes
   - `bugs/` — bug investigations, root causes, fixes applied
   - `guides/` — how-to guides, setup instructions, runbooks

3. **Write with YAML frontmatter** — always include structured metadata:

   ```yaml
   ---
   type: decision | research | note | bug-report | guide
   status: draft | reviewed | approved | archived
   topic: short-topic-name
   date: YYYY-MM-DD
   tags: [relevant, tags]
   ---
   ```

4. **Use `workspace_write`** to save the file. Use a descriptive filename in kebab-case (e.g., `auth-token-refresh-fix.md`).

5. **Confirm what was saved** — show the path, key frontmatter fields, and mention it's versioned (they can update it later and the old version is preserved).

## Example

If the conversation discussed choosing PostgreSQL over MySQL:

```markdown
---
type: decision
status: approved
topic: database-selection
date: 2026-02-19
tags: [database, infrastructure]
---
# Database Selection: PostgreSQL

## Decision
PostgreSQL over MySQL for the new service.

## Reasoning
- Better JSON support (JSONB) for our flexible schema needs
- Superior full-text search (eliminates need for Elasticsearch)
- Row-level security for multi-tenant isolation

## Alternatives Considered
- MySQL: Familiar to team but weaker JSON/FTS support
- MongoDB: Overkill for our relational data patterns
```

Save to: `decisions/database-selection.md`

## Tips

- If the user says "/save" without context, scan the conversation for the most significant knowledge and propose what to save
- If multiple things are worth saving, save them as separate files
- Always use `workspace_write` (not regular Write tool) — this goes to the persistent workspace, not the local filesystem
- If a file at the chosen path already exists, `workspace_write` creates a new version (nothing is overwritten)
