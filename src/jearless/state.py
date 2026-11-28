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
REJECTED = "rejected"  # task tooling/38 — the fourth derived state

# Both merge message forms (README): local merges and forge "Create a merge commit".
# The owner segment carries no slashes; the branch name after it may (feature/p/1-x).
_MERGE_BRANCH_RE = re.compile(r"^Merge branch '([^']+)'")
_MERGE_PR_RE = re.compile(r"^Merge pull request #\d+ from [^/\s]+/(\S+)")

# Task tooling/64: a commit declares its task with a Task: trailer — the squash
# bridge (the forge's squash kills the branch name) and the hardening against
# hand-edited merge subjects. Git's trailer rule: the message's LAST paragraph;
# the generator (`jear message`) ends the message with the trailer, so the
# declaration rides where the forge keeps it.
_TRAILER_RE = re.compile(r"^Task:\s*([a-z0-9_]+)/(\d+)\s*$")


def branch_from_merge_subject(subject: str) -> str | None:
    m = _MERGE_BRANCH_RE.match(subject)
    if m:
        return m.group(1)
    m = _MERGE_PR_RE.match(subject)
    if m:
        return m.group(1)
    return None


def task_trailer(body: str) -> tuple[str, int] | None:
    """The Task: trailer of a commit message body — (project, id), or None.

    Git's semantics: trailers live in the message's last paragraph. A
    mid-body mention never attributes — a PR template's bold ``**Task:**``
    line and a note in prose are text, not a declaration. Only the final
    block declares.
    """
    if not body:
        return None
    block = body.rstrip().rsplit("\n\n", 1)[-1]
    for line in block.splitlines():
        m = _TRAILER_RE.match(line.strip())
        if m:
            return (m.group(1), int(m.group(2)))
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
    # trunk + every family branch (task tooling/67)
    refs_to_walk = cfg.integration_refs(cwd, remote)
    known = {(t.project, t.id) for t in reg.all()}
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

    # the trailer walk (task tooling/74, the hostile review's P0): commits on
    # the delivery refs' first-parent chains declaring their task — the squash
    # bridge reaches the BOARD, not just the changelog and doctor, and a merge
    # whose subject the reviewer edited away still closes its task via the
    # body. first-parent, merges included; a ghost trailer (no such task)
    # declares nothing; the merge walk above stays the legacy path. REJECTED
    # still wins in the view below — the declaration is about delivery, not
    # about the human's latest word.
    for ref in refs_to_walk:
        try:
            out = gitwrap.out(
                ["log", "--first-parent", ref, "--format=tformat:%H%x1f%B%x00"],
                cwd,
            )
        except GitError:
            continue
        for record in out.split("\x00"):
            record = record.strip("\n")
            if not record.strip():
                continue
            sha, body = record.split("\x1f", 1)
            tkey = task_trailer(body)
            if tkey and tkey in known:
                done.setdefault(tkey, set()).add(sha)

    # the sibling tips that matter for reopen (task tooling/67): non-trunk
    # delivery refs whose tip carries UNPROMOTED work — a retake forked from
    # the newest sprint carries that tip whole, while the done merge may rest
    # on an older unpromoted sibling, outside the fork base. A sibling whose
    # tip is the trunk's own history (promoted, or an empty newborn at the
    # trunk's tip) is trunk-equivalent: carrying it means "forked from the
    # trunk's past", the pre-merge leftover the stale rule protects.
    trunk_ref = f"{remote}/{cfg.trunk_ref}"
    sibling_tips = [
        r for r in refs_to_walk
        if r != trunk_ref and not gitwrap.is_ancestor(r, trunk_ref, cwd)
    ]

    def _reopened(branch_name: str, done_shas: set[str]) -> bool:
        """Derived reopen (task tooling/26) by SHA, not clocks: the live branch
        forked at-or-after ANY done-merge of the task (a done sha is an ancestor
        of — or equal to — the branch's fork point) means rework is under way,
        in_progress wins over done. A stale pre-merge branch (forked before
        every done-merge) stays done. No same-second traps: shas, not dates.

        The fork point is taken against every ref the merges were read from
        (task tooling/61): in GitFlow mode a merge may sit on the integration
        branch alone, before any promotion — measured only against the trunk
        it would be invisible and a live retake would stay done.

        Task tooling/67 adds the sibling case: a retake forked from the newest
        sprint carries that sprint's tip while the done merge rests on an
        older unpromoted sibling — outside the fork base's history, invisible
        to the fork-point rule. A branch carrying a sibling sprint's tip whole
        reopens too. The trunk's tip is deliberately not a sibling: a branch
        forked from the trunk's past is the pre-merge leftover the stale rule
        protects, and no SHA can tell it from a retake."""
        rbranch = f"{remote}/{branch_name}"
        for ref in refs_to_walk:
            try:
                base = gitwrap.out(["merge-base", ref, rbranch], cwd)
            except GitError:
                continue  # no common history with this ref — try the next
            if any(gitwrap.is_ancestor(done_sha, base, cwd) for done_sha in done_shas):
                return True
        for ref in sibling_tips:
            if gitwrap.is_ancestor(ref, rbranch, cwd):
                return True
        return False

    ref = f"{remote}/{cfg.trunk_ref}"
    views: list[TaskView] = []
    for task in reg.all():
        key = (task.project, task.id)
        branches = live.get(key, [])
        if task.rejected:
            # REJECTED wins over everything (tooling/38): the human's latest
            # declaration about the future, not a rewrite of the past — the
            # merge, if any, stays in history
            tv = TaskView(task, REJECTED)
        elif key in done:
            # done overrides stale branches — but a branch forked at-or-after
            # the done-merge reopens the task (rework under way, tooling/26)
            reopened = next((b for b in branches if _reopened(b, done[key])), None)
            tv = TaskView(task, IN_PROGRESS, reopened) if reopened else TaskView(task, DONE)
        elif branches:
            tv = TaskView(task, IN_PROGRESS, branches[0])
        else:
            tv = TaskView(task, AVAILABLE)
        if task.archived and tv.state != IN_PROGRESS:
            # archived history is off the working set — only a live retake
            # (rework in progress) brings an archived task back (task tooling/40)
            continue
        views.append(tv)
    return SprintView(views, sorted(unknown))
