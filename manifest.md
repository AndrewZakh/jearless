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
- **Hours and money are honestly unanswered.** Commit dates are client clocks, and a system built on client clocks must not pretend to measure hours. Saying "no" here is the source of trust in every number the system does show. The precision (task tooling/56): **labor hours stay unanswered; duration is measured** — lead time and cycle time report wall-clock duration between git/forge events, with the client-clock disclaimer. Per-author rhythms may inform assignment (tooling/57 — don't drop an urgent task into a dead window); they are never workload evidence.

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
- **Artifacts live under `.jearless/`** (plans, reports, archives, the release checklist); files other things read by convention stay at the root (README, CHANGELOG, `.mailmap`, `.gitignore`, `.jearless.toml`). The root-registry fallback dies in 1.0.

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

## The merge semantics matrix (task tooling/60)

How main's landing types map to jearless — **first-class, limited, or loudly
diagnosed**. The rule behind the table: work that landed is attributed; work
that lost its name is counted as the visible hole.

| Landing type | jearless behavior |
|---|---|
| `--no-ff` merge commit (single task branch) | first-class: the branch name is the task key — bars, changelog, cycle time |
| Forge PR merge ("Merge pull request #N from …/branch") | first-class: the PR form parses to the same branch key |
| Same-branch re-merge | an artifact: first-arrival wins; re-merges are counted as returns in the report |
| Retake (a new branch for a done task) | a new bar (`_fix`/`_chore` suffix) — rework is visible on the chart |
| Octopus merge (2+ branches in one merge) | limited: attributed as a merge (doctor is silent), but no per-task bars and the changelog counts it as skipped — the visible hole. Prefer sequential merges |
| Cherry-pick onto main | loud: a non-merge commit — doctor flags it unattributed (ledger or PR, not silence) |
| Squash merge | attributed when the commit declares its task — a `Task:` trailer (`jear message`) makes it a changelog entry and doctor-silent (tooling/64); without a trailer it stays loud: the branch name dies and the task key is lost |
| Fast-forward | loud: no merge commit at all — doctor flags it |
| Direct push (non-merge, non-sanctioned files) | loud: doctor flags it; under the PR-only constitution it's also platform-blocked |

Every loud row lands in the ledger with a cause when accepted — the same
"visibility, not prohibition" rule as everywhere else.

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
| In GitFlow mode a retake made before promotion went unnoticed — the reopen was measured against the trunk, where the merge did not exist yet (tooling/61) | the fork point is measured against every ref the merges are read from |
| The registration ride's merge was invisible to the join — tooling/65 sat available for days while its work shipped, and the changelog skipped it (registry/<project>-<num> does not parse) | ride branches take the parseable registry/<project>/<num> form; the allocator protects the ids the ride branches claim (tooling/69) |
| The merge subject is editable in the forge UI and forgeable by hand; a squashed delivery loses the branch name entirely — the adopters' squash-mandated orgs had no attribution at all | attribution reads the full body: a `Task: <project>/<id>` trailer in the message's last paragraph wins; the subject regexes stay the legacy fallback for real merges; a plain commit's subject is never trusted (tooling/64) |
| PyPI drifted because publishing lived in someone's head | the release prints its checklist; the checklist is a file, not a habit |
| Auto-committed reports resurrect the post-merge writer — a committed live report lies between runs, and a CI commit-back breaks "nothing automatic writes main" | dashboards ride the forge (PR/MR comments), pages or job artifacts; the tree holds only the release-time frozen slice (tooling/14, reaffirmed 2026-11-20) |
| Direct pushes to a protected branch are the industry's antipattern — "таких проектов просто нет"; five of five of our scars were direct-to-main sins | main accepts changes only through PRs/MRs; the release rides one too; the emergency bypass is explicit and every use is a ledger scar (tooling/54) |
| A binary drawing source drifted from the vector truth | the canonical logo source is the hand-authored svg; the xcf stays untracked (rejected: tooling/45) |

## GitFlow mode

For teams that accumulate unreleased work on an intermediate branch before
it reaches main — `dev`, `release-1`, `sprint-27`, whatever the team calls
it — instead of promoting task by task. Name that branch in `.jearless.toml`:

```toml
[git]
integration_ref = "dev"
```

The name is yours: letters, digits, `-`, `_`, `.`, `/` and the `{n}` template.
The trunk is configurable the same way (`trunk_ref`).

**One integration surface; the `{n}` family may span several branches.**
`integration_ref` names one surface; work flowing through `dev` and then a
separate `release-1` is not tracked as two hops — point it at the one the
team treats as "integrated". But a `{n}` pattern defines a *family*: every
branch matching it that has not been promoted yet is an integration branch
at once (task tooling/67). With `sprint-{n}`, `sprint-27` and `sprint-28`
may both carry unreleased work; the tool sees both.

In this mode done = "merged into main OR any unpromoted integration branch"
(the union kills the pre-promotion available-flicker), and every live view —
the board, the sprint, the burndown, the changelog's unreleased section,
take's fork base — reads the trunk together with every unpromoted family
branch. Released (tag-based) views keep reading main: the promotion delivers
the accumulated batch, and the changelog range catches it naturally via
reachability. Promotions must be true merges. A squash promotion loses the
task names, and `jear doctor` reports it. Our own repository stays
trunk-based; the mode is for adopters.

### A GitFlow example: a branch per sprint (task tooling/61, tooling/66)

A team gives every sprint its own integration branch — `sprint-27`,
`sprint-28`, and so on — and promotes it to `main` when the sprint is
delivered. One setting in `.jearless.toml`, committed to the repository:

```toml
[git]
integration_ref = "sprint-{n}"
```

`{n}` stands for a sprint number. A fixed name such as `dev` needs no
template and works the same way; the rest of this cycle applies to it
unchanged.

The resolution is branch-driven (task tooling/67): the family is every
branch on the remote matching the pattern — the `{n}` slot takes digits —
that has not been promoted yet (its tip is not an ancestor of the trunk).
Plans do not participate: a sprint plan committed before its branch stays
harmless, and a branch created before its plan is seen the same way. Each
candidate costs one `merge-base --is-ancestor` against the trunk — the
family is small by construction.

The cycle of one sprint:

1. **Open the sprint.** Commit `.jearless/plans/sprint_27.yml` and create the
   branch `sprint-27` from `main`.
2. **Take a task.** `jear take shop 1` creates `feature/shop/1-add-the-cart-page`
   forked from the tip of `sprint-27`, and pushes it.
3. **Open the pull request against `sprint-27`**, not `main`, and have it
   merged with a merge commit.
4. **The task is done.** `jear sprint` shows `shop/1` under `done`, although
   `main` has no task merge yet — done means integrated, and it reached
   `sprint-27`.
5. **Take the next task.** `jear take shop 2` forks from the new tip of
   `sprint-27`, so it builds on the cart page.
6. **See what the sprint still owes to `main`.** `jear changelog --from
   origin/main --to origin/sprint-27` lists the tasks not yet promoted:
   `- shop-1: add the cart page`.
7. **Deliver.** Merge `sprint-27` into `main` with a true merge commit.
   Nothing changes on the board: the tasks were already done.

**A plan committed before its branch.** A sprint plan may be committed
before anyone has created that sprint's branch. The resolution reads
branches, not plans, so the plan alone changes nothing: the tool stays on
`sprint-27`, tasks integrated there remain done, and `jear take` forks from
`sprint-27` and works. *(Until tooling/66 the tool read the plan number
alone. `jear take` then refused with `no origin/sprint-28`, and every task
on `sprint-27` not yet promoted fell back from `done` to `available`.)*

Every step above was run against exactly this configuration in a throwaway
repository; the output quoted is what the tool printed.

### Several unpromoted sprints at once (task tooling/67)

`{n}` is a family, not a pointer. When `sprint-28` is created while
`sprint-27` is still not in `main`, both stay in view — the semantics:

- **done** = merged into main OR any unpromoted family branch. A task
  integrated on `sprint-27` stays done after `sprint-28` appears.
- **The fork base** = the newest unpromoted family branch's tip; when every
  family branch is promoted, the trunk. New work builds on the newest sprint.
- **The unreleased changelog** = the union: main together with every
  unpromoted family branch, first arrival wins across the union — a task
  merged to `sprint-27` lists once, even after a re-merge to `sprint-28`.
  The header date reads the trunk tip (the release anchor). The per-branch
  debt stays one recipe away: `jear changelog --from origin/main --to
  origin/sprint-27`.
- **Reopen** = a live branch naming a done task carries undelivered work.
  Stale is the exception, decided by SHA, never clocks: the branch was the
  merge's own source — its tip is an ancestor of some done merge's second
  parent. A retake forked from the newest sprint qualifies even though its
  history does not contain the done merge resting on the unpromoted
  sibling — the fork-point rule that served until tooling/67 cannot see
  that case. The rule also makes honest what the fork-point rule hid: a
  branch that continued past its merge, and a second engineer's parallel
  branch after the first merge, both read as rework in progress.

### Where GitFlow mode holds (task tooling/61)

Each line was run by hand in a throwaway repository and is pinned by a test
in `tests/test_gitflow.py`.

- **Done means integrated.** A task merged into any unpromoted family branch
  is done even while main still lacks it. After a partial promotion — one
  task promoted, another not — both read as done; the changelog from main to
  the integration tip lists exactly what the next promotion delivers.
- **Re-integration is harmless.** Merging the same branch name into the
  integration branch a second time leaves the task done: the first arrival
  already shipped it.
- **A retake reopens the task.** A fix branch forked from the integration
  tip — past the task's own merge — puts the task back in progress, whether
  or not the task has been promoted yet. (Until tooling/61 the reopen was
  measured against the trunk alone, so a retake made before promotion went
  unnoticed and the task stayed done. Until tooling/67 the fork-point rule
  could not see a retake forked from the newest sprint when the done merge
  rested on an unpromoted sibling.)
- **A branch that was the merge's source is not a retake.** Its tip is an
  ancestor of the done merge's second parent — the pre-merge leftover, stale
  by SHA, no clocks involved (tooling/67). Any other live branch naming a
  done task carries undelivered work.
- **Divergence is fine.** The integration branch ahead of main, main ahead of
  it, task branches deleted — the states do not depend on the two agreeing.

Not covered, and not promised: promotions that are not true merges, several
integration *surfaces* (work flowing through `dev` and then a separate
`release-1` is one hop too many), and more than one `{n}` family — the
config names one pattern. The branch's own name is not a limit —
`tests/test_gitflow.py` runs the same scenario under `dev`, `release-1`,
`sprint-27`, `release/2.x` and `sprint-{n}`.
