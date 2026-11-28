"""events: the lifecycle as a versioned JSON stream (task tooling/73).

A deterministic PULL-based export — the Event Model the third review parked,
now derived from the machinery that already exists (no new traversal): every
event is a commit the tool already reads. The consumer pulls and dedupes by
a stable id; replay is re-running the command; a partial failure delivers
nothing because nothing is delivered — jearless never pushes. Read-only:
stdout, one JSON object per line, each line an envelope carrying the schema
version so the shape can evolve without breaking old consumers.

The id is ``type:key:sha`` — stable across re-runs and clones, readable by a
human, dedupe-able by a machine. The stream is ordered by committer time
(stable git metadata, never a wall clock), ties by sha; within the merge
source the walk itself is topo-ordered, so first arrivals are first.

Events (one carrier per fact: key, sha, time — nothing else):
- task.created   — the commit that first named the task in the registry
- task.started   — the first own commit of the task's branch
- task.merged    — the first-arrival merge
- task.returned  — each re-merge beyond the first
- task.rejected  — the commit that first carried the rejected cause
- sprint.opened  — the commit that added the sprint plan
- release.tagged — the commit an annotated tag points at

The stream reads the LOCAL clone: freshness is the consumer's last pull —
that is the pull model, and replay must work offline.
"""

import json
import sys
from pathlib import Path

from jearless import config, gitwrap, registry, state, timeline
from jearless import report as report_mod
from jearless.errors import JearlessError

SCHEMA_VERSION = 1
_DATE = "%Y-%m-%dT%H:%M:%S"
_UTC = {"TZ": "UTC"}


def _event(etype: str, key: str, sha: str, ctime: str) -> dict:
    return {
        "v": SCHEMA_VERSION,
        "id": f"{etype}:{key}:{sha}",
        "type": etype,
        "key": key,
        "sha": sha,
        "time": ctime,
    }


def _committer_date(cwd: Path, sha: str) -> str:
    return gitwrap.out(
        ["log", "-1", "--format=%cd", f"--date=format-local:{_DATE}", sha], cwd, env=_UTC
    )


def _registry_events(cwd: Path, reg_path: Path) -> tuple[list[dict], list[dict]]:
    """task.created and task.rejected in ONE walk over the registry's history:
    the oldest commit naming the task, and the oldest commit whose version of
    the file carries its rejected cause."""
    created: dict[tuple[str, int], dict] = {}
    rejected: dict[tuple[str, int], dict] = {}
    commits = gitwrap.lines(
        ["log", "--reverse", "--follow", "--format=%H%x1f%cd",
         f"--date=format-local:{_DATE}", "--", str(reg_path)],
        cwd,
        env=_UTC,
    )
    candidates = (
        str(reg_path),
        f"{registry.HOMEDIR}/{registry.REGISTRY_NAME}",
        registry.REGISTRY_NAME,
    )
    for line in commits:
        sha, cdate = line.split("\x1f", 1)
        text = None
        for candidate in candidates:
            try:
                text = gitwrap.out(["show", f"{sha}:{candidate}"], cwd)
                break
            except gitwrap.GitError:
                text = None  # the file lived elsewhere (the rename)
        if text is None:
            continue
        try:
            snapshot = registry.from_text(text, f"{sha}").all()
        except registry.RegistryError:
            continue  # a historical version the current contract refuses — skip it
        for task in snapshot:
            key = (task.project, task.id)
            name = f"{task.project}/{task.id}"
            if key not in created:
                created[key] = _event("task.created", name, sha, cdate)
            if task.rejected and key not in rejected:
                rejected[key] = _event("task.rejected", name, sha, cdate)
    return list(created.values()), list(rejected.values())


