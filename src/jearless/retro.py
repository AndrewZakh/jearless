"""retro: the plan gantt (the team's committed contract) against the actual timeline.

Bar ids in the plan must be task ids — <project>_<num> (README): that is the join
key. Planning misses are printed for the retrospective; the exit code stays 0,
a retro is information, not a gate.
"""

import re
from datetime import datetime
from pathlib import Path

from jearless import config, registry, timeline
from jearless.errors import JearlessError

# "name :id, start, end" — a mermaid gantt task line with explicit dates.
_PLAN_LINE = re.compile(
    r"^\s*(?P<label>.+?)\s*:\s*(?P<id>[a-z0-9_]+)\s*,\s*"
    r"(?P<start>\d{4}-\d{2}-\d{2}(?:T[\d:]+)?)\s*,\s*"
    r"(?P<end>\d{4}-\d{2}-\d{2}(?:T[\d:]+)?)\s*$"
)
_SKIP_FIRST_WORDS = {
    "gantt", "title", "dateformat", "axisformat", "section",
    "todaymarker", "excludes", "weekend", "%%",
}


def _parse_plan(path: Path) -> dict[str, tuple[datetime, datetime]]:
    plan: dict[str, tuple[datetime, datetime]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        first = line.strip().split(" ", 1)[0].lower()
        if first in _SKIP_FIRST_WORDS or first.startswith("#"):
            continue
        m = _PLAN_LINE.match(line)
        if m:
            plan[m.group("id")] = (
                datetime.fromisoformat(m.group("start")),
                datetime.fromisoformat(m.group("end")),
            )
    return plan


def run(cwd: Path, plan_path: Path, ref: str = "HEAD") -> int:
    try:
        plan = _parse_plan(plan_path)
    except OSError as exc:
        raise JearlessError(f"cannot read the plan: {exc}") from exc
    bars = timeline.merge_bars(cwd, config.load(cwd), registry.load_all(cwd), ref)
    actual = {f"{b.project}_{b.num}": b for b in bars}

    joined = sorted(set(plan) & set(actual))
    print(f"retro: {plan_path.name} vs actual ({len(joined)} joined)")
    for tid in joined:
        planned_start, planned_end = plan[tid]
        bar = actual[tid]
        actual_start = datetime.fromisoformat(bar.start)
        actual_end = datetime.fromisoformat(bar.end)
        # calendar-day diff: timedelta.days floors toward -infinity, so finishing
        # 20 minutes early would otherwise report as a full day early
        shift = (actual_end.date() - planned_end.date()).days
        verdict = "on time" if shift == 0 else f"end {shift:+d}d"
        print(
            f"  {tid}: planned {planned_start:%m-%d}→{planned_end:%m-%d}, "
            f"actual {actual_start:%m-%d}→{actual_end:%m-%d}, {verdict}"
        )
    for tid in sorted(set(plan) - set(actual)):
        print(f"  plan-only: {tid} — not done yet (or never taken)")
    for tid in sorted(set(actual) - set(plan)):
        print(f"  actual-only: {tid} — the work nobody planned")
    return 0
