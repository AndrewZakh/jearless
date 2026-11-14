"""report: the release-time PM snapshot (task tooling/17) — derived, never stored.

The changelog pattern for PM numbers: generated at the tag boundary, committed
next to it (.jearless/reports/), into the release step. Every number here is a
join over git and the union — nothing is a stored metric, and what git cannot
know (hours, money) is reported as absent, not faked.
"""

import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from jearless import config, gitwrap, plan, registry, state, timeline

_DATE = "%Y-%m-%dT%H:%M:%S"
_UTC = {"TZ": "UTC"}


def _prev_tag(cwd: Path, tag: str) -> str | None:
    try:
        return gitwrap.out(["describe", "--tags", "--abbrev=0", f"{tag}^"], cwd)
    except gitwrap.GitError:
        return None  # no earlier tag: the whole history is the range


def _task_merges(cwd: Path, cfg: config.Config, from_tag: str | None, to_ref: str):
    """First-arrival merge sha per task key in the range (re-merges collapse),
    plus merge totals for the rework rate — off-taxonomy merges count in the
    denominator only: they are work, even when they are not tasks."""
    shipped_before: set[tuple[str, int]] = set()
    if from_tag:
        for subject in gitwrap.lines(["log", from_tag, "--merges", "--format=%s"], cwd):
            branch = state.branch_from_merge_subject(subject)
            m = cfg.match_branch(branch) if branch else None
            if m:
                shipped_before.add((m.group("project"), int(m.group("num"))))
    rev_range = f"{from_tag}..{to_ref}" if from_tag else to_ref
    first: dict[tuple[str, int], str] = {}
    total_merges = 0
    fix_merges = 0
    for line in gitwrap.lines(["log", rev_range, "--merges", "--format=%H%x1f%s"], cwd):
        sha, subject = line.split("\x1f", 1)
        total_merges += 1
        branch = state.branch_from_merge_subject(subject)
        if branch and branch.split("/", 1)[0] == "fix":
            fix_merges += 1
        m = cfg.match_branch(branch) if branch else None
        if not m:
            continue
        key = (m.group("project"), int(m.group("num")))
        if key in shipped_before or key in first:
            continue  # a re-merge is an artifact: the first arrival shipped it
        first[key] = sha
    return first, total_merges, fix_merges


def _task_births(cwd: Path, reg_path: Path) -> dict[tuple[str, int], str]:
    """When each task entered the registry: the oldest commit where the id appears."""
    births: dict[tuple[str, int], str] = {}
    commits = gitwrap.lines(
        ["log", "--reverse", "--follow", "--format=%H%x1f%cd",
         f"--date=format-local:{_DATE}", "--", str(reg_path)],
        cwd,
        env=_UTC,
    )
    candidates = (str(reg_path), f"{registry.HOMEDIR}/{registry.REGISTRY_NAME}", registry.REGISTRY_NAME)
    for line in commits:
        sha, cdate = line.split("\x1f", 1)
        for candidate in candidates:
            try:
                text = gitwrap.out(["show", f"{sha}:{candidate}"], cwd)
                break
            except gitwrap.GitError:
                text = None  # the file lived elsewhere (the rename)
        if text is None:
            continue
        for task in registry.from_text(text, f"{sha}").all():
            births.setdefault((task.project, task.id), cdate)
    return births


def _attribution(cwd: Path, own: list[str], merge_sha: str) -> str:
    """Derived, nothing stored: the author of most of the branch's own commits,
    fallback — the committer of its first commit. Who merged is always exact."""
    if not own:
        return gitwrap.out(["log", "-1", "--format=%cn", merge_sha], cwd)
    names: Counter[str] = Counter()
    for sha in own:
        names[gitwrap.out(["show", "-s", "--format=%an", sha], cwd)] += 1
    return names.most_common(1)[0][0]


def _percentile(values: list[float], pct: int) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def render(cwd: Path, tag: str, from_tag: str | None = None, to_ref: str | None = None) -> str:
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    first, total_merges, fix_merges = _task_merges(cwd, cfg, from_tag, to_ref or tag)
    tasks_by_key = {(t.project, t.id): t for t in reg.all()}

    lines = [f"# Report {tag}", ""]

    points: dict[str, int] = {}
    for key in first:
        task = tasks_by_key.get(key)
        if task and task.story_points:
            points[key[0]] = points.get(key[0], 0) + task.story_points
    since = f"since {from_tag}" if from_tag else "whole history"
    lines.append("## Velocity (release — points merged " + since + ")")
    if points:
        lines.extend(f"- {p}: {v} pt" for p, v in sorted(points.items()))
    else:
        lines.append("- nothing merged")
    lines.append("")

    durations: list[float] = []
    lines.append("## Cycle time (client clocks — commit dates are self-reported)")
    for key, sha in sorted(first.items()):
        own = timeline.own_commits(cwd, sha)
        start = timeline._author_date(cwd, own[0]) if own else None
        end = gitwrap.out(
            ["log", "-1", "--format=%cd", f"--date=format-local:{_DATE}", sha], cwd, env=_UTC
        )
        if start and end:
            hours = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
            durations.append(hours)
    if durations:
        lines.append(
            f"- median {statistics.median(durations):.1f}h,"
            f" p85 {_percentile(durations, 85):.1f}h over {len(durations)} task(s)"
        )
    else:
        lines.append("- no measurable task in the range")
    lines.append("")

    lines.append("## Rework rate (fix-prefix merges / all merges)")
    if total_merges:
        lines.append(f"- {fix_merges} fix / {total_merges} merges ({round(100 * fix_merges / total_merges)}%)")
    else:
        lines.append("- no merges in the range")
    lines.append("")

    plan_path = plan.latest_plan(cwd)
    plan_birth = plan.birth_date(cwd, plan_path) if plan_path else None
    lines.append(
        "## Scope creep (tasks born after the plan's birth,"
        f" {plan_birth or 'no plan committed'})"
    )
    creep = []
    if plan_birth:
        reg_path = registry.load(cwd).path
        if reg_path and reg_path.exists():
            births = _task_births(cwd, reg_path)
            for key in sorted(set(births) & set(tasks_by_key)):
                if births[key] > plan_birth:
                    creep.append(f"- {key[0]}/{key[1]}  {tasks_by_key[key].summary}"
                                 f"  (born {births[key]})")
    lines.extend(creep or ["- none — the scope held"])
    lines.append("")

    lines.append("## Attribution (derived: most commits per task branch)")
    for key, sha in sorted(first.items()):
        own = timeline.own_commits(cwd, sha)
        lines.append(f"- {key[0]}/{key[1]} — {_attribution(cwd, own, sha)}")
    return "\n".join(lines) + "\n"


def run(cwd: Path, tag: str) -> int:
    from_tag = _prev_tag(cwd, tag)
    print(render(cwd, tag, from_tag), end="")
    return 0