def _started_events(
    cwd: Path, remote: str, refs: list[str], first_sha: dict, view: state.SprintView
) -> list[dict]:
    """task.started: the first own commit of the task's branch — for a
    delivered task, the first commit its delivering branch carried; for a
    live branch, the first commit not yet on a delivery ref. The claim alone
    (a zero-commit branch) started nothing: no commit, no event."""
    events: list[dict] = []
    for tv in view.tasks:
        if tv.state == state.DONE:
            key = (tv.task.project, tv.task.id)
            if key not in first_sha:
                continue
            own = timeline.own_commits(cwd, first_sha[key])
            sha = own[0] if own else None
        elif tv.state == state.IN_PROGRESS and tv.branch:
            revs = gitwrap.out(
                ["rev-list", "--reverse", f"{remote}/{tv.branch}", "--not", *refs], cwd
            )
            own = revs.splitlines()
            sha = own[0] if own else None
        else:
            continue  # available, rejected, or a claim without commits
        if sha:
            events.append(
                _event("task.started", f"{tv.task.project}/{tv.task.id}", sha, _committer_date(cwd, sha))
            )
    return events


def _sprint_events(cwd: Path) -> list[dict]:
    """sprint.opened: the commit that added the sprint plan (the plan's git
    birth). One commit may add several plans — one event per plan, keyed by
    the file's stem."""
    events: list[dict] = []
    plans = f"{config.HOMEDIR}/plans"
    for line in gitwrap.lines(
        ["log", "--reverse", "--diff-filter=A", "--format=%H%x1f%cd",
         f"--date=format-local:{_DATE}", "--", plans],
        cwd,
        env=_UTC,
    ):
        sha, cdate = line.split("\x1f", 1)
        names = gitwrap.lines(
            ["diff-tree", "--no-commit-id", "--name-only", "--diff-filter=A", "-r", sha, "--", plans],
            cwd,
        )
        for name in names:
            events.append(_event("sprint.opened", Path(name).stem, sha, cdate))
    return events


def _release_events(cwd: Path) -> list[dict]:
    """release.tagged: the commit a tag points at. The tag object itself is
    not a commit — the event anchors to the release moment's commit, so
    --since (which walks commits) stays honest. Fields split on spaces:
    refnames cannot contain whitespace, and the date format has none
    (for-each-ref does not interpolate %xNN, unlike git log)."""
    events: list[dict] = []
    for line in gitwrap.lines(
        ["for-each-ref", "refs/tags",
         "--format=%(refname:short) %(*objectname) %(objectname)"
         " %(creatordate:format-local:" + _DATE + ")"],
        cwd,
        env=_UTC,
    ):
        name, peeled, obj, cdate = line.split()
        events.append(_event("release.tagged", name, peeled or obj, cdate))
    return events


def run(cwd: Path, since: str | None = None, fmt: str = "json") -> int:
    if fmt != "json":
        raise JearlessError(f"format must be json (got '{fmt}')")
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    refs = cfg.integration_refs(cwd, "origin")

    reg_live = registry.load(cwd)
    created, rejected = _registry_events(cwd, reg_live.path) if reg_live.path else ([], [])
    first_sha, _fb, returns, _total, _fix = report_mod._task_merges(cwd, cfg, None, refs)
    merged = [
        _event("task.merged", f"{p}/{n}", sha, _committer_date(cwd, sha))
        for (p, n), sha in first_sha.items()
    ]
    returned = [
        _event("task.returned", f"{p}/{n}", sha, _committer_date(cwd, sha))
        for (p, n), sha in returns
    ]
    view = state.compute(cwd, cfg, reg, "origin")
    started = _started_events(cwd, "origin", refs, first_sha, view)

    events = created + started + merged + returned + rejected
    events += _sprint_events(cwd) + _release_events(cwd)

    if since:
        try:
            reachable = set(gitwrap.out(["rev-list", since], cwd).split())
        except gitwrap.GitError as exc:
            raise JearlessError(f"--since {since}: no such ref") from exc
        events = [e for e in events if e["sha"] not in reachable]
    events.sort(key=lambda e: (e["time"], e["sha"]))
    for event in events:
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    return 0
