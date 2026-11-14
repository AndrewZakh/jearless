"""sprint: the board computed on demand — fetch --prune, then the canonical join."""

from pathlib import Path

from jearless import config, gitwrap, registry, state
from jearless.errors import JearlessError

_SECTION_ORDER = (state.IN_PROGRESS, state.AVAILABLE, state.DONE)


def run(cwd: Path, remote: str = "origin") -> int:
    try:
        gitwrap.run(["fetch", "--quiet", "--prune", remote], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot fetch '{remote}': the sprint truth lives on the remote"
        ) from exc
    view = state.compute(cwd, config.load(cwd), registry.load(cwd), remote)
    for section in _SECTION_ORDER:
        group = [tv for tv in view.tasks if tv.state == section]
        print(f"{section} ({len(group)}):")
        for tv in sorted(group, key=lambda tv: (tv.task.project, tv.task.id)):
            line = f"  {tv.task.project}/{tv.task.id}  {tv.task.summary}"
            if tv.task.story_points is not None:
                line += f" ({tv.task.story_points} pt)"
            if tv.task.depends_on:
                line += "  after " + ", ".join(f"{p}/{n}" for p, n in tv.task.depends_on)
            if tv.branch:
                line += f"  [{tv.branch}]"
            print(line)
    if view.unknown_branches:
        print(f"branches without a registry task ({len(view.unknown_branches)}):")
        for name in view.unknown_branches:
            print(f"  {name}")
    return 0
