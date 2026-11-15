"""retro: the authored sprint contract against the actual timeline (task tooling/20).

The plan lives in plan/sprint_N.yml — the one authored artifact (the README
manifest): dated planned windows join with first-arrival merges and report the
drift; undated entries join by membership only; merged-but-unplanned work is
the visible hole. Exit 0 — a retro is information, not a gate.
"""

from datetime import datetime
from pathlib import Path

from jearless import config, plan, registry, timeline


def run(cwd: Path, plan_path: Path, ref: str = "HEAD") -> int:
    reg = registry.load_all(cwd)
    plan_obj = plan.load_plan(plan_path, reg)
    bars = timeline.merge_bars(cwd, config.load(cwd), reg, ref)
    actual = {(b.project, b.num): b for b in bars}
    planned = {entry.task: entry for entry in plan_obj.entries}
    birth = plan.birth_date(cwd, plan_path)  # full timestamp; None = unborn

    joined = [entry for entry in plan_obj.entries if entry.task in actual]
    print(f"retro: {plan_path.name} vs actual ({len(joined)} joined)")
    for entry in joined:  # the plan's own order: top-down is the sprint priority
        bar = actual[entry.task]
        spec = f"{entry.task[0]}/{entry.task[1]}"
        actual_start = datetime.fromisoformat(bar.start)
        actual_end = datetime.fromisoformat(bar.end)
        if entry.start and entry.end:
            # calendar-day diff: sub-day drift is "on time", not ±1d (the floor trap)
            shift = (actual_end.date() - entry.end).days
            verdict = "on time" if shift == 0 else f"end {shift:+d}d"
            print(
                f"  {spec}: planned {entry.start:%m-%d}→{entry.end:%m-%d},"
                f" actual {actual_start:%m-%d}→{actual_end:%m-%d}, {verdict}"
            )
        else:
            print(f"  {spec}: merged {actual_end:%m-%d} — no planned window")
    for entry in plan_obj.entries:
        if entry.task not in actual:
            print(f"  plan-only: {entry.task[0]}/{entry.task[1]} — not done yet (or never taken)")
    # actual-only = unplanned work INSIDE the plan's lifetime: merges after the
    # plan's birth. Merges before it are pre-plan history, not a hole.
    if birth:
        birth_day = datetime.fromisoformat(birth).date()
        in_window = [
            key
            for key in sorted(set(actual) - set(planned))
            if datetime.fromisoformat(actual[key].end).date() >= birth_day
        ]
        for key in in_window:
            print(f"  actual-only: {key[0]}/{key[1]} — the work nobody planned")
        if not in_window:
            print("  actual-only: none — the scope held inside the plan's lifetime")
    else:
        print("  actual-only: skipped — the plan is unborn, there is no window yet")
    return 0
