"""The canonical three-source join (README): available / in_progress / done.

The README risk list demands exactly one implementation of this join —
this module is it. Everything else derives from here.

REOPEN is derived too (task tooling/26): a live branch forked AFTER the
task's done-merge (merge-base date > merge committer date) means rework is
under way — in_progress wins over done. Nothing is stored; the fork date
comes from git.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from jearless import config, gitwrap, registry
from jearless.gitwrap import GitError

AVAILABLE = "available"
IN_PROGRESS = "in_progress"
DONE = "done"

# Both merge message forms (README): local merges and forge "Create a merge commit".
# The owner segment carries no slashes; the branch name after it may (feature/p/1-x).
_MERGE_BRANCH_RE = re.compile(r"^Merge branch '([^']+)'")
_MERGE_PR_RE = re.compile(r"^Merge pull request #\d+ from [^/\s]+/(\S+)")


def branch_from_merge_subject(subject: str) -> str | None:
    m = _MERGE_BRANCH_RE.match(subject)
    if m:
        return m.group(1)
    m = _MERGE_PR_RE.match(subject)
    if m:
        return m.group(1)
    return None


@dataclass(frozen=True)
class TaskView:
    task: registry.Task
    state: str
    branch: str | None = None


@dataclass(frozen=True)
class SprintView:
    tasks: list[TaskView]
    # Task branches whose (project, number) key has no registry entry.
    unknown_branches: list[str]


def compute(
    cwd: Path, cfg: config.Config, reg: registry.Registry, remote: str = "origin"
) -> SprintView:
    # ALL live branches per key: a retaken (reopened) task has two — the stale
    # pre-merge one and the declared fix one (task tooling/26)
    live: dict[tuple[str, int], list[str]] = {}
    unknown: list[str] = []
    registry_keys = {(t.project, t.id) for t in reg.all()}
    for name in gitwrap.remote_heads(cwd, remote):
        m = cfg.match_branch(name)
        if not m:
            continue  # off-taxonomy branches are not jearless business (README open question)
        key = (m.group("project"), int(m.group("num")))
        if key not in registry_keys:
            unknown.append(name)
            continue
        live.setdefault(key, []).append(name)

    done: dict[tuple[str, int], set[str]] = {}  # key -> shas of done-merges, all refs
    refs_to_walk = [f"{remote}/{cfg.trunk_ref}"]
    if cfg.integration_ref:
        refs_to_walk.append(cfg.live_ref(cwd, remote))  # GitFlow mode (task tooling/32)
    for ref in refs_to_walk:
        try:
            merges = gitwrap.lines(["log", ref, "--merges", "--format=%H%x1f%s"], cwd)
        except GitError:
            continue  # the integration branch may not exist yet
        for line in merges:  # newest first
            sha, subject = line.split("\x1f", 1)
            branch = branch_from_merge_subject(subject)
            if not branch:
                continue
            m = cfg.match_branch(branch)
            if m:
                done.setdefault((m.group("project"), int(m.group("num"))), set()).add(sha)

    def _reopened(branch_name: str, done_shas: set[str]) -> bool:
        """Derived reopen (task tooling/26) by SHA, not clocks: the live branch
        forked at-or-after ANY done-merge of the task (a done sha is an ancestor
        of — or equal to — the branch's fork point) means rework is under way,
        in_progress wins over done. A stale pre-merge branch (forked before
        every done-merge) stays done. No same-second traps: shas, not dates."""
        try:
            base = gitwrap.out(["merge-base", ref, branch_name], cwd)
        except GitError:
            return False
        return any(gitwrap.is_ancestor(done_sha, base, cwd) for done_sha in done_shas)

    ref = f"{remote}/{cfg.trunk_ref}"
    views: list[TaskView] = []
    for task in reg.all():
        key = (task.project, task.id)
        branches = live.get(key, [])
        if key in done:
            # done overrides stale branches — but a branch forked at-or-after
            # the done-merge reopens the task (rework under way, tooling/26)
            reopened = next((b for b in branches if _reopened(b, done[key])), None)
            if reopened:
                views.append(TaskView(task, IN_PROGRESS, reopened))
            else:
                views.append(TaskView(task, DONE))
        elif branches:
            views.append(TaskView(task, IN_PROGRESS, branches[0]))
        else:
            views.append(TaskView(task, AVAILABLE))
    return SprintView(views, sorted(unknown))
