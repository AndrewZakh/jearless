"""doctor: the visible hole — unattributed commits, naming violations, a sick registry.

A commit on main is attributed when it is a merge (the branch name is the key)
or touches nothing but the registry (a sanctioned human edit, README).
Everything else is a hole: a squash, a fast-forward or plain drift.
"""

from pathlib import Path

from jearless import config, gitwrap, registry
from jearless.gitwrap import GitError
from jearless.registry import REGISTRY_NAME, RegistryError


def _check_registry(cwd: Path, findings: list[str]) -> None:
    try:
        registry.load(cwd)
    except RegistryError as exc:
        findings.append(f"registry: {exc}")


def _check_branches(cwd: Path, cfg: config.Config, findings: list[str], remote: str) -> None:
    try:
        heads = gitwrap.remote_heads(cwd, remote)
    except GitError:
        findings.append(f"{remote}: unreachable — branch checks skipped")
        return
    known = set(cfg.sections) | {"chore"}
    for name in heads:
        prefix = name.split("/", 1)[0]
        if prefix in known and not cfg.match_branch(name):
            findings.append(f"branch: '{name}' starts like a task branch but misses the pattern")


def _is_registry_edit(cwd: Path, sha: str) -> bool:
    files = gitwrap.lines(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], cwd)
    return all(f == REGISTRY_NAME or f.startswith("archive_") for f in files)


def _check_unattributed(cwd: Path, findings: list[str], remote: str) -> None:
    ref = f"{remote}/main"
    try:
        log = gitwrap.out(["log", ref, "--format=%H%x1f%P%x1f%s"], cwd)
    except GitError:
        findings.append(f"main: no {ref} — nothing to audit yet")
        return
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, parents, subject = line.split("\x1f", 2)
        if len(parents.split()) > 1:
            continue  # a merge: attributed by its branch name
        if _is_registry_edit(cwd, sha):
            continue  # a sanctioned human edit (add a task, fix the registry)
        findings.append(
            f"main: unattributed commit {sha[:7]} \"{subject}\" "
            f"(not a merge, not a registry edit) — squash or fast-forward suspected"
        )


def run(cwd: Path, remote: str = "origin") -> int:
    findings: list[str] = []
    _check_registry(cwd, findings)
    cfg = config.load(cwd)
    _check_branches(cwd, cfg, findings, remote)
    _check_unattributed(cwd, findings, remote)
    for line in findings:
        print(line)
    print(f"doctor: {len(findings)} finding(s)")
    return 1 if findings else 0
