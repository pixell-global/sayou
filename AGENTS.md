# Sayou Workspace

You have access to a persistent workspace via sayou MCP tools.

## Key behaviors

1. **Session start**: The sayou plugin automatically loads workspace context (preferences, recent files, activity). Follow all user preferences.
2. **Preference persistence**: When the user corrects you or expresses preferences ("I don't like X", "always use Y"), save them to `preferences/` using `workspace_write` with frontmatter `type: preference`. Do not announce it.
3. **Knowledge persistence**: Save important decisions, research, and findings to the workspace so they survive across sessions.
4. **Retrieval**: Use `workspace_search` or `workspace_read` to find past work before re-doing it.

## File conventions

| Folder | Purpose |
|--------|---------|
| `preferences/` | User coding style, conventions, workflow rules |
| `decisions/` | Architecture and design decisions |
| `research/` | Research findings and analysis |
| `notes/` | General notes and meeting summaries |
| `activity/` | Auto-generated daily activity logs |
| `sessions/` | Auto-generated session summaries |
