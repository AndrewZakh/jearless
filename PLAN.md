# Implementation plan

Date: 2026-11-06; actualized 2026-11-19 (tooling/39) and 2026-11-25 (tooling/55). The four-phase build plan
became history in three days (v0.1.0 → the first release v0.9.4); this file now maps
the technical decisions and the shipped CLI surface. Development runs on jearless
itself — sprints live in `.jearless/plans/`, the tool builds itself (see the tag
history). The design lives in README.md (the project constitution — argued and
proven). The name is settled: **jearless**. Package `jearless`, console command
`jear` (alias `jearless`), config `.jearless.toml`. Slogan: "Fearless. Jearless.
Bare git is enough — for small teams."

## Technical decisions (and why)

- **Python 3.11+, installed via pipx.** One dependency — ruamel.yaml. Everything else is stdlib.
- **Git via subprocess.** Zero dependencies and full flag transparency. GitPython drags in gitdb and hides parameters — and our tool is precisely about the exact semantics of git; hiding it is out of the question.
- **Versioning via auto-version-hook** (pre-commit, pinned `v1.1.0`, config `.version-hook.yml`): the version bump rides the feature branch, main is protected, merge commits are untouched (`skip_merges`) — the "main moves only by merges" invariant holds. The flow version lives in `env.yml`; the package version in pyproject mirrors it automatically (`version_files`, hook v1.1.0).
- **CLI on argparse.** The tool preaches minimalism — let the framework count be zero.
- **ruamel.yaml (rt mode) — the only YAML parser.** Edits preserve comments (closes the round-trip risk from the README); reads use it too — the files are kilobytes, and the 2026-11-06 measurement showed performance is a non-issue at any scale.
- **Tests are repository factories in temporary directories** (the pattern of our /tmp demos) plus golden files for the generator. No git mocks — only real repositories with real merges.
- **The config is `.jearless.toml`:** the branch regex, the changelog line template, the prefix-to-section mapping, GitFlow mode — an optional intermediate branch of any name, such as `dev` or `release-1`, set with `[git] integration_ref` (`{n}` resolves to the newest sprint whose branch exists — task tooling/66; one branch at a time) and a configurable `[git] trunk_ref`.
- **Artifacts live under `.jearless/`** (task tooling/15): the registry, archives, plans, reports; the public face stays at the root (README, CHANGELOG.md). Resolution order `.jearless/` → root → birth in `.jearless/`; both existing = refuse — two live registries are the drift disease.
- **Planning follows the README manifest** (tooling 15–19): the plan file is the only authored artifact about the future; priority, blocked_by and parent are deliberate refusals with recorded reasons; kind is declared at take, membership is derived from the plan.
- **The MR dashboard is a forge comment, not a tree file** (task tooling/14, shipped as `sprint-comment.yml`): a `pull_request` Action installs the PR's own jearless, renders the current sprint's gantt, burn-down and board, and maintains one sticky comment per PR (tooling/50). A GitLab analog ships in `examples/`. No ref moves — the charter invariant is untouched.

## The CLI surface (all shipped unless noted)

