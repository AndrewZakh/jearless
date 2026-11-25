# Contributing to jearless

The project eats its own food: tasks are tracked with jearless itself, in
this repository. Read [manifest.md](manifest.md) first — the charter and the
planning rules live there; this file is the mechanics. Branch protection
recipes for GitHub and GitLab are in
[examples/branch-protection.md](examples/branch-protection.md).

## Setup

```sh
uv venv && uv pip install -e ".[dev]"     # or: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install              # the version bump and the registry checks
.venv/bin/pytest -q                       # the suite (integration-heavy: real repos, ~65s)
.venv/bin/ruff check src tests
```

POSIX only (Linux, macOS — WSL counts as Linux); native Windows is untested.

## The ritual

Nothing lands on main directly: every change arrives as a pull request, and
the merge button belongs to the reviewer. An issue starts from a template —
a bug report, an idea or a question — chosen when it is opened.

1. `jear board` — see the working set. `jear add tooling "your task"` — the
   task is written to `.jearless/tasks.yml` and carried to a `registry/…`
   branch as a pull request (the duplicate guard may ask for a confirmation;
   `--yes` skips).
2. `jear take tooling <id> [--type fix|chore]` — creates the branch and pushes
   it. **The push is the claim**: the server arbitrates races.
3. Work, commit on the branch. The pre-commit hook bumps the version — it
   rides the branch, main is untouched. Run `pytest -q` and
   `ruff check src tests` before every commit.
4. Open the pull request and stop. The description starts from a template:
   the task, what changes and why, how it was checked, and which documents
   were touched. Every PR gets a sticky comment with the sprint gantt, the
   burn-down and the board. Merge commits only — squash and rebase merges
   are disabled.
5. `jear sprint` — the board recomputes from git; `jear doctor` — the audit;
   `jear prune` — removes the local copies of merged branches.
6. Releases are two-phase: `jear release` prepares a `release/<tag>` branch
   and its PR; after the merge, `jear release --finalize <tag>` lands the tag.
   Then the printed checklist: `uv build && uv publish`.

## The rules that matter most

- main moves only by `--no-ff` merge commits, and only through pull requests;
  nothing automatic writes to it.
- State is derived, never stored. If you are about to add a `status:` field —
  read [manifest.md](manifest.md) first.
- The test suite builds real git repositories in temp dirs; no mocks. Pin
  commit dates via `GIT_COMMITTER_DATE` when a test cares about time.
