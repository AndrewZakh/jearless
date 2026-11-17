"""take: claim a task with a single push (README: the push is the occupancy signal).

--type declares the KIND of work (task tooling/19): the branch prefix is the
type's only carrier — the registry stays typeless (one carrier per fact).
Membership is never inferred here: whether the task is in a sprint plan is
derived by the report, not baked into an immutable name (the auto-hotfix
hypothesis, rejected).
"""

from pathlib import Path

from jearless import config, gitwrap, registry, slug, state
from jearless.errors import JearlessError

KINDS = ("feature", "fix", "chore")


def _find_task(reg: registry.Registry, project: str, num: int) -> registry.Task:
    for task in reg.tasks.get(project, []):
        if task.id == num:
            return task
    raise JearlessError(f"no task {project}/{num} in the registry")


def _taken_branch(heads: dict[str, str], cfg: config.Config, project: str, num: int) -> str | None:
    for name in heads:
        m = cfg.match_branch(name)
        if m and m.group("project") == project and int(m.group("num")) == num:
            return name
    return None


def take(cwd: Path, project: str, num: int, remote: str = "origin", kind: str = "feature") -> str:
    """Create <kind>/<project>/<id>-<slug> at the origin/main tip and push it.

    Zero commits, zero YAML edits (README). The ls-remote check is advisory;
    the push itself is the arbiter of the race. Kind is the declared work kind
    (feature/fix/chore) — occupancy ignores it: one task, one live branch.
    """
    if kind not in KINDS:
        raise JearlessError(f"kind must be one of: {', '.join(KINDS)} (got '{kind}')")
    cfg = config.load(cwd)
    task = _find_task(registry.load(cwd), project, num)
    if not gitwrap.is_repo(cwd):
        raise JearlessError("not a git repository")
    try:
        heads = gitwrap.remote_heads(cwd, remote)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot reach '{remote}': taking a task requires a remote — the push is the signal"
        ) from exc
    busy = _taken_branch(heads, cfg, project, num)
    if busy:
        raise JearlessError(
            f"task {project}/{num} is already taken: branch '{busy}' exists on {remote}"
        )

    base = f"{remote}/main"
    try:
        gitwrap.run(["fetch", "--quiet", remote], cwd)
        gitwrap.run(["rev-parse", "--verify", "--quiet", base], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(f"no {base}: take branches off the main tip ({exc})") from exc

    # a DONE task re-taken is rework: the kind stays declared (task tooling/26)
    view = state.compute(cwd, cfg, registry.load(cwd), remote)
    tv = next((tv for tv in view.tasks if (tv.task.project, tv.task.id) == (project, num)), None)
    if tv is not None and tv.state == state.DONE and kind != "fix":
        raise JearlessError(f"task {project}/{num} is done — re-take requires --type fix")

    branch = f"{kind}/{project}/{num}-{slug.slugify(task.summary)}"
    previous = gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd)
    try:
        gitwrap.run(["checkout", "--quiet", "-b", branch, base], cwd)
        gitwrap.run(["push", "--quiet", "-u", remote, branch], cwd)
    except gitwrap.GitError as exc:
        # Lost the race at push time: roll back and report "taken".
        gitwrap.run(["checkout", "--quiet", previous], cwd)
        gitwrap.run(["branch", "--quiet", "-D", branch], cwd)
        raise JearlessError(f"push rejected — {project}/{num} was taken by someone else") from exc
    return branch
