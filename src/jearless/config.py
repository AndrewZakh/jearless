"""The .jearless.toml config: the branch regex, the changelog line template, sections."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jearless.errors import JearlessError

CONFIG_NAME = ".jearless.toml"

# Slashes are the structural separators: type/project/number-slug (README).
DEFAULT_BRANCH_PATTERN = (
    r"^(?P<type>[a-z]+)/(?P<project>[a-z0-9_]+)/(?P<num>\d+)(?:-(?P<slug>[a-z0-9-]+))?$"
)
REQUIRED_GROUPS = ("type", "project", "num")
DEFAULT_SECTIONS = {"feature": "Added", "fix": "Fixed"}
DEFAULT_LINE_TEMPLATE = "{project}-{num}: {summary}"


class ConfigError(JearlessError):
    """The config exists but is invalid."""


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
        raise ConfigError(f"branch regex does not compile: {exc}") from exc
    missing = [g for g in REQUIRED_GROUPS if g not in compiled.groupindex]
    if missing:
        raise ConfigError(f"branch regex misses named groups: {', '.join(missing)}")
    return compiled


def load(cwd: Path) -> Config:
    """A missing .jearless.toml is not an error: defaults apply."""
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
