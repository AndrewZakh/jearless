"""add: append a task to the eternal registry — the one sanctioned YAML write.

The duplicate guard (task tooling/10) watches the door: on high keyword
overlap with existing summaries it lists the look-alikes and demands
confirmation. The most common duplicate in nature is a re-suggested DONE
task — hence the derived state next to each match.
"""

import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

from jearless import config, duplicate, gitwrap, registry, state
from jearless.errors import JearlessError
from jearless.registry import REGISTRY_NAME

# Project names live in branch names: lowercase latin, digits, underscores.
PROJECT_RE = re.compile(r"^[a-z0-9_]+$")

# The header a newborn registry is born with — the same covenant comment as the seeded one.
_TEMPLATE = """\
# The eternal jearless task registry (README: frozen facts only, no live state).
# Status is never stored: available = here without a branch; in_progress = a branch
# on origin; done = a merge commit in main.
tasks: {}
"""


def _max_from_archives(cwd: Path, project: str) -> int:
    best = 0
    for path in sorted(cwd.glob("archive_*.yml")):
        best = max(best, registry.load_path(path).max_id(project))
    return best


def _max_from_branches(cwd: Path, cfg: config.Config, project: str, remote: str) -> int | None:
    """None means origin is unreachable: the id is then based on the registry only."""
    try:
        heads = gitwrap.remote_heads(cwd, remote)
    except gitwrap.GitError:
        return None
    best = 0
    for name in heads:
        m = cfg.match_branch(name)
        if m and m.group("project") == project:
            best = max(best, int(m.group("num")))
    return best


def _states(cwd: Path, cfg: config.Config, remote: str) -> dict[tuple[str, int], str]:
    """Derived states for the warning; an unreachable origin simply drops the annotation."""
    try:
        gitwrap.run(["fetch", "--quiet", remote], cwd)
        view = state.compute(cwd, cfg, registry.load(cwd), remote)
    except (gitwrap.GitError, JearlessError):
        return {}
    return {(tv.task.project, tv.task.id): tv.state for tv in view.tasks}


def _guard(cwd: Path, cfg: config.Config, summary: str, remote: str, yes: bool) -> None:
    if yes:
        return
    matches = duplicate.find_similar(registry.load_all(cwd), summary, cfg.duplicate_threshold)
    if not matches:
        return
    states = _states(cwd, cfg, remote)
    print("warning: similar tasks exist:")
    for m in matches:
        derived = states.get((m.task.project, m.task.id))
        tag = f" ({derived})" if derived else ""
        print(f"  {m.task.project}/{m.task.id}{tag}: {m.task.summary} — {round(m.score * 100)}%")
    if not sys.stdin.isatty():
        raise JearlessError("declined: no terminal to confirm — re-run with --yes to force")
    if input("Are you sure to add? [y/N] ").strip().lower() not in ("y", "yes"):
        raise JearlessError("declined — the registry is untouched")


def add(
    cwd: Path,
    project: str,
    summary: str,
    points: int | None = None,
    remote: str = "origin",
    yes: bool = False,
) -> int:
    if not PROJECT_RE.match(project):
        raise JearlessError("project names are [a-z0-9_]: they live in branch names")
    summary = summary.strip()
    if not summary:
        raise JearlessError("summary must not be empty")

    cfg = config.load(cwd)
    _guard(cwd, cfg, summary, remote, yes)
    candidates = [registry.load(cwd).max_id(project), _max_from_archives(cwd, project)]
    from_branches = _max_from_branches(cwd, cfg, project, remote)
    if from_branches is not None:
        candidates.append(from_branches)
    else:
        print(
            f"jear: cannot reach '{remote}' — next id checked against the registry only",
            file=sys.stderr,
        )
    next_id = max(candidates) + 1

    path = cwd / REGISTRY_NAME
    yaml = YAML(typ="rt")  # round-trip: comments survive the append
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100000  # never wrap a long summary
    data = yaml.load(path) if path.exists() else None
    if data is None:
        data = yaml.load(_TEMPLATE)
    if not isinstance(data, dict):
        raise JearlessError(f"{REGISTRY_NAME}: expected a mapping at the top level")
    entry: dict = {"id": next_id, "summary": summary}
    if points is not None:
        entry["story_points"] = points
    data.setdefault("tasks", {}).setdefault(project, []).append(entry)
    yaml.dump(data, path)
    print(f"task {project}/{next_id} added — commit tasks.yml to main")
    return next_id
