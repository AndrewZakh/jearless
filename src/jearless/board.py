"""board: the kanban view over the canonical join (task tooling/25).

Sprint-first: with a plan (the latest by default, --plan explicit) the board
shows the planned tasks in the plan's own order — the sprint priority — plus
any unplanned work currently in progress (hiding live work would be a lie).
Without a plan, or with --all, it shows everything with per-column limits:
available — the last N by id (free and monotonic; no history walk), done —
the last N by merge date, in_progress — all (branches are few), plus the
disclosure of what did not fit. Columns are STATES, not sprints — a
multi-sprint board is refused by design: that is the velocity trend's job
(task tooling/27). The mermaid kanban type needs a v11 renderer; the output
is portable text either way. Pure view: nothing stored.
"""

from pathlib import Path

from jearless import config, gitwrap, registry, state, timeline
from jearless import plan as plan_mod
from jearless.errors import JearlessError

_DEFAULT_LIMIT = 10
_COLUMNS = (
    (state.AVAILABLE, "Available"),
    (state.IN_PROGRESS, "In progress"),
    (state.DONE, "Done"),
    (state.REJECTED, "Rejected"),  # tooling/38 — terminal, past the working set
)


def _card(tv: state.TaskView) -> str:
    label = f"{tv.task.project}/{tv.task.id} — {tv.task.summary}"
    if tv.task.story_points is not None:
        label += f" ({tv.task.story_points} pt)"
    return timeline._sanitize(label)


def run(
    cwd: Path,
    plan_path: str | None = None,
    show_all: bool = False,
    limit: int = _DEFAULT_LIMIT,
    remote: str = "origin",
) -> int:
    try:
        gitwrap.run(["fetch", "--quiet", "--prune", remote], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot fetch '{remote}': the board truth lives on the remote"
        ) from exc

    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    view = state.compute(cwd, cfg, reg, remote)
    by_key = {(tv.task.project, tv.task.id): tv for tv in view.tasks}

    plan_obj = None
    if not show_all:
        target = plan_path or plan_mod.latest_plan(cwd)
        if target:
            if not Path(target).exists():
                raise JearlessError(f"{target}: no such plan file")
            plan_obj = plan_mod.load_plan(Path(target), registry.load_all(cwd))

    columns: dict[str, list[state.TaskView]] = {s: [] for s, _ in _COLUMNS}
    notes: list[str] = []

    if plan_obj is not None:
        planned: set[tuple[str, int]] = set()
        for entry in plan_obj.entries:  # the plan's own order is the card order
            tv = by_key.get(entry.task)
            if tv is None:
                continue  # archived: not on the working board
            planned.add(entry.task)
            columns[tv.state].append(tv)
        for tv in view.tasks:  # unplanned live work still shows — hiding it would be a lie
            if (tv.task.project, tv.task.id) not in planned and tv.state == state.IN_PROGRESS:
                columns[state.IN_PROGRESS].append(tv)
        notes.append(f"%% sprint_{plan_obj.number}" if plan_obj.number else "%% plan")
    else:
        for s, _ in _COLUMNS:
            cards = sorted(
                (tv for tv in view.tasks if tv.state == s),
                key=lambda tv: (tv.task.project, tv.task.id),
            )
            if s == state.DONE:
                # "last N by merge date": oldest first, keep the tail
                ends = {
                    (b.project, b.num): b.end
                    for b in timeline.merge_bars(cwd, cfg, reg, cfg.integration_refs(cwd, remote))
                }
                cards = sorted(cards, key=lambda tv: ends.get((tv.task.project, tv.task.id), ""))
            if len(cards) > limit:
                notes.append(f"%% and {len(cards) - limit} more {s.lower()}")
                cards = cards[-limit:]
            columns[s] = cards
        notes.append("%% no plan committed — showing everything" if plan_mod.latest_plan(cwd) is None
                     else "%% --all: ignoring plans")

    lines = ["kanban"]
    for s, title in _COLUMNS:
        lines.append(f"    {s}[{title}]")
        for tv in columns[s]:
            card_id = f"{tv.task.project}_{tv.task.id}"
            lines.append(f"        {card_id}[{_card(tv)}]")
    lines.extend(notes)
    print("\n".join(lines))
    return 0
