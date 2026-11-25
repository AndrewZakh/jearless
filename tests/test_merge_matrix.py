"""The merge semantics matrix, edge-tested (task tooling/60).

Every row of the manifest matrix, exercised: first-class merges, the octopus
limit, the cherry-pick and fast-forward loud diagnostics.
"""

import pytest

from jearless import doctor as doctor_mod
from jearless import gitwrap
from jearless import state as state_mod


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: seed\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _branch_work(clone, name: str, file: str, content: str):
    gitwrap.run(["checkout", "-q", "-b", name], clone)
    (clone / file).write_text(content, encoding="utf-8")
    gitwrap.run(["add", file], clone)
    gitwrap.run(["commit", "-q", "-m", f"work on {name}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", name], clone)


def test_octopus_subject_is_not_a_single_branch_key():
    assert (
        state_mod.branch_from_merge_subject(
            "Merge branches 'feature/p/1-a' and 'feature/p/2-b'"
        )
        is None
    )


def test_octopus_merge_is_attributed_silently(repo, capsys):
    _branch_work(repo, "feature/p/1-a", "a.txt", "a")
    _branch_work(repo, "feature/p/2-b", "b.txt", "b")
    gitwrap.run(["merge", "feature/p/1-a", "feature/p/2-b", "-m",
                 "Merge branches 'feature/p/1-a' and 'feature/p/2-b'"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0  # a merge is a merge: attributed, silent


def test_cherry_pick_is_loud(repo, capsys):
    _branch_work(repo, "feature/p/1-a", "a.txt", "a")
    gitwrap.run(["checkout", "-q", "main"], repo)
    sha = gitwrap.out(["log", "--format=%H", "-1", "feature/p/1-a"], repo)
    gitwrap.run(["cherry-pick", sha], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out
    assert "unattributed commit" in out and "squash or fast-forward suspected" in out


def test_fast_forward_is_loud(repo, capsys):
    _branch_work(repo, "feature/p/1-a", "a.txt", "a")
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(["merge", "--ff-only", "feature/p/1-a"], repo)  # the forbidden landing
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1
    assert "unattributed commit" in capsys.readouterr().out


def test_branch_naming_finding_carries_a_hint(repo, capsys):
    gitwrap.run(["push", "-q", "origin", "main:refs/heads/feature/typo"], repo)
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out
    assert "rename it to match, or delete it" in out