| Command | Mechanics |
|---|---|
| `add <project> "summary" [--points N] [--depends ...] [--yes]` | append a task to the registry (comments survive); next id = max over registry ∧ archives ∧ branches; the duplicate guard warns on keyword overlap and asks `y/N` (non-TTY declines, `--yes` skips) |
| `take <project> <id> [--type fix\|chore\|feature]` | registry → slug; check origin (ls-remote — the truth, not the cache); branch `<type>/<project>/<id>-<slug>` (default feature — the declared kind); push. The server arbitrates the race |
| `retake <project> <id> --type fix` | reopen a done task: the fork is derived by SHA (an ancestor check against the done-merge), never by clocks — same-second traps are impossible |
| `find <query>` | case-insensitive substring search across summaries/descriptions; rejected tasks carry the `[rejected: …]` marker |
| `sprint [--write [PATH]] [--rag <plan>]` | fetch --prune; the join registry × origin branches × merge log; states available / in_progress / done / rejected. Bare = pure print. `--write` refreshes a markdown dashboard (create-with-markers / replace-chunk / refuse a human file; a generated-at · git@sha stamp makes staleness visible) |
| `board [--all] [--limit N]` | mermaid kanban over the canonical states; plan-first: the planned cards in the plan's own order, unplanned in-progress work still shows (hiding it would be a lie) |
| `log <project> <id>` | the per-task journal: every branch of the task, own commits, merge dates — the retake story in one screen |
| `reject <project> <id> <cause>` | withdraw a task with a mandatory cause ("a bare rejection is invisible debt"); REJECTED is the fourth derived state and wins over everything; revival = remove the field, git remembers |
| `changelog --from <tag> --to <tag>` | merge commits → the config regex → sections by prefix; the summary from the registry (union with archives); the dry-run mindset — printed, never stored (storing is the release step) |
| `doctor [--acknowledge <sha> "cause"]` | unattributed commits on main (the first-parent audit), branch-naming violations, an invalid registry; the scar ledger `.jearless/doctor_ignore` keeps acknowledged holes visible; exit code counts live findings only — gate-able. `--acknowledge <sha> "cause"` appends an accepted scar to the ledger |
| `timeline --live \| --snapshot <tag>` | a mermaid gantt of the facts; live is never committed; the snapshot is a release artifact |
| `retro <plan.yml>` | join the authored sprint contract with first-arrival merges: dated windows report the drift, undated join by membership; merged-but-unplanned work is the visible hole |
| `plan <file> [--gantt]` | validate the authored sprint contract (`.jearless/plans/`): ids vs the union, duplicates, dates; the file's git birth is the sprint start; the order of ids is the sprint priority |
| `burndown [plan] [--trend]` | sprint burn-down (stepped ideal at planned ends vs first-arrival actual, window = plan birth → last planned end, extended honestly) and the cross-sprint velocity trend |
| `archive <tag>` | move done-as-of-tag tasks into `archive_<tag>.yml` (the cut is by the release tag, done tasks only); identity is the union (load_all); human-run — the tool writes both files, the human commits; an archive file is frozen |
| `report <tag>` | the release-time PM snapshot into `.jearless/reports/`: velocity, cycle time (median + p85, client-clock disclaimer), fix share, return rate, backlog growth, attribution, Points-in-time (lead time by size), review latency (forge server clocks), authorship (lines by author) |
| `release [--tag TAG] [--finalize TAG]` | two phases, nothing writes main: PREPARE commits the artifacts (changelog, snapshot, report) on release/<tag> and opens the PR; FINALIZE lands the annotated tag on the merge commit after the PR merges (task tooling/51); ends with the publish reminder |
| `graph` | mermaid flowchart of the registry's `depends_on` links; refuses unknown targets and cycles, doctor reports them as findings |
| `rhythm [author]` | when landed work happens: commits by local hour, weekday, ISO week and month, read from the offsets stored in the commits; per-author mode is opt-in assignment hints — never workload evidence |
| `prune` | deletes local branches fully merged into origin/main; unmerged branches are refused |
| `message <project>/<id>` | the squash-box message carrying the `Task:` trailer, for adopters whose forges mandate squash |

## The phases — all shipped

- **Phase 0. Skeleton** — shipped 2026-11-06: empty states never crash.
- **Phase 1. The core loop** — shipped 2026-11-06: the race test (two takes, one remote) passes; deleting a branch returns the task to available.
- **Phase 2. The journal** — shipped 2026-11-06: both merge message forms, the first-parent audit, doctor catches unattributed commits.
- **Phase 3. Time** — shipped 2026-11-06: live/snapshot timeline, the retro join.
- **Phase 4 (on trigger)** — archive shipped with release v0.9.4; the ergonomics trigger for mass archival never fired (the benchmark: a one-minute query needs millions of tasks).

Since then the development is sprint-based and dogfooded: the tool tracks,
dashboards, burns down, retros and releases itself. The scars are on the
ledger (`.jearless/doctor_ignore`) — direct-to-main slips are acknowledged
aloud, never hidden.

## What is deliberately absent (and that is a feature)

Statuses and assignees (derived, not stored), CI integrations beyond the
test gate and the PR dashboard, a web UI, daemons, hooks, notifications. The
moment those are needed — time to leave for Issues / git-bug / Backlog.md,
not to build them in here.

## Open implementation questions

- `take` for a task missing from the registry: **settled** — it refuses; ad-hoc work gets a registry entry or a non-taxonomy branch (shown aloud as the visible hole).
- Detecting a fast-forward retroactively is impossible (it leaves no trace) — doctor catches only unattributed commits. Standing rule: the scars go on the ledger, the shishki stay visible.
- Branch protection: **settled** — main accepts changes only through pull requests (tooling/54); recipes in `examples/branch-protection.md`.
- xcf→Git-LFS: **rejected** (tooling/45) — the hand-authored svg is the canonical logo source.
- Trailer attribution for squash-mandated forges (tooling/64): recorded, not started.
