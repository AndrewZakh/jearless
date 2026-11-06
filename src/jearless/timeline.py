"""timeline: the actual, derived from git (README) — start = author date of the
branch's first own commit, end = committer date of the merge commit.

Live is printed on demand and never committed; the snapshot is frozen by a tag
and becomes a release artifact (the release step's business, task tooling/9).
Bar ids are <project>_<num> — the join key for retro (README).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jearless import config, gitwrap, registry, state

_DATE = "%Y-%m-%dT%H:%M:%S"


@dataclass(frozen=True)
class Bar:
    project: str
    num: int
    label: str
    start: str
    end: str


def _author_date(cwd: Path, sha: str) -> str:
    return gitwrap.out(["log", "-1", "--format=%ad", f"--date=format:{_DATE}", sha], cwd)


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
    """Done tasks: one bar per task merge in the ref's history."""
    bars: list[Bar] = []
    log = gitwrap.out(
        ["log", ref, "--merges", "--format=%H%x1f%s%x1f%cd", f"--date=format:{_DATE}"], cwd
    )
    for line in log.splitlines():
        sha, subject, cdate = line.split("\x1f", 2)
        branch = state.branch_from_merge_subject(subject)
        m = cfg.match_branch(branch) if branch else None
        if not m:
            continue
        first = _first_own_commit(cwd, f"{sha}^2", f"{sha}^1")
        start = _author_date(cwd, first) if first else cdate  # zero-commit branch: the merge is the task
        bars.append(Bar(m.group("project"), int(m.group("num")), _label(reg, m), start, cdate))
    return bars


def live_bars(cwd: Path, cfg: config.Config, reg: registry.Registry, remote: str = "origin") -> list[Bar]:
    """Done tasks plus in-progress branches, the latter ending 'now'."""
    done = merge_bars(cwd, cfg, reg, f"{remote}/main")
    done_keys = {(b.project, b.num) for b in done}
    now = datetime.now().strftime(_DATE)
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


def run(cwd: Path, snapshot: str | None = None, remote: str = "origin") -> int:
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    if snapshot:
        bars = merge_bars(cwd, cfg, reg, snapshot)
        title = f"jearless — snapshot {snapshot}"
    else:
        bars = live_bars(cwd, cfg, reg, remote)
        title = "jearless — live"
    print("gantt")
    print(f"    title {title}")
    # mermaid's own tokens, not strftime patterns — %Y would not render
    print("    dateFormat YYYY-MM-DDTHH:mm:ss")
    print("    axisFormat %d.%m %H:%M")
    for project in sorted({b.project for b in bars}):
        print(f"    section {project}")
        for bar in sorted(
            (b for b in bars if b.project == project), key=lambda b: (b.start, b.num)
        ):
            print(f"    {_sanitize(bar.label)} :{bar.project}_{bar.num}, {bar.start}, {bar.end}")
    return 0
