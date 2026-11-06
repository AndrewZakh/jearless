"""The canonical three-source join (README): available / in_progress / done.

The README risk list demands exactly one implementation of this join —
this module is it. Everything else derives from here.
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
    in_progress: dict[tuple[str, int], str] = {}
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
        in_progress.setdefault(key, name)

    done: set[tuple[str, int]] = set()
    try:
        subjects = gitwrap.lines(["log", f"{remote}/main", "--merges", "--format=%s"], cwd)
    except GitError:
        subjects = []  # no origin/main yet — nothing is done
    for subject in subjects:
        branch = branch_from_merge_subject(subject)
        if not branch:
            continue
        m = cfg.match_branch(branch)
        if m:
            done.add((m.group("project"), int(m.group("num"))))

    views: list[TaskView] = []
    for task in reg.all():
        key = (task.project, task.id)
        if key in done:  # done overrides a still-existing branch (README state model)
            views.append(TaskView(task, DONE))
        elif key in in_progress:
            views.append(TaskView(task, IN_PROGRESS, in_progress[key]))
        else:
            views.append(TaskView(task, AVAILABLE))
    return SprintView(views, sorted(unknown))
