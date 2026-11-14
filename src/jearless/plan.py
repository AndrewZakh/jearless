"""plan: the authored sprint contract (task tooling/16) — hand-written yaml.

plan/sprint_N.yml lives in `.jearless/plans/`. The file's git birth IS the
sprint start — nothing stores a date. The order of ids is the sprint
priority (the README manifest). Unknown ids, duplicates and inconsistent
dates refuse loud — the same visible-hole philosophy as check_links. The
gantt-of-the-plan is DERIVED from this file (--gantt): one authored plan,
no drift with hand-drawn chart artifacts.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from jearless import gitwrap, registry, timeline
from jearless.errors import JearlessError

PLAN_DIR_NAME = "plans"
PLAN_FILE_RE = re.compile(r"^sprint_(\d+)\.yml$")
_TASK_RE = re.compile(r"^([a-z0-9_]+)/(\d+)$")


@dataclass(frozen=True)
class PlanEntry:
    task: tuple[str, int]
    start: date | None
    end: date | None
    order: int  # the position in the file — the sprint priority


@dataclass(frozen=True)
class Plan:
    path: Path
    number: int
    goal: str
    entries: list[PlanEntry]

    def tasks(self) -> list[tuple[str, int]]:
        return [entry.task for entry in self.entries]


def plans_dir(cwd: Path) -> Path:
    return cwd / registry.HOMEDIR / PLAN_DIR_NAME


def next_plan_number(cwd: Path) -> int:
    """max over plan files + 1, eternal — the task-id allocation pattern."""
    best = 0
    plans = plans_dir(cwd)
    if plans.exists():
        for path in plans.iterdir():
            m = PLAN_FILE_RE.match(path.name)
            if m:
                best = max(best, int(m.group(1)))
    return best + 1


def latest_plan(cwd: Path) -> Path | None:
    """The current plan is never guessed by commands — but report's scope creep
    needs one, and there the highest number is the honest pick."""
    plans = plans_dir(cwd)
    if not plans.exists():
        return None
    numbered = []
    for path in plans.iterdir():
        m = PLAN_FILE_RE.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    return max(numbered)[1] if numbered else None


def _as_date(value: object, where: str) -> date:
    try:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise JearlessError(f"{where}: dates must be ISO YYYY-MM-DD ({exc})") from exc


def load_plan(path: Path, reg: registry.Registry) -> Plan:
    """Parse + validate against the union: unknown ids and duplicates refuse loud."""
    yaml = YAML(typ="rt")
    try:
        data = yaml.load(path)
    except YAMLError as exc:
        raise JearlessError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("plan"), dict):
        raise JearlessError(f"{path.name}: expected the 'plan:' mapping")
    goal = str(data["plan"].get("goal") or "")
    raw_entries = data["plan"].get("tasks", [])
    if not isinstance(raw_entries, list):
        raise JearlessError(f"{path.name}: plan.tasks must be a list")

    known = {(t.project, t.id) for t in reg.all()}
    entries: list[PlanEntry] = []
    seen: set[tuple[str, int]] = set()
    for i, raw in enumerate(raw_entries):
        where = f"{path.name}: entry {i}"
        if not isinstance(raw, dict) or "task" not in raw:
            raise JearlessError(f"{where} must carry 'task: project/number'")
        spec = str(raw["task"]).strip()
        m = _TASK_RE.match(spec)
        if not m:
            raise JearlessError(f"{where}: '{spec}' — expected 'project/number'")
        key = (m.group(1), int(m.group(2)))
        if key not in known:
            raise JearlessError(
                f"{path.name}: planned task {spec} — no such task in the registry or archives"
            )
        if key in seen:
            raise JearlessError(f"{path.name}: {spec} is planned twice")
        seen.add(key)
        start = end = None
        planned = raw.get("planned")
        if planned is not None:
            if not isinstance(planned, dict):
                raise JearlessError(f"{where}: 'planned' must be a mapping of start/end")
            start = _as_date(planned["start"], where)
            end = _as_date(planned["end"], where)
            if end < start:
                raise JearlessError(f"{where}: planned end before start")
        entries.append(PlanEntry(key, start, end, i))

    m = PLAN_FILE_RE.match(path.name)
    number = int(m.group(1)) if m else 0
    return Plan(path, number, goal, entries)


def birth_date(cwd: Path, path: Path) -> str | None:
    """The file's git birth IS the sprint start — nothing stores a date.

    Full timestamp precision: report's scope creep compares this against
    per-task birth times, and same-day granularity would lie. An uncommitted
    plan is unborn: commit it to start the sprint.
    """
    try:
        lines = gitwrap.lines(
            ["log", "--follow", "--diff-filter=A", "--format=%cd",
             "--date=format-local:%Y-%m-%dT%H:%M:%S", "--", str(path)],
            cwd,
            env={"TZ": "UTC"},
        )
    except gitwrap.GitError:
        return None  # not a repo / not committed yet
    return lines[-1] if lines else None  # the oldest add wins


def _plan_gantt(plan: Plan, reg: registry.Registry) -> str:
    """The derived gantt-of-the-plan: dated windows only, undated tasks listed in a comment."""
    labels = {(t.project, t.id): t.summary for t in reg.all()}
    lines = [timeline._CHART_THEME, "gantt", f"    title plan sprint_{plan.number}",
             "    dateFormat YYYY-MM-DD", "    axisFormat %d.%m"]
    undated: list[str] = []
    for entry in plan.entries:
        spec = f"{entry.task[0]}/{entry.task[1]}"
        if entry.start and entry.end:
            label = timeline._sanitize(labels.get(entry.task, spec))
            lines.append(f"    {label} :{entry.task[0]}_{entry.task[1]}, {entry.start}, {entry.end}")
        else:
            undated.append(spec)
    if undated:
        lines.append(f"%% undated (no planned window): {', '.join(undated)}")
    return "\n".join(lines) + "\n"


def run(cwd: Path, path: Path, gantt: bool = False) -> int:
    reg = registry.load_all(cwd)
    plan = load_plan(path, reg)
    tasks_by_key = {(t.project, t.id): t for t in reg.all()}
    birth = birth_date(cwd, path)

    header = f"sprint_{plan.number}" if plan.number else path.name
    print(f"{header}: {plan.goal}" if plan.goal else header)
    if birth:
        print(f"sprint start: {birth} (the file's git birth)")
    else:
        print("sprint start: unborn — commit the plan to start the sprint")
    total = 0
    print(f"committed: {len(plan.entries)} task(s)")
    for entry in plan.entries:
        task = tasks_by_key.get(entry.task)
        spec = f"{entry.task[0]}/{entry.task[1]}"
        line = f"  {entry.order + 1}. {spec}"
        if task:
            if task.story_points is not None:
                total += task.story_points
                line += f" ({task.story_points} pt)"
            line += f"  {task.summary}"
        if entry.start and entry.end:
            line += f"  · planned {entry.start:%m-%d} → {entry.end:%m-%d}"
        print(line)
    print(f"total: {total} pt")
    if gantt:
        print(_plan_gantt(plan, reg), end="")
    return 0
