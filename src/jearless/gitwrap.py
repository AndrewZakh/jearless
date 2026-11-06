"""Git via subprocess: no intermediary libraries, all flags in plain sight.

Rationale in PLAN.md: jearless is about the precise semantics of git,
so git calls must not be hidden behind wrappers like GitPython.
"""

import os
import subprocess
from pathlib import Path

from jearless.errors import JearlessError


class GitError(JearlessError):
    """git exited with a non-zero code."""


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env={**os.environ, **env} if env else None,
    )


def run(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run git; on failure raise GitError with stderr as a single line."""
    proc = _git(args, cwd, env)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise GitError(f"git {' '.join(args)}: {detail}")
    return proc


def out(args: list[str], cwd: Path) -> str:
    return run(args, cwd).stdout.strip()


def lines(args: list[str], cwd: Path) -> list[str]:
    return [ln for ln in run(args, cwd).stdout.splitlines() if ln.strip()]


def is_repo(cwd: Path) -> bool:
    proc = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_commits(cwd: Path) -> bool:
    """A fresh `git init` is a repository without commits: a Phase 0 empty state."""
    proc = _git(["rev-parse", "--verify", "--quiet", "HEAD"], cwd)
    return proc.returncode == 0


def remote_heads(cwd: Path, remote: str = "origin", pattern: str | None = None) -> dict[str, str]:
    """Branches on the remote — the source of truth about occupancy (README), not a cache."""
    args = ["ls-remote", "--heads", remote]
    if pattern:
        args.append(pattern)
    heads: dict[str, str] = {}
    for ln in lines(args, cwd):
        sha, _, ref = ln.partition("\t")
        heads[ref.removeprefix("refs/heads/")] = sha
    return heads
