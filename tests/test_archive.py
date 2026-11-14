import pytest

from jearless import archive as archive_mod
from jearless import gitwrap, registry
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
      depends_on: 1
    - id: 3
      summary: third task
"""


def _merge_branch(clone, branch: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "wip"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def test_archive_moves_done_as_of_tag(repo, capsys):
    _merge_branch(repo, "feature/p/1-a")
    _merge_branch(repo, "feature/p/2-b")
    gitwrap.run(["tag", "v0.1.0"], repo)
    _merge_branch(repo, "feature/p/3-c")  # done after the tag: stays
    assert archive_mod.run(repo, "v0.1.0") == 0
    out = capsys.readouterr().out
    assert "archived 2 task(s)" in out and "p: 1, 2" in out
    # the archive file is frozen history with the moved entries intact
    text = (repo / "archive_v0.1.0.yml").read_text(encoding="utf-8")
    assert "done as of v0.1.0" in text
    assert "first task" in text and "second task" in text and "depends_on" in text
    # the registry keeps the rest; identity is the union
    reg = registry.load(repo)
    assert [t.id for t in reg.all()] == [3]
    assert registry.load_all(repo).count() == 3  # p/2's link resolves across the union
    # the remaining file stays valid YAML with its structure
    assert registry.load(repo).max_id("p") == 3


def test_second_archive_same_tag_rejected(repo):
    _merge_branch(repo, "feature/p/1-a")
    gitwrap.run(["tag", "v0.1.0"], repo)
    archive_mod.run(repo, "v0.1.0")
    with pytest.raises(JearlessError, match="frozen"):
        archive_mod.run(repo, "v0.1.0")


def test_archive_requires_a_real_tag(repo):
    with pytest.raises(JearlessError, match="no tag"):
        archive_mod.run(repo, "v9.9.9")


def test_archive_nothing_done(repo, capsys):
    gitwrap.run(["tag", "v0.1.0"], repo)  # a tag, but nothing merged yet
    assert archive_mod.run(repo, "v0.1.0") == 0
    assert "nothing done" in capsys.readouterr().out
    assert not (repo / "archive_v0.1.0.yml").exists()


def test_archived_done_tasks_leave_the_sprint(repo, capsys):
    """The board shows the present: archived tasks are not its business anymore."""
    from jearless import sprint as sprint_mod

    _merge_branch(repo, "feature/p/1-a")
    _merge_branch(repo, "feature/p/2-b")
    gitwrap.run(["tag", "v0.1.0"], repo)
    archive_mod.run(repo, "v0.1.0")
    capsys.readouterr()
    assert sprint_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "available (1):" in out and "p/3" in out
    assert "done (0):" in out  # the archived history left the board
    assert "p/1  first task" not in out and "p/2  second task" not in out
    # their branches remain on origin: orphaned, listed as the visible holes
    assert "branches without a registry task (2):" in out
    assert "feature/p/1-a" in out and "feature/p/2-b" in out
