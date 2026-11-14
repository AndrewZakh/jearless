"""timeline: the actual, derived from git (README) — start = author date of the
branch's first own commit, end = committer date of the merge commit.

All rendered times are UTC — one clock for the whole chart (task tooling/14's
bot catch: a local author date against a UTC "now" made an open bar run
backwards). Live is printed on demand and never committed; the snapshot is
frozen by a tag and becomes a release artifact (task tooling/9). Bar ids are
<project>_<num> — the join key for retro (README).
"""

import re
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jearless import config, gitwrap, registry, state

_DATE = "%Y-%m-%dT%H:%M:%S"
_UTC = {"TZ": "UTC"}  # --date=format-local renders in the process local zone

# GitHub renders mermaid in a sandbox where the page's CSS variables do not
# cascade (the var() attempt painted the text near-black on a dark canvas),
# and the default theme's section stripes swallow the bars. So we own the
# canvas: a literal dark card (GitHub's dark colors) — identical in both
# modes, readable everywhere, like a dark code block.
_CHART_THEME = (
    '%%{init: {"themeCSS": "'
    "svg{background-color:#0d1117} "
    "text{fill:#e6edf3} "
    ".section0,.section1,.section2,.section3{fill:transparent} "
    ".task,.rect{fill:#58a6ff;stroke:#1f6feb} "
    ".grid .tick line{stroke:#30363d} "
    '.grid path{stroke:#30363d}'
    '"}}%%'
)

# Second-scale bars on a days-scale axis are sub-pixel — no color saves them.
# The render floors every bar to 3% of the axis span (disclosed in the file;
# exact times live in git). Rows are per-task, so floored bars never collide.
_FLOOR_FRACTION = 0.03


def _utc_now() -> str:
    return datetime.now(UTC).strftime(_DATE)


@dataclass(frozen=True)
class Bar:
    project: str
    num: int
    label: str
    start: str
    end: str


def _author_date(cwd: Path, sha: str) -> str:
    return gitwrap.out(
        ["log", "-1", "--format=%ad", f"--date=format-local:{_DATE}", sha], cwd, env=_UTC
    )


def _label(reg: registry.Registry, m: re.Match) -> str:
    project, num = m.group("project"), int(m.group("num"))
    for task in reg.tasks.get(project, []):
        if task.id == num:
            return task.summary
    return (m.group("slug") or "task").replace("-", " ")


def _first_own_commit(cwd: Path, sha: str, excluded: str) -> str | None:
    """The oldest commit reachable from the branch tip but not from main.

    A take-created branch pointing at the main tip has no own commits yet —
    there is no honest start, and no bar (sprint already shows it as in_progress).
    """
    revs = gitwrap.out(["rev-list", "--reverse", sha, "--not", excluded], cwd)
    return revs.splitlines()[0] if revs else None


def merge_bars(cwd: Path, cfg: config.Config, reg: registry.Registry, ref: str) -> list[Bar]:
    """Done tasks: ONE bar per task — the first arrival (task tooling/11).

    The same branch can be merged twice (divergence, restore): the re-merge
    is an artifact — a task ships in the version of its first merge — so the
    earliest merge owns the bar and the newer one is discarded.
    """
    log = gitwrap.out(
        ["log", ref, "--merges", "--format=%H%x1f%s%x1f%cd", f"--date=format-local:{_DATE}"],
        cwd,
        env=_UTC,
    )
    bars: dict[tuple[str, int], Bar] = {}
    for line in reversed([ln for ln in log.splitlines() if ln.strip()]):  # oldest first
        sha, subject, cdate = line.split("\x1f", 2)
        branch = state.branch_from_merge_subject(subject)
        m = cfg.match_branch(branch) if branch else None
        if not m:
            continue
        key = (m.group("project"), int(m.group("num")))
        if key in bars:
            continue  # a re-merge: the first arrival already owns the bar
        first = _first_own_commit(cwd, f"{sha}^2", f"{sha}^1")
        start = _author_date(cwd, first) if first else cdate  # zero-commit branch: the merge is the task
        bars[key] = Bar(m.group("project"), int(m.group("num")), _label(reg, m), start, cdate)
    return list(bars.values())


def live_bars(cwd: Path, cfg: config.Config, reg: registry.Registry, remote: str = "origin") -> list[Bar]:
    """Done tasks plus in-progress branches, the latter ending 'now'."""
    done = merge_bars(cwd, cfg, reg, f"{remote}/main")
    done_keys = {(b.project, b.num) for b in done}
    now = _utc_now()
    bars = list(done)
    for name, sha in gitwrap.remote_heads(cwd, remote).items():
        m = cfg.match_branch(name)
        if not m or (m.group("project"), int(m.group("num"))) in done_keys:
            continue
        first = _first_own_commit(cwd, sha, f"{remote}/main")
        if not first:
            continue
        bars.append(
            Bar(m.group("project"), int(m.group("num")), _label(reg, m), _author_date(cwd, first), now)
        )
    return bars


def _sanitize(label: str) -> str:
    return re.sub(r"[:,\n]", " ", label).strip()


def _floor_slivers(bars: list[Bar]) -> tuple[list[Bar], str | None]:
    """Stretch sub-pixel bars to 3% of the axis span; longer bars are untouched.

    The floor distorts only the rendered END of a sliver — the start stays
    true, and the disclosure rides the chart as a mermaid comment.
    """
    if not bars:
        return bars, None
    span = max(datetime.fromisoformat(b.end) for b in bars) - min(
        datetime.fromisoformat(b.start) for b in bars
    )
    floor = timedelta(seconds=span.total_seconds() * _FLOOR_FRACTION)
    if floor <= timedelta(0):
        return bars, None
    out: list[Bar] = []
    floored = 0
    for bar in bars:
        duration = datetime.fromisoformat(bar.end) - datetime.fromisoformat(bar.start)
        if duration >= floor:
            out.append(bar)
            continue
        floored += 1
        out.append(
            dataclass_replace(
                bar, end=(datetime.fromisoformat(bar.start) + floor).strftime(_DATE)
            )
        )
    note = (
        f"%% visibility floor: {floor} per bar ({floored} bar(s) stretched) —"
        " exact times live in git"
    )
    return out, note


def render(
    cwd: Path, snapshot: str | None = None, remote: str = "origin", title: str | None = None
) -> str:
    """The gantt as text; `title` overrides the chart title (used by release)."""
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    if snapshot:
        bars = merge_bars(cwd, cfg, reg, snapshot)
        title = title or f"jearless — snapshot {snapshot}"
    else:
        bars = live_bars(cwd, cfg, reg, remote)
        title = title or "jearless — live"
    bars, floor_note = _floor_slivers(bars)
    lines = [
        _CHART_THEME,
        "gantt",
        f"    title {title}",
        # mermaid's own tokens, not strftime patterns — %Y would not render
        "    dateFormat YYYY-MM-DDTHH:mm:ss",
        "    axisFormat %d.%m %H:%M",
    ]
    if floor_note:
        lines.append(floor_note)
    for project in sorted({b.project for b in bars}):
        lines.append(f"    section {project}")
        for bar in sorted(
            (b for b in bars if b.project == project), key=lambda b: (b.start, b.num)
        ):
            lines.append(f"    {_sanitize(bar.label)} :{bar.project}_{bar.num}, {bar.start}, {bar.end}")
    return "\n".join(lines) + "\n"


def run(cwd: Path, snapshot: str | None = None, remote: str = "origin") -> int:
    print(render(cwd, snapshot=snapshot, remote=remote), end="")
    return 0
