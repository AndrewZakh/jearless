"""burndown: two derived charts over plan x merges (task tooling/27), xychart-beta.

(1) Sprint burn-down for a plan: the ideal line steps down at every planned
    end (the plan's own expectation, not an abstract slope), the actual line
    burns points at each first-arrival merge of a planned task. The window is
    the plan's git birth -> the last planned end; if merges or today run past
    it, the chart extends honestly. Undated plans degrade with a disclaimer.
(2) Velocity trend: points done per plan across sprints (plans + archives
    union x merges) — the planning-buffer answer.

Pure views, nothing stored. GitHub may not render xychart-beta — the output
is portable text (mermaid.live / CLI / IDE plugins).
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from jearless import config, gitwrap, registry, timeline
from jearless import plan as plan_mod
from jearless.errors import JearlessError

_DAY = timedelta(days=1)


def _d(ts: str) -> date:
    return datetime.fromisoformat(ts).date()


def _pts_of(reg: registry.Registry, key: tuple[str, int]) -> int:
    for task in reg.all():
        if (task.project, task.id) == key:
            return task.story_points or 0
    return 0


def _first_arrivals(bars: list[timeline.Bar]) -> dict[tuple[str, int], timeline.Bar]:
    """First arrival per task: a fix bar is rework, not the planned completion."""
    first: dict[tuple[str, int], timeline.Bar] = {}
    for bar in bars:
        first.setdefault((bar.project, bar.num), bar)
    return first


def _carry(values: dict[date, float], dates: list[date], start_value: float) -> list[str]:
    """Daily series with carry-forward between data points; whole values as ints."""
    out: list[str] = []
    current = start_value
    for d in dates:
        if d in values:
            current = values[d]
        out.append(str(int(current)) if current.is_integer() else str(round(current, 1)))
    return out


def burndown_render(cwd: Path, plan_path: Path, cfg: config.Config, remote: str = "origin") -> str:
    reg_all = registry.load_all(cwd)
    plan_obj = plan_mod.load_plan(plan_path, reg_all)
    birth = plan_mod.birth_date(cwd, plan_path)
    if birth is None:
        raise JearlessError(f"{plan_path.name}: unborn — commit the plan to burn it down")
    start = _d(birth)

    pts = {e.task: _pts_of(reg_all, e.task) for e in plan_obj.entries}
    total = sum(pts.values())
    dated = [e for e in plan_obj.entries if e.start and e.end]
    window_end = max((e.end for e in dated), default=start)
    today = date.today()
    end = max(window_end, today, start)

    dates: list[date] = []
    cursor = start
    while cursor <= end:
        dates.append(cursor)
        cursor += _DAY

    # the ideal line steps down at every planned end (the plan's own shape)
    burn_at: dict[date, float] = {}
    for entry in dated:
        burn_at[entry.end] = burn_at.get(entry.end, 0) + pts.get(entry.task, 0)
    ideal_vals: dict[date, float] = {}
    remaining = float(total)
    for d in dates:
        remaining = max(0.0, remaining - burn_at.get(d, 0.0))
        ideal_vals[d] = remaining

    # the actual line burns at each first-arrival merge of a planned task
    bars = timeline.merge_bars(cwd, cfg, reg_all, cfg.live_ref(remote))
    arrivals = _first_arrivals(bars)
    actual_burn: dict[date, float] = {}
    for entry in plan_obj.entries:
        bar = arrivals.get(entry.task)
        if bar:
            d = _d(bar.end)
            actual_burn[d] = actual_burn.get(d, 0) + pts.get(entry.task, 0)
    actual_vals: dict[date, float] = {}
    remaining = float(total)
    for d in dates:
        remaining = max(0.0, remaining - actual_burn.get(d, 0.0))
        actual_vals[d] = remaining

    y_max = max([total, 1])
    lines = [
        'xychart-beta',
        f'    title "{plan_path.stem} burn-down (planned {total} pt)"',
        '    x-axis ' + "[" + ", ".join(f'"{d.isoformat()}"' for d in dates) + "]",
        f'    y-axis "Points remaining" 0 --> {y_max}',
        "    line [" + ", ".join(_carry(ideal_vals, dates, float(total))) + "]",
        "    line [" + ", ".join(_carry(actual_vals, dates, float(total))) + "]",
    ]
    if not dated:
        lines.append("%% plan has no dated windows — the ideal spans birth -> today")
    if end > window_end:
        lines.append(f"%% chart extended past the planned window (ends {window_end})")
    return "\n".join(lines) + "\n"


def trend_render(cwd: Path, remote: str = "origin") -> str:
    """Points done per plan across sprints, against each plan's total."""
    cfg = config.load(cwd)
    reg_all = registry.load_all(cwd)
    bars = timeline.merge_bars(cwd, cfg, reg_all, f"{remote}/main")
    arrivals = _first_arrivals(bars)

    plans = sorted(plan_mod.plans_dir(cwd).glob("sprint_*.yml")) if plan_mod.plans_dir(cwd).exists() else []
    if not plans:
        raise JearlessError("no plans committed under .jearless/plans/ — nothing to trend")

    xs: list[str] = []
    done_vals: list[float] = []
    planned_vals: list[float] = []
    for path in plans:
        plan_obj = plan_mod.load_plan(path, reg_all)
        xs.append(f"sprint_{plan_obj.number}")
        done = sum(
            pts for entry in plan_obj.entries
            if (pts := _pts_of(reg_all, entry.task)) and entry.task in arrivals
        )
        total = sum(_pts_of(reg_all, e.task) for e in plan_obj.entries)
        done_vals.append(float(done))
        planned_vals.append(float(total))

    y_max = max([*planned_vals, *done_vals, 1])
    lines = [
        "xychart-beta",
        '    title "velocity trend — points done per sprint"',
        "    x-axis " + "[" + ", ".join(f'"{x}"' for x in xs) + "]",
        f'    y-axis "Points" 0 --> {int(y_max) + 1}',
        "    bar [" + ", ".join(str(int(v)) if v.is_integer() else str(round(v, 1)) for v in done_vals) + "]",
        "    line [" + ", ".join(str(int(v)) if v.is_integer() else str(round(v, 1)) for v in planned_vals) + "]",
    ]
    return "\n".join(lines) + "\n"


def run(cwd: Path, plan_path: str | None = None, trend: bool = False, remote: str = "origin") -> int:
    try:
        gitwrap.run(["fetch", "--quiet", "--prune", remote], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot fetch '{remote}': the burn-down truth lives on the remote"
        ) from exc
    if trend:
        print(trend_render(cwd, remote), end="")
        return 0
    target = plan_path or plan_mod.latest_plan(cwd)
    if not target:
        raise JearlessError("no plans committed under .jearless/plans/ — author sprint_N.yml first")
    if not Path(target).exists():
        raise JearlessError(f"{target}: no such plan file")
    print(burndown_render(cwd, Path(target), config.load(cwd), remote), end="")
    return 0
