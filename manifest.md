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

## The charter

- **main moves only by merge commits** — `--no-ff`, no squash, no rebase-merge. Rebase inside your own unmerged branch is harmless and free. Merge commits carrying the branch name are the only carrier of "this task shipped".
- **State is derived, never stored.** available = in the registry without a branch; in_progress = a branch on origin; done = a merge commit naming the task. Reopen is derived too: a live branch forked at-or-after the done-merge means rework is under way.
- **One carrier per fact.** The branch prefix is the declared kind; `depends_on` is the only link field; story_points are the only estimate, never incremented.
- **Nothing automatic writes to main.** Releases, archives, dashboards — human-run, the tool prints the hints.
- **Artifacts live under `.jearless/`** (plans, reports, archives, snapshots, the release checklist); files other things read by convention stay at the root (README, CHANGELOG, `.mailmap`, `.gitignore`, `.jearless.toml`). The root-registry fallback dies in 1.0.

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
