---
name: recall
description: Search past knowledge in the sayou workspace
user_invocable: true
triggers:
  - "what did we decide about"
  - "do we have research on"
  - "find notes about"
  - "what do we know about"
  - "search workspace for"
  - "recall"
---

# /recall — Search Past Knowledge

Search the sayou workspace for past decisions, research, notes, and other saved knowledge.

## Instructions

Use a multi-step search strategy to find the most relevant results:

### Step 1: Structured search (fastest)

Use `workspace_search` with the user's query. This searches file paths and frontmatter text.

```
workspace_search(query="auth architecture", limit=10)
```

If the user mentions a specific type or status, add filters:

```
workspace_search(filters={"type": "decision"}, query="database")
workspace_search(filters={"status": "approved"})
```

### Step 2: Content search (if Step 1 is insufficient)

Use `workspace_grep` to search inside file contents:

```
workspace_grep(query="PostgreSQL", context_lines=3)
```

### Step 3: Semantic search (if Steps 1-2 miss)

Use `workspace_semantic_search` for meaning-based retrieval when exact keywords don't match:

```
workspace_semantic_search(query="why we chose that database", top_k=5)
```

Note: This only works if the workspace has embeddings enabled (`SAYOU_EMBEDDING_PROVIDER` set).

### Step 4: Read and present

For each relevant file found, use `workspace_read` to get the full content. Present the key information clearly, citing which file it came from and when it was last updated.

## Output Format

Present results with clear attribution:

```
Found in decisions/database-selection.md (v2, updated 3d ago):

  Decision: PostgreSQL over MySQL
  Status: approved
  Reasoning: Better JSON support, superior FTS, row-level security
```

If multiple files match, show a summary list first, then offer to read specific ones in detail.

## Tips

- Start with the broadest reasonable search, then narrow down
- If nothing is found, tell the user — don't make up information
- Mention the file path so the user can reference or update it later
- If the workspace is empty, suggest using `/save` to start building knowledge
- For time-based queries ("what did we do last week"), use `workspace_search` with date filters or check `activity/` logs
