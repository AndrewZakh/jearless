# The jearless manifest

How work is planned, measured and — deliberately — not measured. Every refusal
below is a feature: each one removes a place where two sources of truth could
drift apart.

## The planning manifest

- **The plan is the only authored artifact about the future.** `plan/sprint_N.yml` is committed at sprint start; the file's git birth **is** the sprint start — nothing stores a date. Its membership is the commitment; the order of ids is the sprint priority. The gantt-of-the-plan is derived from this file, never hand-drawn: one authored plan, no drift between plan artifacts.
- **Priority is deliberately absent — and that is a feature.** The plan's membership and order already answer "what matters now". A global priority field in the registry has no consumer today — no report, no view, no gate reads it — and an unread field rots. Adding it later is free: the registry is additive, the loader validates, nothing migrates. The field waits for its trigger: the team catching itself re-reading the whole backlog during planning to pick the next sprint. Until that pain exists, a decision made in a conversation beats a rotting column.
- **One carrier per fact.** `blocked_by` was rejected as a duplicate of `depends_on` — the same relation must not live in two places. The red RAG state reads the existing graph.
- **The rework rate is free; attribution is deferred.** The share of fix merges comes from the branch prefixes and counts ad-hoc fixes that a parent field would never see. `parent` buys only per-feature attribution ("which feature is falling apart") — deferred to the same trigger tier as priority.
- **Kind is declared, membership is derived.** The branch prefix is the human's declaration at take time (`--type`); unplanned-ness is derived from the plan's birth versus the task's creation. The auto-hotfix hypothesis (unplanned tasks automatically become `hotfix/`) was rejected: membership and kind are orthogonal axes, and the inference bakes a time-of-take judgment into an immutable branch name — erasing the difference between "production is on fire" and "calmly added scope", which is exactly what a report must keep separate.
- **Humans bring chaos — and chaos is data, not a violation.** An unplanned task is shown by the retro, counted by the report, absorbed by the registry. The plan may be amended by a human commit; discipline lies in visibility, not in prohibition. A "urgent, add the logo now" task is the most life-like task there is — the system's job is to record it honestly, not to gate it.
- **The report answers facts, not reasons.** A displaced task shows as "not merged"; why it was displaced is the retrospective's human job. Git knows facts; people know reasons.
- **Hours and money are honestly unanswered.** Commit dates are client clocks, and a system built on client clocks must not pretend to measure hours. Saying "no" here is the source of trust in every number the system does show.

## The pilot criterion

The number that decides whether the idea works: **how many times did an
engineer interrupt their work for a status that git and the sprint plan
could already assemble?** The goal is zero manual status updates and zero
status questions wherever the join suffices. A hand-written report costs
more than the time it takes to write: two context switches break the
thought, and a connection the engineer almost caught before the pause is
sometimes gone for good. A pilot on a team with different habits will show
how much routine the tool really lifts. (Review, 2026-11-19.)

## The charter

- **main moves only by merge commits** — `--no-ff`, no squash, no rebase-merge. Rebase inside your own unmerged branch is harmless and free. Merge commits carrying the branch name are the only carrier of "this task shipped".
- **State is derived, never stored.** available = in the registry without a branch; in_progress = a branch on origin; done = a merge commit naming the task. Reopen is derived too: a live branch forked at-or-after the done-merge means rework is under way.
- **One carrier per fact.** The branch prefix is the declared kind; `depends_on` is the only link field; story_points are the only estimate, never incremented.
- **Nothing automatic writes to main.** Releases, archives, dashboards — human-run, the tool prints the hints.
- **Artifacts live under `.jearless/`** (plans, reports, archives, snapshots, the release checklist); files other things read by convention stay at the root (README, CHANGELOG, `.mailmap`, `.gitignore`, `.jearless.toml`). The root-registry fallback dies in 1.0.

## Boundary cases

Both classic sprint-boundary scenarios fall out of the design with zero
special cases — because states are sprint-blind: sprints are plans (authored),
the state belongs to git, and the retro is where the two calendars meet and
tell the truth about both. Verified live (2026-11-17).

- **Pull-forward.** An early finisher takes a task from the next sprint's
  scope: `take` works — tasks are sprint-blind. The current sprint's retro
  lists it as actual-only ("the work nobody planned") — that is the
  planning-buffer data; the next sprint's retro joins it as planned and on
  time. The velocity trend counts the points once, for the sprint whose plan
  owns the task. Gap to know: an unplanned pulled task is invisible on the
  sprint board until the plan includes it — `board --all` and the retro cover
  the gap.
- **Carry-over.** A task that slips to the next sprint: the old sprint's retro
  shows the miss loudly (`end +Nd`) and never counts the points — the
  burn-down stays above the ideal at the window's end; the new sprint's retro
  counts the completion — no double-count, the mirror of the points-increment
  rejection. The old plan is NOT amended retroactively: the missed commitment
  stays visible; the retro explains why.
- **No retroactive credit.** Opening a sprint after some of its tasks already
  merged cannot claim that work: the plan-birth filter excludes pre-plan
  merges from the burn-down and the retro. You may record the tasks and track
  what is still open — the system refuses to issue credit for the past, the
  same way it refuses to increment points. A late plan shows as late; the
  retro explains why.
- **The window closes.** Sprint N lives from its plan's birth to the next
  plan's birth (the latest lives to now): a recomputed old retro never picks
  up the next sprint's unplanned work, and numbering is not trusted — the
  boundary is birth order, not the N. The retro prints its plan revision and
  the history slice, so a recount is reproducible. (Task tooling/42.)

## The decision history (cause → rule)

| Cause | Rule |
|---|---|
| Squash and rebase merges silently lose the branch name — the changelog line vanishes | main moves only by `--no-ff` merges |
| A stored status drifts from reality the moment nobody updates it | zero stored statuses — the join derives all three |
| The first-arrival rule kept colliding with same-second date comparisons | reopen compares SHAs (`is_ancestor`), never clocks |
| A stale post-merge branch shadowed the fix branch forever (`setdefault` kept the first) | the join collects ALL live branches per key and picks the reopen candidate |
| A global priority field had no reader and rotted | deferred with a trigger: the planning-scan pain |
| The auto-hotfix inference baked a time-of-take judgment into an immutable name | kind is declared at take (`--type`); unplanned-ness is derived |
| Story points incremented post-hoc double-count in velocity and rewrite the past | points are frozen estimates; rework cost is derived (cycle time + rework rate) |
| An unread config key rots like an unread field | config sections are born with the feature that needs them |
| PyPI drifted because publishing lived in someone's head | the release prints its checklist; the checklist is a file, not a habit |

## GitFlow mode

For forges that accumulate unreleased work on an integration branch (staging)
instead of promoting per task: `[git] integration_ref = "staging"` in
`.jearless.toml`. Then done = "merged into main OR the integration tip"
(the union kills the pre-promotion available-flicker), and every live view —
the board, the sprint, the burndown, the changelog's unreleased section,
take's fork base — reads the integration tip. Released (tag-based) views keep
reading main: the promotion delivers the accumulated batch, and the changelog
range catches it naturally via reachability. Promotions must be true merges —
a squash promotion loses the task names and `jear doctor`'s ledger will hear
about it. Our own repository stays trunk-based; the mode is for adopters.
