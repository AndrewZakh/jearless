# Contributing to jearless

The project eats its own food: tasks are tracked with jearless itself, in
this repository. Read [manifest.md](manifest.md) first — the charter and the
planning rules live there; this file is the mechanics.

## Setup

```sh
uv venv && uv pip install -e ".[dev]"     # or: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install              # the version bump hook
.venv/bin/pytest -q                       # the suite (integration-heavy: real repos, ~35s)
.venv/bin/ruff check src tests
```

POSIX only (Linux, macOS — WSL counts as Linux); native Windows is untested.

## The ritual

1. `jear board` — see the working set. `jear add tooling "your task"` — it
   lands in `.jearless/tasks.yml` (the duplicate guard may ask for a
   confirmation; `--yes` skips).
2. `jear take tooling <id> [--type fix|chore]` — creates the branch and pushes
   it. **The push is the claim**: the server arbitrates races.
3. Work, commit on the branch. The pre-commit hook bumps the version — it
   rides the branch, main is untouched.
4. Merge with `--no-ff` (no squash, no rebase merges) and push. Delete the
   merged branch. `jear sprint` — the board recomputes from git; `jear doctor`
   — the audit.
5. Releases are human-run: `jear release` (it prints the checklist), then
   `uv build && uv publish`.

## The rules that matter most

- main moves only by `--no-ff` merge commits; nothing automatic writes to it.
- State is derived, never stored. If you are about to add a `status:` field —
  read [manifest.md](manifest.md) first.
- The test suite builds real git repositories in temp dirs; no mocks. Pin
  commit dates via `GIT_COMMITTER_DATE` when a test cares about time.
