# jearless

<p align="center">
  <img src="assets/img/logo.svg" alt="jearless — the hedgehog whose spines are a gear" width="150">
</p>

**Fearless. Jearless.** Task tracking and a changelog on bare git — for small teams.

*Why the name: by ear — a faint echo of Jira; by sight — fearless; spelled with an error — and we track errors for a living; a jearless sprint — a fast run without fat. The mascot: a hedgehog whose spines are a gear.*

A git-native task tracker: the registry is a versioned YAML, the state is derived from branches and merge commits, the changelog, reports and charts are generated at release time. No tracker service, no database, no daemons — one dependency (ruamel.yaml), one binary, your own repository as the single source of truth.

## Install

```sh
pipx install jearless        # the intended way for daily use
```

POSIX systems only (Linux, macOS — WSL counts as Linux); native Windows is untested.

For development: `uv venv && uv pip install -e ".[dev]"` (or the pip equivalent), then `pre-commit install`.

## Quickstart

Inside your git repository:

```sh
jear add door "paint it black" --points 2   # a task in the eternal registry
jear take door 1                            # branch feature/door/1-paint-it-black, pushed — the push IS the claim
# ... work, then a true merge (--no-ff) ...
jear sprint                                 # available / in_progress / done — derived from git
jear doctor                                 # the audit: unattributed commits, naming, registry health
```

No statuses are ever stored. Three sources — the registry, the branches, the merge history — are joined on demand.

## What it draws (real output)

The actual timeline of a sprint — start = the branch's first commit, end = the merge:

```mermaid
gantt
    title jearless — live
    dateFormat YYYY-MM-DDTHH:mm:ss
    axisFormat %d.%m %H:%M
    section tooling
    take — claim a task with a single push :tooling_2, 2026-11-06T20:14:45, 2026-11-06T20:14:51
    sprint — a join of three sources :tooling_3, 2026-11-06T20:18:06, 2026-11-06T20:18:12
```

The sprint board (mermaid kanban), the burn-down and the velocity trend (`xychart-beta`), the changelog and a PM report per release — all derived, all portable text.

## How it works

| State | Derived from |
|---|---|
| available | in `tasks.yml`, no branch on origin, no merge commit |
| in_progress | a branch exists on origin |
| done | a merge commit naming the task, in main |

- **The eternal registry** (`.jearless/tasks.yml`): frozen facts only — id, summary, description, story_points, `depends_on`. Tasks are never deleted. No status fields: git knows the state.
- **Taking a task = pushing a branch**: `jear take door 1` checks occupancy via the remote first (advisory — `ls-remote`), and the push arbitrates the race for identical branch names — though git may answer `Everything up-to-date` when the branch already carries that exact commit. Exclusive ownership is not required: two engineers on one task are both visible on the board.
- **Two engineers, one task — the Vasya and Masha model**: the first merge is the `done` signal. If the contract check finds gaps, Vasya re-takes the task (`jear take --type fix`) and the board shows the rework; the full story lives in `jear log`. Whether front-end and database work deserve separate tasks is the team's own call — the same ID means the same task.
- **The changelog, reports and charts are generated at release time** from merge commits between tags. Nothing is stored — everything is a join. The report carries velocity, cycle time (client-clock disclaimer), fix share, return rate (same-ID re-merges), backlog growth and attribution — the name is the task branch's most frequent committer, enough to find the first person to talk to.
- **The changelog, reports and charts are generated at release time** from merge commits between tags. Nothing is stored — everything is a join.
- **`jear doctor`** audits main: unattributed commits (squash/fast-forward scars) are loud; acknowledged scars live in the `.jearless/doctor_ignore` ledger, counted aloud.

Ad-hoc questions (total effort, per-project sums, dependencies) answer by one-liners — the query cookbook: [COOKBOOK.md](COOKBOOK.md).

The philosophy behind it — EngineerOps, the engineer-first artifact model — lives in [ENGINEEROPS.md](ENGINEEROPS.md) (Concept 0.1).

The planning rules — why there is no priority field, why kind is declared while membership is derived, why hours are honestly unanswered — live in [manifest.md](manifest.md). The mechanics of contributing: [CONTRIBUTING.md](CONTRIBUTING.md). The implementation plan and its reasoning: [PLAN.md](PLAN.md).

## Release checklist

Human-run; `jear release` prints the authored checklist (`.jearless/release.md`) every time: build, publish (TestPyPI rehearsal on metadata change), verify via the JSON API, refresh the dashboard.

## The fine print

- **Scale**: hundreds of merges a day ≈ tens of seconds per report (git subprocess fan-out) — built for small teams, honestly.
- **Deprecation horizon**: the legacy root registry fallback dies in 1.0; `.jearless/` is the only home after that.
- **A released-but-unpublished version drifts** — which is why every release ends with its checklist.

## The idea, compressed

Automation of tasks and a changelog on bare git. The design debates — why the registry is eternal, why the state is derived, why the first arrival wins — and the decisions they produced are the project's core; they live in the README's history and [manifest.md](manifest.md).

**Status**: the design has stabilized through dogfooding — the tool has tracked, released and audited its own development since its first day.
