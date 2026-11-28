"""export: the whole join as flat rows — CSV for spreadsheets, JSON for
integrations (task tooling/68).

One row per task: the frozen facts from the registry, the derived state, and
every date the tool honestly has. Read-only: stdout by default, --output
FILE when asked. Times are UTC; commit dates are client clocks (the
manifest: hours are not measured, duration is).

Period boundaries resolve to delivery moments and never drop rows — they
fill the in_period column:

- ``2026-11-25`` — a plain date;
- ``p/12`` — that task's first-arrival merge;
- ``sprint-27`` (any branch name) — that branch's promotion merge on the
  trunk.

A task is in the period when its first-arrival merge falls between the
boundaries. Undelivered tasks always ride along with empty dates and
``in_period = false``.

Columns (frozen, in this order): project, id, summary, description,
story_points, depends_on, rejected, archived, state, branch, created_at,
taken_at, merged_at, pr_created_at, pr_merged_at, in_period.

branch is the live branch while the task is in progress, otherwise the
branch that delivered it.
"""

import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from jearless import config, forge, gitwrap, registry, state, timeline
from jearless import report as report_mod
from jearless.errors import JearlessError

_DATE = "%Y-%m-%dT%H:%M:%S"
_UTC = {"TZ": "UTC"}

_COLUMNS = [
    "project", "id", "summary", "description", "story_points", "depends_on",
    "rejected", "archived", "state", "branch", "created_at", "taken_at",
    "merged_at", "pr_created_at", "pr_merged_at", "in_period",
]

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TASK_RE = re.compile(r"([a-z0-9_]+)/(\d+)")


def _committer_date(cwd: Path, sha: str) -> str:
    return gitwrap.out(
        ["log", "-1", "--format=%cd", f"--date=format-local:{_DATE}", sha], cwd, env=_UTC
    )


def _taken_at_delivered(cwd: Path, merge_sha: str) -> str:
    """The author date of the first commit the delivered task's branch carried."""
    own = timeline.own_commits(cwd, merge_sha)
    return timeline._author_date(cwd, own[0]) if own else ""


def _taken_at_live(cwd: Path, branch: str, live_ref: str) -> str:
    """The author date of the first commit of a task still in progress:
    its commits not yet on the trunk. Empty when only the claim exists."""
    revs = gitwrap.out(["rev-list", "--reverse", branch, "--not", live_ref], cwd)
    own = revs.splitlines()
    return timeline._author_date(cwd, own[0]) if own else ""


