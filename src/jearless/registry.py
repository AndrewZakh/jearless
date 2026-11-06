"""Вечный реестр задач tasks.yml: только замороженные факты, без живого состояния (README)."""

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from jearless.errors import JearlessError

REGISTRY_NAME = "tasks.yml"

# Поля живого состояния в реестре запрещены: состояние знает гит (README).
FORBIDDEN_FIELDS = {"status"}


class RegistryError(JearlessError):
    """tasks.yml есть, но не читается или нарушает контракт."""


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
        raise RegistryError(f"{where}: запись задачи не является отображением")
    for banned in FORBIDDEN_FIELDS:
        if banned in entry:
            raise RegistryError(
                f"{where}: поле '{banned}' запрещено — живое состояние выводится из гита,"
                " а не хранится (README)"
            )
    if "id" not in entry or not isinstance(entry["id"], int) or entry["id"] < 1:
        raise RegistryError(f"{where}: обязательное поле 'id' — целое >= 1")
    if not isinstance(entry.get("summary"), str) or not entry["summary"].strip():
        raise RegistryError(f"{where}: обязательное поле 'summary' — непустая строка")
    description = entry.get("description", "")
    if not isinstance(description, str):
        raise RegistryError(f"{where}: 'description' должно быть строкой")
    points = entry.get("story_points")
    if points is not None and not isinstance(points, int):
        raise RegistryError(f"{where}: 'story_points' должно быть целым")
    return Task(
        project=project,
        id=entry["id"],
        summary=entry["summary"],
        description=description,
        story_points=points,
    )


def load(cwd: Path) -> Registry:
    path = cwd / REGISTRY_NAME
    if not path.exists():
        return Registry()  # пустое состояние: реестра нет — это не ошибка
    yaml = YAML(typ="rt")  # round-trip: комментарии переживут будущие правки
    try:
        data = yaml.load(path)
    except YAMLError as exc:
        raise RegistryError(f"{REGISTRY_NAME}: {exc}") from exc
    if data is None:
        return Registry()  # пустой файл — тоже законное пустое состояние
    if not isinstance(data, dict) or not isinstance(data.get("tasks", {}), dict):
        raise RegistryError(f"{REGISTRY_NAME}: ожидается структура 'tasks: <подпроект>: [записи]'")
    registry = Registry()
    for project, entries in data.get("tasks", {}).items():
        if not isinstance(entries, list):
            raise RegistryError(f"{REGISTRY_NAME}: подпроект '{project}' — ожидается список задач")
        registry.tasks[str(project)] = [
            _task_from_entry(str(project), entry, f"{REGISTRY_NAME}: {project}[{i}]")
            for i, entry in enumerate(entries)
        ]
    return registry
