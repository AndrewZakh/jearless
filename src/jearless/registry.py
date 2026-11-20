"""The eternal task registry tasks.yml: frozen facts only, no live state (README)."""

import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from jearless.config import HOMEDIR
from jearless.errors import JearlessError

REGISTRY_NAME = "tasks.yml"

# Live-state fields are forbidden in the registry: git knows the state (README).
FORBIDDEN_FIELDS = {"status"}

# A dependency link is a frozen authorial fact (the story_points rule, task tooling/12).
_DEP_CROSS_RE = re.compile(r"^([a-z0-9_]+)/(\d+)$")

# The one-line nudge prints once per registry path per process when the legacy
# root home is in use — one hint per command run, no spam across many loads.
_root_nudged: set[str] = set()


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
    rejected: str | None = None  # the withdrawal cause — an authorial decision fact (tooling/38)
    archived: bool = False  # set by load_all for archive-sourced tasks (tooling/40)


@dataclass
class Registry:
    tasks: dict[str, list[Task]] = field(default_factory=dict)
    path: Path | None = None  # the resolved registry file (home, legacy root, or birth)
    nudge: bool = False  # True when the legacy root home is in use

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
    rejected = entry.get("rejected")
    # key presence, not value: a bare `rejected:` (null) is also invisible debt
    if "rejected" in entry and (not isinstance(rejected, str) or not rejected.strip()):
        raise RegistryError(
            f"{where}: 'rejected' present requires a non-empty cause — "
            "a bare rejection is invisible debt"
        )
    return Task(
        project=project,
        id=entry["id"],
        summary=entry["summary"],
        description=description,
        story_points=points,
        depends_on=_parse_depends(project, entry, where),
        rejected=rejected if isinstance(rejected, str) else None,
    )


def load(cwd: Path) -> Registry:
    """One canonical registry (task tooling/15): `.jearless/tasks.yml`, else the
    legacy root file, else the `.jearless/` birth path (add creates it there).

    Both existing is an emergency, not a choice — two live registries are the
    drift disease, so the tool refuses instead of silently picking one.
    """
    home = cwd / HOMEDIR
    home_reg, root_reg = home / REGISTRY_NAME, cwd / REGISTRY_NAME
    if home_reg.exists() and root_reg.exists():
        raise RegistryError(
            f"two live registries: {home_reg} and {root_reg} — pick one;"
            " git mv keeps the history"
        )
    if home_reg.exists():
        reg = load_path(home_reg)
        reg.path, reg.nudge = home_reg, False
        return reg
    if root_reg.exists():
        reg = load_path(root_reg)
        reg.path, reg.nudge = root_reg, True
        if str(root_reg) not in _root_nudged:
            # a warning, not output: it must never pollute a rendered chart
            print(f"jear: the registry lives at the root — the canonical home is {home_reg}",
                  file=sys.stderr)
            _root_nudged.add(str(root_reg))
        return reg
    return Registry(path=home_reg)  # birth: `add` creates the file here


def load_all(cwd: Path) -> Registry:
    """The registry plus every archive: the identity source for the changelog and analytics.

    Archives are read from BOTH homes — frozen files stay where they were born.
    Archive-sourced tasks carry archived=True (task tooling/40): the union is
    identity, but only the working set belongs to the live views.
    """
    combined = load(cwd)
    home = cwd / HOMEDIR
    for path in sorted(set(cwd.glob("archive_*.yml")) | set(home.glob("archive_*.yml"))):
        for project, tasks in load_path(path).tasks.items():
            combined.tasks.setdefault(project, []).extend(
                replace(t, archived=True) for t in tasks
            )
    return combined


def load_path(path: Path) -> Registry:
    if not path.exists():
        return Registry()  # empty state: no registry — not an error
    yaml = YAML(typ="rt")  # round-trip: comments survive future edits
    try:
        data = yaml.load(path)
    except YAMLError as exc:
        raise RegistryError(f"{path.name}: {exc}") from exc
    return from_data(data, path.name)


def from_data(data: object, source: str) -> Registry:
    """Parse already-loaded yaml data into a Registry (used by load_path and
    by report's historical snapshot walk, which reads text out of git)."""
    if data is None:
        return Registry()  # an empty file is also a valid empty state
    if not isinstance(data, dict) or not isinstance(data.get("tasks", {}), dict):
        raise RegistryError(f"{source}: expected the structure 'tasks: <project>: [entries]'")
    registry = Registry()
    for project, entries in data.get("tasks", {}).items():
        if not isinstance(entries, list):
            raise RegistryError(f"{source}: project '{project}' — a list of tasks expected")
        registry.tasks[str(project)] = [
            _task_from_entry(str(project), entry, f"{source}: {project}[{i}]")
            for i, entry in enumerate(entries)
        ]
    return registry


def from_text(text: str, source: str = "<text>") -> Registry:
    """Parse registry yaml text (report's historical snapshot walk)."""
    yaml = YAML(typ="rt")
    try:
        data = yaml.load(text)
    except YAMLError as exc:
        raise RegistryError(f"{source}: {exc}") from exc
    return from_data(data, source)
