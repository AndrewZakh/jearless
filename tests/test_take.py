from pathlib import Path

import pytest

from jearless import gitwrap
from jearless import take as take_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  tooling:
    - id: 1
      summary: add a task to the registry
    - id: 2
      summary: Claim a task with a single push
"""


@pytest.fixture
def work(origin_and_clone):
    """A bare origin with a clone carrying a pushed registry on main."""
    bare, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return bare, clone


def test_take_creates_and_pushes_branch(work):
    _, clone = work
    branch = take_mod.take(clone, "tooling", 2)
    assert branch == "feature/tooling/2-claim-a-task-with-a-single-push"
    assert branch in gitwrap.remote_heads(clone)
    # zero commits: the branch points exactly at the main tip
    assert gitwrap.out(["rev-parse", branch], clone) == gitwrap.out(
        ["rev-parse", "origin/main"], clone
    )
    assert gitwrap.out(["symbolic-ref", "--short", "HEAD"], clone) == branch


def test_take_unknown_task(work):
    _, clone = work
    with pytest.raises(JearlessError, match="no task"):
        take_mod.take(clone, "tooling", 99)


def test_race_second_take_gets_taken(work, tmp_path):
    """Phase 1 DoD: two takes against one remote — the second one gets 'taken'."""
    bare, clone = work
    take_mod.take(clone, "tooling", 1)
    rival = tmp_path / "rival"
    gitwrap.run(["clone", "--quiet", str(bare), str(rival)], tmp_path)
    with pytest.raises(JearlessError, match="already taken"):
        take_mod.take(rival, "tooling", 1)
    # no leftover local branch in the rival clone
    local = gitwrap.out(["branch", "--format", "%(refname:short)"], rival)
    assert "feature/tooling/1-add-a-task-to-the-registry" not in local.splitlines()


def test_take_requires_a_remote(empty_repo: Path):
    (empty_repo / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    with pytest.raises(JearlessError, match="remote"):
        take_mod.take(empty_repo, "tooling", 1)


# --- typed take (task tooling/19) ---


def test_take_typed_fix_branch(work):
    _, clone = work
    branch = take_mod.take(clone, "tooling", 1, kind="fix")
    assert branch == "fix/tooling/1-add-a-task-to-the-registry"
    assert branch in gitwrap.remote_heads(clone)  # the declared kind rides the push


def test_take_kind_blocked_across_types(work):
    """Occupancy ignores the kind: one task, one live branch — a fix cannot dodge it."""
    _, clone = work
    take_mod.take(clone, "tooling", 1, kind="fix")
    with pytest.raises(JearlessError, match="already taken"):
        take_mod.take(clone, "tooling", 1)  # the default feature kind


def test_take_rejects_unknown_kind(work):
    _, clone = work
    with pytest.raises(JearlessError, match="kind must be one of"):
        take_mod.take(clone, "tooling", 1, kind="hotfix")  # the auto-hotfix, refused


# --- re-take of a DONE task (task tooling/26) ---


def _merge_done(clone):
    branch = "feature/tooling/1-add-a-task-to-the-registry"
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / "done.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "done.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "task work"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    # the charter lifecycle: merged branches are deleted (forge auto-delete does it too)
    gitwrap.run(["push", "-q", "origin", "--delete", branch], clone)
    gitwrap.run(["branch", "-q", "-D", branch], clone)


def test_take_done_task_refused_without_fix_kind(work):
    """Task tooling/26: a done task re-taken is rework — the kind stays declared."""
    _, clone = work
    _merge_done(clone)
    with pytest.raises(JearlessError, match="re-take requires --type fix"):
        take_mod.take(clone, "tooling", 1)  # the default kind on a done task


def test_take_done_task_with_fix_kind_proceeds(work):
    _, clone = work
    _merge_done(clone)
    branch = take_mod.take(clone, "tooling", 1, kind="fix")
    assert branch == "fix/tooling/1-add-a-task-to-the-registry"
    assert branch in gitwrap.remote_heads(clone)  # the re-take is declared on origin
