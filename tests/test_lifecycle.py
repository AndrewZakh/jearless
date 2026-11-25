import pytest

from jearless import gitwrap
from jearless import lifecycle as lifecycle_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: seed task
    - id: 2
      summary: the long task
      description: |
        The full story with a **trailer** candidate.
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merged_branch(clone, name):
    gitwrap.run(["checkout", "-q", "-b", name], clone)
    (clone / f"{name.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "work"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{name}'", name], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    # the local branch copy remains — prune's target (the forge deleted origin's)


def test_prune_deletes_merged_local_copies(repo, capsys):
    _merged_branch(repo, "feature/p/2-x")
    assert lifecycle_mod.run_prune(repo) == 0
    out = capsys.readouterr().out
    assert "pruned feature/p/2-x" in out
    assert "1 branch(es) deleted" in out
    names = gitwrap.lines(["branch", "--list"], repo)
    assert not any("feature/p/2-x" in n for n in names)


def test_prune_keeps_unmerged_and_trunk(repo, capsys):
    _merged_branch(repo, "feature/p/2-x")
    gitwrap.run(["checkout", "-q", "-b", "feature/p/3-wip"], repo)
    (repo / "wip.txt").write_text("wip", encoding="utf-8")
    gitwrap.run(["add", "wip.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "wip"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    assert lifecycle_mod.run_prune(repo) == 0
    out = capsys.readouterr().out
    assert "pruned feature/p/2-x" in out
    names = gitwrap.lines(["branch", "--list"], repo)
    assert any("feature/p/3-wip" in n for n in names)  # unmerged: untouched


def test_prune_clean(repo, capsys):
    assert lifecycle_mod.run_prune(repo) == 0
    assert "no local branches fully merged" in capsys.readouterr().out


def test_message_summary_trailer_and_description(repo, capsys):
    assert lifecycle_mod.message(repo, "p/2") == 0
    out = capsys.readouterr().out
    assert out.startswith("the long task\n")
    assert "The full story with a **trailer** candidate." in out
    assert out.rstrip().endswith("Task: p/2")


def test_message_unknown_refused(repo):
    with pytest.raises(JearlessError, match="no such task"):
        lifecycle_mod.message(repo, "p/9")


def test_message_bad_ref_refused(repo):
    with pytest.raises(JearlessError, match="expected PROJECT/ID"):
        lifecycle_mod.message(repo, "p")
