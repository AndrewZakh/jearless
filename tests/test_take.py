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
