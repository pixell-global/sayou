# Contributing to sayou

Thank you for your interest in contributing to sayou.

## Branching & Pull Requests

Read [docs/BRANCHING_STRATEGY.md](./docs/BRANCHING_STRATEGY.md) for the full branching strategy.

**Quick version:** Branch from `main`, open a PR, get it reviewed, squash-merge. Never push directly to `main`.

```bash
git checkout -b feat/my-feature
# make changes, commit, push
gh pr create --title "Add my feature"
```

## Reporting Issues

Open an issue on GitHub with:
- A clear description of the problem or suggestion
- Steps to reproduce (for bugs)
- Expected vs actual behavior

## Code Style

- Python 3.11+
- Type hints on all public interfaces
- Tests for all new functionality
- Docstrings on public modules and classes

## RFC Process

Significant changes to sayou's architecture or core principles go through an RFC (Request for Comments) process. RFCs are Markdown files in `docs/rfcs/` that describe the problem, proposed solution, alternatives considered, and migration path.

Details on the RFC process will be documented as the project matures.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
