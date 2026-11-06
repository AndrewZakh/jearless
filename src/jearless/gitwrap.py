"""Гит через subprocess: никаких библиотек-посредников, все флаги на виду.

Обоснование — PLAN.md: jearless про точную семантику гита,
поэтому вызовы не прячутся за обёртками вроде GitPython.
"""

import subprocess
from pathlib import Path

from jearless.errors import JearlessError


class GitError(JearlessError):
    """git завершился с ненулевым кодом."""


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Выполнить git, при ошибке — GitError с stderr одной строкой."""
    proc = _git(args, cwd)
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
    """Свежий `git init` — репозиторий, но без коммитов: пустое состояние Ф0."""
    proc = _git(["rev-parse", "--verify", "--quiet", "HEAD"], cwd)
    return proc.returncode == 0


def remote_heads(cwd: Path, remote: str = "origin", pattern: str | None = None) -> dict[str, str]:
    """Ветки на remote — источник истины о занятости (README), не локальный кэш."""
    args = ["ls-remote", "--heads", remote]
    if pattern:
        args.append(pattern)
    heads: dict[str, str] = {}
    for ln in lines(args, cwd):
        sha, _, ref = ln.partition("\t")
        heads[ref.removeprefix("refs/heads/")] = sha
    return heads
