# jearless

**Fearless. Jearless.** Task tracking and a changelog on bare git — for small teams.

*Why the name: by ear — a faint echo of Jira; by sight — fearless; spelled with an error — and we track errors for a living; a jearless sprint — a fast run without fat.*

**Status:** the design has stabilized; the mechanism is built around the eternal registry; the name is settled — jearless (2026-11-06). This file records the decisions and their rationale — it is not a specification. The implementation plan lives in [PLAN.md](PLAN.md).

## The idea

Task tracking and a changelog on bare git. No trackers, no infrastructure.

1. `tasks.yml` — the **eternal task registry**: subproject, id, summary, description, story_points. Tasks are added and never deleted; the file only grows. No live-state fields.
2. `jear take door_design 16` — zero commits, zero YAML edits: verify the branch is absent on origin, create `feature/door_design/16-slug`, push. **Taking a task = pushing the branch.**
3. Merging is a true merge (`--no-ff`): the branch name lands in history through the merge commit. No squash, no rebase merges.
4. The changelog is not stored — it is generated at release time: merge commits between tags → the regex from the config → the line template. The line is the summary from the registry or the slug from the branch name.
5. The branch prefix (`feature/`, `fix/`, `chore/`) → the changelog section.

## The state model: three sources, zero stored statuses