def _promotion_date(cwd: Path, cfg: config.Config, branch: str, remote: str) -> datetime:
    """When the branch was promoted: the committer date of the newest
    first-parent merge on the trunk whose second-parent side contains the
    branch's tip. A branch never promoted anchors nothing."""
    tip = f"{remote}/{branch}"
    trunk = f"{remote}/{cfg.trunk_ref}"
    try:
        gitwrap.run(["rev-parse", "--verify", "--quiet", tip], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(f"no {tip}: nothing to anchor the boundary to") from exc
    merges = gitwrap.lines(
        ["log", trunk, "--first-parent", "--merges",
         "--format=%H%x1f%P%x1f%cd", f"--date=format-local:{_DATE}"],
        cwd, env=_UTC,
    )
    for line in merges:
        _sha, parents, cdate = line.split("\x1f", 2)
        parts = parents.split()
        second = parts[1] if len(parts) > 1 else None
        if second and gitwrap.is_ancestor(tip, second, cwd):
            return datetime.fromisoformat(cdate)
    raise JearlessError(f"{branch}: no promotion merge found on {trunk}")


def _resolve_boundary(
    cwd: Path,
    cfg: config.Config,
    value: str,
    remote: str,
    delivered: dict[tuple[str, int], str],
) -> datetime:
    """A boundary value -> a moment: a date, a delivered task (p/N), a tag
    (its release commit on the trunk), or a branch name (its promotion merge
    on the trunk)."""
    if _DATE_RE.fullmatch(value):
        return datetime.fromisoformat(value)
    m = _TASK_RE.fullmatch(value)
    if m:
        when = delivered.get((m.group(1), int(m.group(2))))
        if when is None:
            raise JearlessError(
                f"{value}: not delivered — nothing to anchor the boundary to"
            )
        return datetime.fromisoformat(when)
    try:
        return datetime.fromisoformat(
            _committer_date(cwd, f"refs/tags/{value}")
        )
    except gitwrap.GitError:
        pass  # not a tag either — the branch anchor is the last resort
    return _promotion_date(cwd, cfg, value, remote)


def _rows(cwd: Path, cfg: config.Config, remote: str) -> list[dict]:
    """Every task in the union as one flat row, the join already applied."""
    reg = registry.load_all(cwd)
    view = state.compute(cwd, cfg, reg, remote)
    live_ref = cfg.live_ref(cwd, remote)

    first_sha, first_branch, _returns, _total, _fix = report_mod._task_merges(
        cwd, cfg, None, live_ref
    )
    pr_map = forge.pr_times_map(cwd)
    reg_live = registry.load(cwd)
    births = report_mod._task_births(cwd, reg_live.path) if reg_live.path else {}

    view_by_key = {(tv.task.project, tv.task.id): tv for tv in view.tasks}
    rows: list[dict] = []
    for task in sorted(reg.all(), key=lambda t: (t.project, t.id)):
        key = (task.project, task.id)
        tv = view_by_key.get(key)
        sha = first_sha.get(key)

        if tv:
            st, live_branch = tv.state, tv.branch
        else:
            # an archived task with no live branch: it shipped by definition
            # (only done tasks are archived) — the state stays derived, from
            # the archive boundary
            st, live_branch = state.DONE, ""

        merged_at = taken_at = None
        delivering_branch = first_branch.get(key, "")
        if sha:
            merged_at = _committer_date(cwd, sha)
            taken_at = _taken_at_delivered(cwd, sha)
        elif tv and tv.branch:
            taken_at = _taken_at_live(cwd, tv.branch, live_ref) or None

        pr_created = pr_merged = None
        times = pr_map.get(delivering_branch or live_branch or "")
        if times:
            pr_created, pr_merged = times

        branch = live_branch if (tv and tv.state == state.IN_PROGRESS) else delivering_branch

        rows.append({
            "project": task.project,
            "id": task.id,
            "summary": task.summary,
            "description": task.description,
            "story_points": task.story_points,
            "depends_on": "; ".join(f"{p}/{n}" for p, n in task.depends_on),
            "rejected": task.rejected,
            "archived": "true" if task.archived else "false",
            "state": st,
            "branch": branch or None,
            "created_at": births.get(key) or None,
            "taken_at": taken_at,
            "merged_at": merged_at,
            "pr_created_at": pr_created,
            "pr_merged_at": pr_merged,
            "in_period": True,
        })
    return rows


def _mark_in_period(rows: list[dict], bounds) -> None:
    lo, hi = bounds
    for row in rows:
        row["in_period"] = False
        if not row["merged_at"]:
            continue  # undelivered: never inside a delivery period
        when = datetime.fromisoformat(row["merged_at"])
        if (lo is None or when >= lo) and (hi is None or when <= hi):
            row["in_period"] = True


def run(
    cwd: Path,
    fmt: str = "csv",
    from_boundary: str | None = None,
    to_boundary: str | None = None,
    output: str | None = None,
    remote: str = "origin",
) -> int:
    if fmt not in ("csv", "json"):
        raise JearlessError(f"format must be csv or json (got '{fmt}')")
    cfg = config.load(cwd)
    try:
        gitwrap.run(["fetch", "--quiet", "--prune", remote], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot fetch '{remote}': the exported state lives on the remote"
        ) from exc

    rows = _rows(cwd, cfg, remote)
    if from_boundary or to_boundary:
        delivered = {row_key(r): r["merged_at"] for r in rows if r["merged_at"]}
        lo = _resolve_boundary(cwd, cfg, from_boundary, remote, delivered) if from_boundary else None
        hi = _resolve_boundary(cwd, cfg, to_boundary, remote, delivered) if to_boundary else None
        _mark_in_period(rows, (lo, hi))

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_COLUMNS)
        for row in rows:
            flat = []
            for c in _COLUMNS:
                value = row[c]
                if c == "in_period":
                    flat.append("true" if value else "false")
                    continue
                # the formula-injection neutralization (task tooling/72): a
                # spreadsheet executes a cell starting with =, +, - or @ —
                # prefix it so it stays text. The content is unchanged in
                # git and YAML; only the CSV cell is guarded.
                if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
                    value = "'" + value
                flat.append(value)
            writer.writerow(flat)
        text = buf.getvalue()
    else:
        text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"

    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"{len(rows)} row(s) -> {output}")
    else:
        sys.stdout.write(text)
    return 0


def row_key(row: dict) -> tuple[str, int]:
    return (row["project"], row["id"])
