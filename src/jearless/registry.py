"""The eternal task registry tasks.yml: frozen facts only, no live state (README)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from jearless.errors import JearlessError

REGISTRY_NAME = "tasks.yml"

# Live-state fields are forbidden in the registry: git knows the state (README).
FORBIDDEN_FIELDS = {"status"}

# A dependency link is a frozen authorial fact (the story_points rule, task tooling/12).
_DEP_CROSS_RE = re.compile(r"^([a-z0-9_]+)/(\d+)$")


class RegistryError(JearlessError):
    """tasks.yml exists but cannot be read or violates the contract."""


@dataclass(frozen=True)
class Task:
    project: str
    id: int
    summary: str
    description: str = ""
    story_points: int | None = None
    depends_on: tuple[tuple[str, int], ...] = ()


@dataclass
class Registry:
    tasks: dict[str, list[Task]] = field(default_factory=dict)

    def all(self) -> list[Task]:
        return [t for tasks in self.tasks.values() for t in tasks]

    def count(self) -> int:
        return len(self.all())

    def max_id(self, project: str) -> int:
        return max((t.id for t in self.tasks.get(project, [])), default=0)


def _parse_depends(project: str, entry: dict, where: str) -> tuple[tuple[str, int], ...]:
    """A bare number points inside the same project; 'project/num' crosses projects."""
    raw = entry.get("depends_on")
    if raw is None:
        return ()
    items = raw if isinstance(raw, list) else [raw]
    deps: list[tuple[str, int]] = []
    for item in items:
        if isinstance(item, int) and not isinstance(item, bool):
            deps.append((project, item))
            continue
        if isinstance(item, str):
            m = _DEP_CROSS_RE.match(item.strip())
            if m:
                deps.append((m.group(1), int(m.group(2))))
                continue
        raise RegistryError(
            f"{where}: 'depends_on' entry must be a task number or 'project/number', got {item!r}"
        )
    return tuple(deps)


def parse_dep_spec(project: str, values: list[str]) -> tuple[tuple[str, int], ...]:
    """The CLI-side normalizer for --depends (task tooling/12)."""
    deps: list[tuple[str, int]] = []
    for value in values:
        value = value.strip()
        if value.isdigit():
            deps.append((project, int(value)))
            continue
        m = _DEP_CROSS_RE.match(value)
        if not m:
            raise JearlessError(f"--depends '{value}': expected a task number or project/number")
        deps.append((m.group(1), int(m.group(2))))
    return tuple(deps)


def check_links(reg: Registry) -> None:
    """A broken link is a hole: unknown targets and cycles are refused loudly.

    Doctor reports these as findings instead of crashing; the graph view
    refuses outright — a typo in a frozen fact must be visible, not silent.
    """
    tasks = {(t.project, t.id): t for t in reg.all()}
    for task in tasks.values():
        for dep in task.depends_on:
            if dep not in tasks:
                raise RegistryError(
                    f"{task.project}/{task.id}: depends_on {dep[0]}/{dep[1]}"
                    " — no such task in the registry or archives"
                )
    color: dict[tuple[str, int], int] = dict.fromkeys(tasks, 0)  # 0 white, 1 gray, 2 black

    def visit(key: tuple[str, int], path: list[tuple[str, int]]) -> None:
        color[key] = 1
        for dep in tasks[key].depends_on:
            if color[dep] == 1:
                cycle = path[path.index(dep) :] + [dep]
                names = " -> ".join(f"{p}/{n}" for p, n in cycle)
                raise RegistryError(f"depends_on cycle: {names}")
            if color[dep] == 0:
                visit(dep, path + [dep])
        color[key] = 2

    for key in tasks:
        if color[key] == 0:
            visit(key, [key])


def _task_from_entry(project: str, entry: object, where: str) -> Task:
    if not isinstance(entry, dict):
        raise RegistryError(f"{where}: a task entry is not a mapping")
    for banned in FORBIDDEN_FIELDS:
        if banned in entry:
            raise RegistryError(
                f"{where}: the field '{banned}' is forbidden — live state is derived"
                " from git, not stored (README)"
            )
    if "id" not in entry or not isinstance(entry["id"], int) or entry["id"] < 1:
        raise RegistryError(f"{where}: the field 'id' is required — an integer >= 1")
    if not isinstance(entry.get("summary"), str) or not entry["summary"].strip():
        raise RegistryError(f"{where}: the field 'summary' is required — a non-empty string")
    description = entry.get("description", "")
    if not isinstance(description, str):
        raise RegistryError(f"{where}: 'description' must be a string")
    points = entry.get("story_points")
    if points is not None and not isinstance(points, int):
        raise RegistryError(f"{where}: 'story_points' must be an integer")
    return Task(
        project=project,
        id=entry["id"],
        summary=entry["summary"],
        description=description,
        story_points=points,
        depends_on=_parse_depends(project, entry, where),
    )


def load(cwd: Path) -> Registry:
    return load_path(cwd / REGISTRY_NAME)


def load_all(cwd: Path) -> Registry:
    """The registry plus every archive: the identity source for the changelog and analytics."""
    combined = load(cwd)
    for path in sorted(cwd.glob("archive_*.yml")):
        for project, tasks in load_path(path).tasks.items():
            combined.tasks.setdefault(project, []).extend(tasks)
    return combined


def load_path(path: Path) -> Registry:
    if not path.exists():
        return Registry()  # empty state: no registry — not an error
    yaml = YAML(typ="rt")  # round-trip: comments survive future edits
    try:
        data = yaml.load(path)
    except YAMLError as exc:
        raise RegistryError(f"{path.name}: {exc}") from exc
    if data is None:
        return Registry()  # an empty file is also a valid empty state
    if not isinstance(data, dict) or not isinstance(data.get("tasks", {}), dict):
        raise RegistryError(f"{path.name}: expected the structure 'tasks: <project>: [entries]'")
    registry = Registry()
    for project, entries in data.get("tasks", {}).items():
        if not isinstance(entries, list):
            raise RegistryError(f"{path.name}: project '{project}' — a list of tasks expected")
        registry.tasks[str(project)] = [
            _task_from_entry(str(project), entry, f"{path.name}: {project}[{i}]")
            for i, entry in enumerate(entries)
        ]
    return registry