| State | Condition |
|---|---|
| available | present in tasks.yml ∧ no branch on origin ∧ no merge commit |
| in_progress | a branch exists on origin ∧ no merge commit |
| done | a merge commit carrying the branch name exists in main (overrides an existing branch when the forge's auto-delete is off) |

The sprint and all analytics are joins on the key (subproject, number), computed on demand. The race for a task is arbitrated by git itself: a second push of a branch with the same name is rejected as non-fast-forward — "taken" arrives from the server.

## Timeline and plan-versus-actual

- **The actual timeline** is a derived view: start = author date of the branch's first commit, end = committer date of the merge commit. The live variant is a command run on demand (fetch --prune, open branches end "now") and is **never committed**. The release snapshot is frozen by the tag and committed next to the changelog.
- **The Gantt (the plan)** is an authored artifact: drawn by hand or by script, committed as the team's contract. For the retrospective comparison, **bar ids = task ids** (subproject + number) — otherwise the plan cannot be joined with the facts.
- The hierarchy of truth about the start: the branch's first commit (exact, eternal) → merge-base (skewed by main's stagnation: the common commit's date ≠ the cut date) → forge events (the push time is visible, but the feed expires — on GitHub, within about 90 days). Push time does not exist in git's object model.
- Activity time metrics (hours, commit-clock deadlines) are deliberately out of scope: commit dates are client clocks, trivially spoofed, and they invite gaming.

## Key decisions

- **The number is an identifier, not a position.** No renumbering, no reuse; the uniqueness key is the pair (subproject, number). Allocating the next number looks only at the registry — it never empties and never shrinks.
- **The eternal registry instead of deletion:** the old mechanics — "the task's deletion rides the branch's first commit" — is cancelled. Consequences: the task card (story_points included) lives forever, so analytics over done tasks lose nothing; `take` never mutates the YAML, so the yq round-trip problem disappears; registry conflicts become nearly impossible — only simultaneous additions at the same spot.
- **The branch name is the only key** linking the registry, the changelog and history. Slashes are the structural separators (`feature/door_design/16-slug`); hyphens live only inside slugs.
- **YAML as the registry format:** readable by yq, analytics over frozen facts. Live-state fields (status and friends) are forbidden: git knows the state, a stored copy drifts. Scripts only read the registry (`add` appending is the sole sanctioned exception).
- **The language of the registry, slugs and changelog is English** (the GitHub norm; decided 2026-11-06). Transliteration is only a fallback inside `take`, for summaries not written in latin script — a last resort for those who skipped their lessons, not the project's style.
- **main moves by merges only — no squash, no rebase merges, always `--no-ff`.** Direct human commits (add a task, fix the plan) are allowed; the ban concerns automatic writers and merge methods. Rebasing inside one's own unmerged branch is harmless — author dates survive it.
- **Nothing automatic writes to main.** Dropping a task = deleting the branch = the task is available again (it never left the registry).
- **"A separate life for the registry" is rejected** (a submodule, a database rendered into yml, a secrets manager): moving the storage does not solve the trigger problem — who flips `done` after the merge. The principle: **state for an event that cannot be observed without infrastructure is never stored — it is derived.**
- **Taking a task is a branch push: an occupancy registry, not a notification** — others see it at their own fetch.

## Pros

- One database — git history plus the eternal registry of facts. Zero state files, zero hooks with write access, zero CI jobs pushing to main.
- Taking a task is one push, zero commits; undoing it is deleting the branch.
- The task card lives in the registry forever: velocity and any analytics over done tasks lose no data.
- The race for a task is resolved by the server, atomically, without locks or queues.
- Plan-versus-actual from two honest sources: the plan is authored and committed, the actual is derived from git, the comparison is the retrospective.
- Branch prefixes are the taxonomy: "Added / Fixed" sections come for free.
- Merge commits make a task an object of history: `--merges` between tags is the task journal; a merge commit's diff is the whole task at once.
- Version binding is free: whatever is merged between v1.2 and v1.3 lands under the v1.3 heading.
- The registry is versioned with the code, reviewed in merges, available offline.

## Cons / risks

- **Squash and rebase merges silently lose the branch name** — the changelog line disappears without an error. On the forge these are the two enemy buttons; the repo needs "Create a merge commit" as the default. The legitimate way to clean up a task's history is **squash inside the branch before the true merge** ("squash inside, merge outside"): compress the WIP into one commit preserving the first commit's author date, then `--no-ff`. Verified by a live demo, 2026-11-06: the key lives in the merge commit, the timeline start in the preserved author date.
- **Fast-forward is the default** and the sneakiest source of lost merge commits: when main has not moved, git just moves the pointer. The "always --no-ff" rule is easy to forget.
- **The regex in the config rots first** (the very first draft failed to match its own example). A generator dry-run is mandatory.
- The regex must digest both merge message forms: "Merge branch ..." and "Merge pull request #N from owner/...".
- **YAML under hand editing:** block scalars for long descriptions are the most finicky spot; on-the-fly validation is mandatory.
- **Registry growth:** the file only increases. A measurement (2026-11-06, synthetic, ~270 bytes per task): a filtered query over 1M tasks (270 MB) takes 20 s with slow ruby/libyaml and 2 s with jq; a full minute arrives at ~3–30 million tasks — outside human scales. The real archivation trigger is ergonomics (scrolling the file, bloated diffs), not query speed.
- **available is a three-way join with negation** (in the registry ∧ no branch ∧ no merge commit): easy to get wrong — hence exactly one canonical implementation.
- **The start of a bar ≠ the birth of the branch:** merge-base is skewed by main's stagnation; the forge event feed expires; git does not store push time. The only eternal starting point is the branch's first commit.
- **Local origin/* refs are a cache, not the truth:** without `fetch --prune`, ghosts of deleted branches keep tasks "taken" forever.
- Only single-line changelog entries; multi-paragraph ones are a backup path of towncrier-style fragments.
- The insurance against someone else's squash/rebase is **a task trailer in the commit message** (`Task: door_design/16`; modern gits even have `git commit --trailer`): it rides in the object itself and survives a squash if it made it into the squash message. git notes and refs/replace were rejected as metadata channels: they do not travel with a default clone/fetch and forges do not show them. When a squash has already happened, the key cannot be attached retroactively (amend would rewrite main) — which is why the generator's dry-run must highlight unattributed commits loudly: the hole must be visible, not silent.
- The applicability boundary: the moment you need labels, assignees or task discussion — move to Issues, do not build a hybrid. Jira earns its keep for large teams and corporate scale; jearless is for the small and the swift.

## Open questions

- The generator config: the regex + the line template + the prefix-to-section mapping; the dry-run format.
- How to hard-wire the fast-forward ban (an alias, a setting, a check inside `take`).
- Branches that miss the regex (quick fixes without a task) — a filter feature or a hole?
- Auto-deleting branches on the forge after a merge — the generator must not rely on the branch still existing.
- Archiving `tasks.yml`: the trigger is ergonomic discomfort, not performance. Rules for the future: cut by release tag (the same frozen moment as the changelog and the timeline snapshot), the file `archive_<tag>.yml`, move out done tasks only; available/in_progress are always computed over tasks.yml, identity for analytics is the union of the registry and the archives; it is a release-time step run by a human. The script itself is a registry task, to be taken when the trigger fires.
