# CLAUDE.md

Instructions for Claude Code when working on the sayou repository.

## Branching Strategy

**Read [docs/BRANCHING_STRATEGY.md](./docs/BRANCHING_STRATEGY.md) before making any commits.**

Key rules:
- **NEVER push directly to `main`**. All changes go through feature branches and PRs.
- Branch naming: `feat/<name>`, `fix/<name>`, `chore/<name>`, `refactor/<name>`, `test/<name>`
- PRs are squash-merged to keep `main` history clean.
- Tag releases on `main` with annotated tags: `git tag -a vX.Y.Z -m "description"`

### Workflow

```bash
# Start work
git checkout main && git pull
git checkout -b feat/my-feature

# After changes
git push -u origin feat/my-feature
gh pr create --title "Add my feature" --body "Description"

# NEVER do this:
git push origin main
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
```

## Architecture

- `sayou/server/__init__.py` — MCP tool registration (11 tools). This is the main agent interface.
- `sayou/config.py` — Settings with env prefix `SAYOU_`. Config priority: env vars > `~/.sayou/config.yaml` > defaults.
- `sayou/catalog/database.py` — Database initialization and engine creation.
- `sayou/workspace.py` — Public Python API (`Workspace` class).
- `sayou/core/workspace.py` — Core workspace implementation.
- `sayou/cli/` — CLI commands (`init`, `status`).
- `sayou/__main__.py` — CLI entry point and MCP server startup.

## Testing

- All tests in `tests/`. Run with `pytest`.
- `test_smoke.py` verifies MCP tool registration.
- Tests requiring `SAYOU_EMBEDDING_PROVIDER` are skipped when not configured.
- All PRs must pass tests before merge.

## Release Process

1. Bump version in `pyproject.toml`
2. Merge PR to `main`
3. Tag: `git tag -a vX.Y.Z -m "description"`
4. Push tag: `git push origin vX.Y.Z`
5. CI publishes to PyPI
