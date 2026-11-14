# Implementation plan

Date: 2026-11-06. The design lives in README.md (the project constitution — argued and proven). This file is how we build it. The name is settled: **jearless**. Package `jearless`, console command `jear` (alias `jearless`), config `.jearless.toml`. Slogan: "Fearless. Jearless. Bare git is enough — for small teams."

## Technical decisions (and why)

- **Python 3.11+, installed via pipx.** One dependency — ruamel.yaml. Everything else is stdlib.
- **Git via subprocess.** Zero dependencies and full flag transparency. GitPython drags in gitdb and hides parameters — and our tool is precisely about the exact semantics of git; hiding it is out of the question.
- **Versioning via auto-version-hook** (pre-commit, pinned `v1.1.0`, config `.version-hook.yml`): the version bump rides the feature branch, main is protected, merge commits are untouched (`skip_merges`) — the "main moves only by merges" invariant holds. The flow version lives in `env.yml`; the package version in pyproject mirrors it automatically (`version_files`, hook v1.1.0).
- **CLI on argparse.** The tool preaches minimalism — let the framework count be zero.
- **ruamel.yaml (rt mode) — the only YAML parser.** Edits preserve comments (closes the round-trip risk from the README); reads use it too — the files are kilobytes, and the 2026-11-06 measurement showed performance is a non-issue at any scale.
- **Tests are repository factories in temporary directories** (the pattern of our /tmp demos) plus golden files for the generator. No git mocks — only real repositories with real merges.
- **The config is `.jearless.toml`:** the branch regex, the changelog line template, the prefix-to-section mapping.
- **The MR dashboard is a forge comment, not a tree file** (task tooling/14): a `pull_request` Action installs the PR's own jearless, renders the live timeline (mermaid renders right in GitHub comments) plus the board, and maintains one sticky comment per MR. No ref moves — the charter invariant is untouched; sprint.md stays human-run.

## The CLI surface (mapped to the README)

| Command | Mechanics | Phase |
|---|---|---|
| `add <project> "summary" [--points N] [--yes]` | append a task to the registry (comments survive); next id = max over registry ∧ archives ∧ branches; the duplicate guard warns on keyword overlap and asks `y/N` (non-TTY declines, `--yes` skips) | 1 |
| `take <project> <id>` | registry → slug; check origin (ls-remote — the truth, not the cache); branch `feature/<project>/<id>-<slug>`; push. The server arbitrates the race | 1 |
| `sprint [--write [PATH]]` | fetch --prune; the join registry × origin branches × merge log; states available / in_progress / done. Bare = pure print. `--write` refreshes a markdown dashboard (default `./sprint.md`): create-with-markers / replace-chunk / refuse a human file; a generated-at · git@sha stamp makes staleness visible; *.md-only commits are sanctioned as docs bookkeeping | 1 |
| `changelog --from <tag> --to <tag> --dry-run` | merge commits → the config regex → sections by prefix; the summary from the registry (union with archives) | 2 |
| `doctor` | unattributed commits on main (neither merges nor registry edits) — the visible hole; branch naming violations; an invalid registry | 2 |
| `timeline --live \| --snapshot <tag>` | a mermaid gantt of the facts; live is never committed; the snapshot is a release artifact | 3 |
| `retro <plan.md>` | join the plan's bar ids (the gantt contract) with the actual timeline; planning misses | 3 |
| `archive <tag>` | move done tasks into `archive_<tag>.yml` — only on the ergonomics trigger | 4 |
| `release [--tag TAG]` | tag + changelog section + timeline snapshot in one human-run move; the tag defaults to the env.yml flow version; artifacts are committed and the annotated tag lands on them | — |
| `graph` | mermaid flowchart of the registry's `depends_on` links — the plan-side dependency view (gantt cannot draw arrows); refuses unknown targets and cycles, doctor reports them as findings | — |

## Phases and Definitions of Done

- **Phase 0. Skeleton:** pyproject, the CLI frame, the config schema, the git wrapper (subprocess), lint. DoD: `--help` works; empty states (no tags, no branches, an empty registry) do not crash commands.
- **Phase 1. The core loop:** add + take + sprint. DoD: a task is taken with a single push; the sprint is assembled from three sources; the race test — two takes from two clones against one remote, the second one gets "taken"; deleting a branch returns the task to available.
- **Phase 2. The journal:** changelog + doctor. DoD: golden tests on a factory repository with both merge message forms ("Merge branch …" and "Merge pull request …"); a squash commit is highlighted by doctor; dry-run is the default mode.
- **Phase 3. Time:** timeline live/snapshot + retro. DoD: the snapshot carries the author date of the branch's first commit and the committer date of the merge; a plan with task ids joins with the facts.
- **Phase 4. Deferred (on trigger):** archive, velocity analytics over the union of the registry and the archives.

## What is deliberately absent (and that is a feature)

Statuses and assignees (derived, not stored), CI integrations, a web UI, daemons, hooks, notifications. The moment those are needed — time to leave for Issues / git-bug / Backlog.md, not to build them in here.

## Open implementation questions

- `take` for a task missing from the registry: refuse, or an `--adhoc` flag — this would also settle the "branches off the regex" question.
- Detecting a fast-forward retroactively is impossible (it leaves no trace) — doctor catches only unattributed commits.
