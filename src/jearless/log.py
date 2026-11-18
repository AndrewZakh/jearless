"""log: the per-task journal — pure provenance (task tooling/34).

The task lifecycle is scattered across branches: the feature branch, fix
re-take branches, the merges into the trunk naming them, the dates.
`jear log <project> <id>` — one command, the full journal: every branch of
the task (any kind), its own commits, the merge dates into the trunk, sorted
oldest first. A retake story reads top to bottom: shipped, then the fix
branch, then that merge. Sources: the trunk's merge history (grep by the
key anchor) + live remote branches matching the key. No state semantics —
pure provenance view.
"""

from pathlib import Path

from jearless import config, gitwrap, registry, state
from jearless.errors import JearlessError

_KINDS = ("feature", "fix", "chore")


def run(cwd: Path, project: str, num: int, remote: str = "origin") -> int:
    cfg = config.load(cwd)
    reg_all = registry.load_all(cwd)
    task = next((t for t in reg_all.all() if (t.project, t.id) == (project, num)), None)
    if task is None:
        raise JearlessError(f"{project}/{num}: no such task in the registry or archives")
    trunk = f"{remote}/{cfg.trunk_ref}"
    marker = f"{project}/{num}-"  # num followed by dash — cannot shadow num+1

    # the merges into the trunk naming this task's branches, oldest first
    merge_lines = gitwrap.lines(
        ["log", trunk, "--merges", f"--grep={marker}", "--reverse",
         "--format=%H%x1f%cd%x1f%s", "--date=short"],
        cwd,
    )
    per_branch: dict[str, list[tuple[str, str, str]]] = {}  # branch -> [(sha, cdate, subject)]
    for line in merge_lines:
        sha, cdate, subject = line.split("\x1f", 2)
        branch = state.branch_from_merge_subject(subject)
        if branch and marker in branch:
            per_branch.setdefault(branch, []).append((sha, cdate, subject))

    # live branches matching the key (not yet merged)
    for name in gitwrap.lines(["branch", "-r", "--format=%(refname:short)"], cwd):
        short = name.removeprefix("origin/")
        kind = short.split("/", 1)[0]
        if kind in _KINDS and marker in short and short not in per_branch:
            per_branch[short] = []  # live, not yet merged

    if not per_branch:
        print(f"{project}/{num} — {task.summary}")
        print("  no branches found: taken nowhere, or the history predates the tool")
        return 0

    branches_sorted = sorted(
        per_branch,
        key=lambda b: per_branch[b][0][1] if per_branch[b] else "",
    )

    print(f"{project}/{num} — {task.summary}")
    for branch in branches_sorted:
        entries = per_branch[branch]
        kind = branch.split("/", 1)[0]
        if entries:
            # the branch's own work = its content at the FIRST merge
            first_sha = entries[0][0]
            own = gitwrap.lines(
                ["log", f"{first_sha}^2", "--not", f"{first_sha}^1",
                 "--format=%h%x1f%ad%x1f%s", "--date=short"],
                cwd,
            )
            print(f"  branch {branch} [{kind}] — {len(entries)} merge(s), {len(own)} own commit(s)")
            for sha, cdate, subject in entries:
                print(f"    merged into the trunk {cdate}: {subject}")
            for line in own:
                sha, adate, subject = line.split("\x1f", 2)
                print(f"      {sha} {adate} {subject}")
        else:
            # live: the branch exists, not yet merged — own commits vs the trunk
            own = gitwrap.lines(
                ["log", branch, "--not", trunk,
                 "--format=%h%x1f%ad%x1f%s", "--date=short"],
                cwd,
            )
            print(f"  branch {branch} [{kind}] — live, not yet merged, {len(own)} own commit(s)")
            for line in own:
                sha, adate, subject = line.split("\x1f", 2)
                print(f"      {sha} {adate} {subject}")
    return 0
