"""lifecycle: the charter's branch lifecycle as commands (task tooling/58).

jear prune — delete local branches fully merged into origin/main. The forge
auto-deletes the origin side on merge; the local copies are ours to clean.
Unmerged branches are refused (`git branch -d` double-checks — nothing
unpushed is lost).

jear message <project>/<id> — the squash-box message with the Task: trailer,
for adopters whose orgs mandate squash (the trailer survives the squash; our
own repos stay --no-ff). Works over the union: archived tasks too.
"""

from pathlib import Path

from jearless import config, gitwrap, registry
from jearless.errors import JearlessError


def run_prune(cwd: Path, remote: str = "origin") -> int:
    cfg = config.load(cwd)
    ref = f"{remote}/{cfg.trunk_ref}"
    merged = gitwrap.lines(["branch", "--merged", ref], cwd)
    current = gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd)
    prunable: list[str] = []
    for line in merged:
        name = line.strip()
        if name.startswith("* ") or name.startswith("("):
            continue  # the checked-out branch / a detached marker
        if name == current or name == cfg.trunk_ref:
            continue
        prunable.append(name)
    if not prunable:
        print(f"prune: no local branches fully merged into {ref}")
        return 0
    for name in prunable:
        gitwrap.run(["branch", "-d", name], cwd)  # lowercase -d: refuses unmerged
        print(f"pruned {name} (merged into {ref})")
    print(f"prune: {len(prunable)} branch(es) deleted; unmerged branches untouched")
    return 0


def message(cwd: Path, ref: str) -> int:
    """The squash-box message: summary, the description, and the Task:
    trailer that survives the squash (task tooling/58)."""
    if "/" not in ref:
        raise JearlessError(f"{ref}: expected PROJECT/ID")
    project, num_raw = ref.split("/", 1)
    try:
        num = int(num_raw)
    except ValueError as exc:
        raise JearlessError(f"{ref}: the id must be a number") from exc
    task = next(
        (t for t in registry.load_all(cwd).all() if (t.project, t.id) == (project, num)),
        None,
    )
    if task is None:
        raise JearlessError(f"{project}/{num}: no such task in the registry")
    out = [task.summary]
    if task.description:
        out.append("")
        out.append(task.description.rstrip())
    out.append("")
    out.append(f"Task: {project}/{num}")
    print("\n".join(out))
    return 0
