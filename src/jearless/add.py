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

from jearless import config, duplicate, forge, gitwrap, registry, state
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
    """Both homes — the registry split taught this the hard way (task tooling/46):
    a root-only glob missed `.jearless/archive_*.yml` and allocated ids that
    collided with archived tasks. The union is the one identity reader."""
    return registry.load_all(cwd).max_id(project)


def _max_from_branches(cwd: Path, cfg: config.Config, project: str, remote: str) -> int | None:
    """None means origin is unreachable: the id is then based on the registry only."""
    try:
        heads = gitwrap.remote_heads(cwd, remote)
    except gitwrap.GitError:
        return None
    best = 0
    ride_prefix = f"registry/{project}-"
    ride_branches: list[str] = []
    for name in heads:
        m = cfg.match_branch(name)
        if m and m.group("project") == project:
            best = max(best, int(m.group("num")))
        elif name.startswith(ride_prefix) and not name.endswith("-rejected"):
            # the add-ride branches (task tooling/63): the branch name freezes
            # at the burst's first add, but the entries inside grow — read the
            # branch's registry file, not the name
            ride_branches.append(name)
    for name in ride_branches:
        for home in (f"{config.HOMEDIR}/{REGISTRY_NAME}", REGISTRY_NAME):
            try:
                text = gitwrap.out(["show", f"{remote}/{name}:{home}"], cwd)
            except gitwrap.GitError:
                continue  # the registry lives in the other home on that branch
            branch_reg = registry.from_text(text, name)
            best = max(best, branch_reg.max_id(project))
            break
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
    depends: list[str] | None = None,
) -> int:
    if not PROJECT_RE.match(project):
        raise JearlessError("project names are [a-z0-9_]: they live in branch names")
    summary = summary.strip()
    if not summary:
        raise JearlessError("summary must not be empty")

    cfg = config.load(cwd)
    _guard(cwd, cfg, summary, remote, yes)
    reg = registry.load(cwd)
    candidates = [reg.max_id(project), _max_from_archives(cwd, project)]
    from_branches = _max_from_branches(cwd, cfg, project, remote)
    if from_branches is not None:
        candidates.append(from_branches)
    else:
        print(
            f"jear: cannot reach '{remote}' — next id checked against the registry and archives only",
            file=sys.stderr,
        )
    next_id = max(candidates) + 1

    deps = registry.parse_dep_spec(project, depends) if depends else ()
    if deps:
        # self-dep first: the new task cannot exist in load_all yet, so the
        # existence loop would misreport this as "no such task"
        if (project, next_id) in deps:
            raise JearlessError("--depends: the new task cannot point at itself")
        known = {(t.project, t.id) for t in registry.load_all(cwd).all()}
        for dep in deps:
            if dep not in known:
                raise JearlessError(
                    f"--depends {dep[0]}/{dep[1]}: no such task in the registry or archives"
                )

    path = reg.path  # the resolved home (or the .jearless birth path)
    path.parent.mkdir(parents=True, exist_ok=True)  # the .jearless birth
    entry: dict = {"id": next_id, "summary": summary}
    if deps:
        entry["depends_on"] = [
            dep[1] if dep[0] == project else f"{dep[0]}/{dep[1]}" for dep in deps
        ]
    if points is not None:
        entry["story_points"] = points

    def apply_entry(cwd: Path) -> None:
        """Append the entry to the registry file as it exists in the current
        worktree — the ride calls this on its own branch, so a burst appends
        to the branch's version, never clobbering the entries before it."""
        yaml = YAML(typ="rt")  # round-trip: comments survive the append
        yaml.indent(mapping=2, sequence=4, offset=2)
        yaml.width = 100000  # never wrap a long summary
        data = yaml.load(path) if path.exists() else None
        if data is None:
            data = yaml.load(_TEMPLATE)
        if not isinstance(data, dict):
            raise JearlessError(f"{REGISTRY_NAME}: expected a mapping at the top level")
        data.setdefault("tasks", {}).setdefault(project, []).append(entry)
        yaml.dump(data, path)

    if gitwrap.is_repo(cwd):
        print(f"task {project}/{next_id} added")
        rode = forge.add_ride(
            cwd,
            project=project,
            num=next_id,
            files=[str(path)],
            title=f"tasks.yml: {project}/{next_id} — {summary}",
            body=f"{project}/{next_id}: {summary}\n\n(the registry mutation rides the forge — task tooling/53)",
            label="registry",
            base=cfg.trunk_ref,
            trunk=cfg.trunk_ref,
            remote=remote,
            apply_entry=apply_entry,
        )
        if not rode:
            apply_entry(cwd)
            gitwrap.run(["add", str(path)], cwd)
            print("the registry edit is written and staged — open the pull request by hand")
    else:
        apply_entry(cwd)
        print(f"task {project}/{next_id} added — the registry is written; commit it when the repo exists")
    return next_id
