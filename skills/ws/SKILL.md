---
name: ws
description: Browse and manage sayou workspace — list files, search, view history
user_invocable: true
triggers:
  - "what's in my workspace"
  - "show workspace"
  - "list files"
  - "workspace status"
  - "browse workspace"
---

# /ws — Workspace Browser

Browse the sayou workspace. Show the user what's stored, find specific files, or check recent changes.

## Instructions

1. **Start with an overview** — use `workspace_list` with `path: "/"` and `recursive: true` to show the full file tree. Present it as a clean, readable tree with frontmatter metadata.

2. **If the user asks about a specific file**, use `workspace_read` to show its contents. Mention the version number and when it was last updated.

3. **If the user asks about changes**, use `workspace_history` on the relevant file to show version history. Offer to diff specific versions.

4. **If the workspace is empty**, tell the user:
   - Use `/save` to save findings or decisions from this session
   - Ask Claude to "save a note about [topic]" to create a file
   - Files support YAML frontmatter for metadata (status, type, tags, etc.)

5. **For large workspaces**, use `workspace_search` or `workspace_grep` to find specific files rather than listing everything.

## Output Format

Show files as a tree with key metadata:

```
research/
  competitor-analysis.md    status=draft     [v3, 2d ago]
  market-sizing.md          status=reviewed  [v1, 5d ago]
decisions/
  auth-architecture.md      status=approved  [v2, 1w ago]
notes/
  standup-2026-02-19.md     type=meeting     [v1, today]
```

Keep it concise. Don't read every file's contents unless asked — the tree overview is usually enough.
