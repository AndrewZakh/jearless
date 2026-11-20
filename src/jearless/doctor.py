"""doctor: the visible hole — unattributed commits, naming violations, a sick registry.

The audit walks the first-parent chain of main: a commit there is attributed
when it is a merge (the branch name is the key) or touches nothing but
sanctioned artifacts — the registry, the changelog, timeline snapshots (README).
Commits that arrived inside a --no-ff merge hang off second parents and are
attributed by that merge. Everything else on the chain is a hole: a squash,
a fast-forward or plain drift.

Accepted holes — scars that cannot be fixed without rewriting history — are
acknowledged in the scar ledger `.jearless/doctor_ignore` (task tooling/31):
one sha per line, each with a cause. Matching is by sha prefix only, so the
ledger can never hide a new violation — only the ones acknowledged by hand.
Ignored findings are still counted aloud ("N accepted scar(s) on the
ledger"); the exit code counts only live findings, so doctor is gate-able.
"""

from pathlib import Path

from jearless import config, gitwrap, registry
from jearless.add import GUIDANCE_HINT
from jearless.errors import JearlessError
from jearless.gitwrap import GitError
from jearless.registry import HOMEDIR, REGISTRY_NAME, RegistryError

LEDGER_NAME = "doctor_ignore"

# The covenant a newborn ledger is born with (the living ledger carries the same lines).
LEDGER_HEADER = (
    "# The scar ledger: accepted holes on main's first-parent chain (task tooling/31).\n"
    "# One sha per line, with the cause. Doctor counts them in the summary instead\n"
    "# of nagging; new sins still scream.\n"
)


def _check_registry(cwd: Path, findings: list[str]) -> None:
    try:
        registry.load(cwd)
    except RegistryError as exc:
        findings.append(f"registry: {exc}")


def _check_links(cwd: Path, findings: list[str]) -> None:
    try:
        reg = registry.load_all(cwd)
    except RegistryError as exc:
        findings.append(f"registry union: {exc}")  # a duplicate key refuses identity (tooling/41)
        return
    try:
        registry.check_links(reg)
    except RegistryError as exc:
        findings.append(f"links: {exc}")


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


# Sanctioned artifacts: bookkeeping, not task work. env.yml version bumps
# normally ride branches via the hook; a direct one is human bookkeeping.
# Markdown is documentation bookkeeping too — the sprint dashboard lives in
# .md chunks (task tooling/13). Accepted price: a docs-only squash is invisible.
# The registry and archives are sanctioned in BOTH homes (task tooling/15).
_H = f"{HOMEDIR}/"
_SANCTIONED_EXACT = frozenset(
    {REGISTRY_NAME, f"{_H}{REGISTRY_NAME}", "CHANGELOG.md", "env.yml", f"{_H}{LEDGER_NAME}"}
)
_SANCTIONED_PREFIXES = (
    "archive_", f"{_H}archive_", "snapshots/", f"{_H}snapshots/",
    f"{_H}reports/", f"{_H}plans/",
)


def _ledger(cwd: Path) -> set[str]:
    """The accepted scars: shas from the ledger, comments and blanks stripped.

    An absent ledger is not an error — a repo without scars needs no file.
    """
    path = cwd / HOMEDIR / LEDGER_NAME
    if not path.exists():
        return set()
    shas: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            shas.add(entry.split()[0])
    return shas


def _is_sanctioned_edit(cwd: Path, sha: str) -> bool:
    files = gitwrap.lines(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], cwd)
    return all(
        f in _SANCTIONED_EXACT
        or f.startswith(_SANCTIONED_PREFIXES)
        or f.endswith(".md")
        for f in files
    )


def _check_unattributed(
    cwd: Path, findings: list[str], remote: str, trunk_ref: str
) -> int:
    """Loud findings per live hole; returns the number of ledger-acknowledged scars."""
    ref = f"{remote}/{trunk_ref}"
    ledger = _ledger(cwd)
    try:
        # first-parent only: WIP that arrived inside a --no-ff merge is attributed
        # by that merge, not audited on its own
        log = gitwrap.out(["log", "--first-parent", ref, "--format=%H%x1f%P%x1f%s"], cwd)
    except GitError:
        findings.append(f"main: no {ref} — nothing to audit yet")
        return 0
    suppressed = 0
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, parents, subject = line.split("\x1f", 2)
        if len(parents.split()) > 1:
            continue  # a merge: attributed by its branch name
        if _is_sanctioned_edit(cwd, sha):
            continue  # a sanctioned human edit: a task, the changelog, a snapshot
        if any(sha.startswith(entry) for entry in ledger):
            suppressed += 1  # on the ledger: counted aloud below, not nagged
            continue
        findings.append(
            f"main: unattributed commit {sha[:7]} \"{subject}\" "
            f"(not a merge, not a registry edit) — squash or fast-forward suspected"
        )
    return suppressed


def run(cwd: Path, remote: str = "origin") -> int:
    findings: list[str] = []
    _check_registry(cwd, findings)
    _check_links(cwd, findings)
    cfg = config.load(cwd)
    _check_branches(cwd, cfg, findings, remote)
    suppressed = _check_unattributed(cwd, findings, remote, cfg.trunk_ref)
    for line in findings:
        print(line)
    if suppressed:
        print(f"{suppressed} accepted scar(s) on the ledger ({HOMEDIR}/{LEDGER_NAME})")
    print(f"doctor: {len(findings)} finding(s)")
    return 1 if findings else 0


def acknowledge(cwd: Path, sha: str, cause: str, remote: str = "origin") -> int:
    """The ledger UX (task tooling/36): validate, require the cause, append, stage.

    The mirror of `reject` (38): a bare acknowledgment is invisible debt. The
    sha must exist on the trunk's first-parent chain — the ledger can only
    acknowledge real commits, never hypothetical ones. The tool edits and
    stages; the human commits (the charter holds).
    """
    cause = cause.strip()
    if not cause:
        raise JearlessError("the cause is required — a bare acknowledgment is invisible debt")
    cfg = config.load(cwd)
    ref = f"{remote}/{cfg.trunk_ref}"
    try:
        chain = gitwrap.out(["log", "--first-parent", ref, "--format=%H"], cwd).split()
    except GitError as exc:
        raise JearlessError(f"no {ref} — nothing to acknowledge against") from exc
    full = next((h for h in chain if h.startswith(sha.strip())), None)
    if full is None:
        raise JearlessError(f"{sha.strip()[:7]}: no such commit on the {ref} first-parent chain")
    ledger_path = cwd / HOMEDIR / LEDGER_NAME
    if any(full.startswith(entry) for entry in _ledger(cwd)):
        raise JearlessError(f"{full[:7]}: already acknowledged")
    if not ledger_path.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(LEDGER_HEADER, encoding="utf-8")
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{full[:7]}  # {cause}\n")
    gitwrap.run(["add", str(ledger_path)], cwd)
    print(f"acknowledged: {full[:7]} — {cause}")
    print(f"ledger: {len(_ledger(cwd))} scar(s) in {HOMEDIR}/{LEDGER_NAME}")
    print("the ledger edit is staged; " + GUIDANCE_HINT)
    return 0
