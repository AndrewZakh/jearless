"""The .jearless.toml config: the branch regex, the changelog line template, sections."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jearless import gitwrap
from jearless.errors import JearlessError

CONFIG_NAME = ".jearless.toml"

# Slashes are the structural separators: type/project/number-slug (README).
DEFAULT_BRANCH_PATTERN = (
    r"^(?P<type>[a-z]+)/(?P<project>[a-z0-9_]+)/(?P<num>\d+)(?:-(?P<slug>[a-z0-9-]+))?$"
)
REQUIRED_GROUPS = ("type", "project", "num")
DEFAULT_SECTIONS = {"feature": "Added", "fix": "Fixed"}
DEFAULT_LINE_TEMPLATE = "{project}-{num}: {summary}"
DEFAULT_DUPLICATE_THRESHOLD = 0.6
HOMEDIR = ".jearless"  # canonical home; registry.py re-exports (config is a leaf)
DEFAULT_TRUNK_REF = "main"
DEFAULT_RAG_AGING_DAYS = 3


class ConfigError(JearlessError):
    """The config exists but is invalid."""


@dataclass(frozen=True)
class Config:
    branch_pattern: re.Pattern
    sections: dict[str, str]
    line_template: str
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD
    rag_aging_days: int = DEFAULT_RAG_AGING_DAYS
    integration_ref: str = ""  # e.g. "release-s{n}" — GitFlow mode (task tooling/32); "" = trunk
    trunk_ref: str = DEFAULT_TRUNK_REF  # e.g. "master" (task tooling/33)

    def match_branch(self, name: str) -> re.Match | None:
        return self.branch_pattern.match(name)

    def live_ref(self, cwd: Path, remote: str) -> str:
        """The tip unreleased work forks from. Trunk: origin/<trunk_ref>.
        GitFlow: the integration branch — for a {n} pattern, the NEWEST
        UNPROMOTED family branch (task tooling/67); when every family branch
        is promoted, the trunk. A fixed name stays as-is.

        The resolution is branch-driven, not plan-driven: branches matching
        the pattern speak for themselves. "Is there" is read from the local
        remote refs, not from the remote itself: this function stays free of
        network calls. The live commands fetch first, so for them the answer
        is current. Without a fetch it is as fresh as the last one — the same
        as any other history read.
        """
        if not self.integration_ref:
            return f"{remote}/{self.trunk_ref}"
        if _FAMILY_SLOT in self.integration_ref:
            family = _family_branches(cwd, remote, self.integration_ref)
            if not family:
                return f"{remote}/{self.trunk_ref}"
            return f"{remote}/{family[0][1]}"  # newest first
        return f"{remote}/{self.integration_ref}"

    def integration_refs(self, cwd: Path, remote: str) -> list[str]:
        """Every ref the delivery surfaces are read from: the trunk plus, in
        GitFlow mode, the integration branch. For a {n} pattern that is EVERY
        family branch (task tooling/67) — a sprint forked from the trunk while
        its predecessor is unpromoted would otherwise vanish from done. A
        fixed name stays single. A promoted member adds nothing to the union
        walk (its history is the trunk's), and an empty newborn sprint — a
        branch at the trunk's tip — still counts: it is the active surface,
        not a delivered one."""
        trunk = f"{remote}/{self.trunk_ref}"
        if not self.integration_ref:
            return [trunk]
        if _FAMILY_SLOT in self.integration_ref:
            return [trunk] + [
                f"{remote}/{name}" for _num, name in _family_branches(cwd, remote, self.integration_ref)
            ]
        # a fixed branch that does not exist yet contributes nothing
        names = set(gitwrap.lines(
            ["for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}"], cwd
        ))
        fixed = f"{remote}/{self.integration_ref}"
        return [trunk] + ([fixed] if fixed in names else [])


_FAMILY_SLOT = "{n}"


def _family_branches(cwd: Path, remote: str, pattern: str) -> list[tuple[int, str]]:
    """Every branch matching the {n} pattern, newest first — the {n} slot
    takes digits (task tooling/67). No promotion filter: a promoted member
    adds nothing to a union walk, and an empty newborn sprint must remain
    the fork target."""
    parts = pattern.split(_FAMILY_SLOT)
    rx = re.compile(re.escape(parts[0]) + r"(\d+)" + "".join(re.escape(p) for p in parts[1:]))
    prefix = f"{remote}/"
    family: list[tuple[int, str]] = []
    for name in gitwrap.lines(
        ["for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}"], cwd
    ):
        if not name.startswith(prefix):
            continue
        m = rx.fullmatch(name[len(prefix):])
        if m:
            family.append((int(m.group(1)), name[len(prefix):]))
    return sorted(family, reverse=True)


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
    duplicate = data.get("duplicate", {})
    threshold = duplicate.get("threshold", DEFAULT_DUPLICATE_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
        raise ConfigError("[duplicate] threshold must be a number in (0, 1]")
    rag = data.get("rag", {})
    aging = rag.get("aging_days", DEFAULT_RAG_AGING_DAYS)
    if not isinstance(aging, int) or isinstance(aging, bool) or aging < 1:
        raise ConfigError("[rag] aging_days must be a positive integer")
    git_cfg = data.get("git", {})
    integration_ref = git_cfg.get("integration_ref", "")
    if not isinstance(integration_ref, str):
        raise ConfigError("[git] integration_ref must be a branch-name string")
    if integration_ref and not re.fullmatch(r"[A-Za-z0-9/_.{}-]+", integration_ref):
        raise ConfigError(f"[git] integration_ref: '{integration_ref}' is not a branch name ({{n}} allowed)")
    trunk_ref = git_cfg.get("trunk_ref", DEFAULT_TRUNK_REF)
    if not isinstance(trunk_ref, str) or not re.fullmatch(r"[A-Za-z0-9/_.-]+", trunk_ref):
        raise ConfigError("[git] trunk_ref must be a branch-name string")
    sections = {**DEFAULT_SECTIONS, **changelog.get("sections", {})}
    return Config(
        branch_pattern=_compile_branch_pattern(branch.get("pattern", DEFAULT_BRANCH_PATTERN)),
        sections=sections,
        line_template=changelog.get("line_template", DEFAULT_LINE_TEMPLATE),
        duplicate_threshold=float(threshold),
        rag_aging_days=aging,
        integration_ref=integration_ref,
        trunk_ref=trunk_ref,
    )
