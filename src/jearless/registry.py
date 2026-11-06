"""The eternal task registry tasks.yml: frozen facts only, no live state (README)."""

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from jearless.errors import JearlessError

REGISTRY_NAME = "tasks.yml"

# Live-state fields are forbidden in the registry: git knows the state (README).
FORBIDDEN_FIELDS = {"status"}


class RegistryError(JearlessError):
    """tasks.yml exists but cannot be read or violates the contract."""


@dataclass(frozen=True)
class Task:
    project: str
    id: int
    summary: str
    description: str = ""
    story_points: int | None = None


@dataclass
class Registry:
    tasks: dict[str, list[Task]] = field(default_factory=dict)

    def all(self) -> list[Task]:
        return [t for tasks in self.tasks.values() for t in tasks]

    def count(self) -> int:
        return len(self.all())

    def max_id(self, project: str) -> int:
        return max((t.id for t in self.tasks.get(project, [])), default=0)


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
    )


def load(cwd: Path) -> Registry:
    return load_path(cwd / REGISTRY_NAME)


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
