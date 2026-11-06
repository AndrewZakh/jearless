"""Конфиг .jearless.toml: регекс ветки, шаблон строки чейнджлога, секции."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jearless.errors import JearlessError

CONFIG_NAME = ".jearless.toml"

# Слэши — структурные разделители: тип/подпроект/номер-слаг (README).
DEFAULT_BRANCH_PATTERN = (
    r"^(?P<type>[a-z]+)/(?P<project>[a-z0-9_]+)/(?P<num>\d+)(?:-(?P<slug>[a-z0-9-]+))?$"
)
REQUIRED_GROUPS = ("type", "project", "num")
DEFAULT_SECTIONS = {"feature": "Добавлено", "fix": "Исправлено"}
DEFAULT_LINE_TEMPLATE = "{project}-{num}: {summary}"


class ConfigError(JearlessError):
    """Конфиг есть, но невалиден."""


@dataclass(frozen=True)
class Config:
    branch_pattern: re.Pattern
    sections: dict[str, str]
    line_template: str

    def match_branch(self, name: str) -> re.Match | None:
        return self.branch_pattern.match(name)


def _compile_branch_pattern(pattern: str) -> re.Pattern:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ConfigError(f"регекс ветки не компилируется: {exc}") from exc
    missing = [g for g in REQUIRED_GROUPS if g not in compiled.groupindex]
    if missing:
        raise ConfigError(f"в регексе ветки нет именованных групп: {', '.join(missing)}")
    return compiled


def load(cwd: Path) -> Config:
    """Отсутствие .jearless.toml — не ошибка: работают дефолты."""
    path = cwd / CONFIG_NAME
    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{CONFIG_NAME}: {exc}") from exc
    branch = data.get("branch", {})
    changelog = data.get("changelog", {})
    sections = {**DEFAULT_SECTIONS, **changelog.get("sections", {})}
    return Config(
        branch_pattern=_compile_branch_pattern(branch.get("pattern", DEFAULT_BRANCH_PATTERN)),
        sections=sections,
        line_template=changelog.get("line_template", DEFAULT_LINE_TEMPLATE),
    )
