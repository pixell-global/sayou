# Branching Strategy

sayou follows a trunk-based development model with short-lived feature branches and tagged releases.

## Branches

| Branch | Purpose | Protected |
|--------|---------|-----------|
| `main` | Stable release branch. Every commit on `main` is deployable. | Yes |
| `feat/<name>` | Feature work. Branched from `main`, merged via PR. | No |
| `fix/<name>` | Bug fixes. Branched from `main`, merged via PR. | No |
| `chore/<name>` | Maintenance (deps, CI, docs). Branched from `main`, merged via PR. | No |

## Workflow

### 1. Start from main

```bash
git checkout main
git pull origin main
git checkout -b feat/my-feature
```

### 2. Work on your branch

- Make small, focused commits
- Write tests for new functionality
- Keep the branch short-lived (ideally < 1 week)

### 3. Open a pull request

```bash
git push -u origin feat/my-feature
gh pr create --title "Add my feature" --body "Description of changes"
```

PR requirements:
- Descriptive title (under 70 characters)
- Summary of what changed and why
- All tests must pass
- At least one approval before merge

### 4. Merge and clean up

PRs are merged via **squash merge** to keep `main` history clean. Delete the branch after merge.

## Releases

Releases are tagged on `main` using semantic versioning:

```bash
git tag -a v0.2.0 -m "v0.2.0: Zero-config defaults, tool consolidation, CLI"
git push origin v0.2.0
```

### Version Numbering

| Version | Meaning |
|---------|---------|
| `v0.x.y` | Pre-1.0 development. Minor bumps may include breaking changes. |
| `v1.0.0` | First stable release. Semver rules apply from here. |
| `vX.Y.Z` | `X` = breaking, `Y` = features, `Z` = fixes |

### Release Checklist

1. All PRs for the release are merged to `main`
2. `pytest` passes with zero failures
3. Version in `pyproject.toml` matches the tag
4. Create annotated tag: `git tag -a vX.Y.Z -m "description"`
5. Push tag: `git push origin vX.Y.Z`
6. GitHub Actions publishes to PyPI automatically

## Branch Protection Rules (main)

- No direct pushes — all changes via PR
- Require passing CI checks
- Require at least 1 approval
- Squash merge only

## Hotfixes

For urgent production fixes:

```bash
git checkout main
git checkout -b fix/critical-bug
# fix, commit, push, PR
```

Hotfixes follow the same PR flow but are prioritized for review.

## Naming Conventions

| Prefix | Use |
|--------|-----|
| `feat/` | New features or capabilities |
| `fix/` | Bug fixes |
| `chore/` | Dependencies, CI, docs, tooling |
| `refactor/` | Code restructuring without behavior change |
| `test/` | Test additions or improvements |
