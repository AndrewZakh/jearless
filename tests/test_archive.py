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
    # the archive file is frozen history with the moved entries intact, in the home
    text = (repo / ".jearless" / "archive_v0.1.0.yml").read_text(encoding="utf-8")
    assert "done as of v0.1.0" in text
    assert "first task" in text and "second task" in text and "depends_on" in text
    # the registry keeps the rest; identity is the union
    reg = registry.load(repo)
    assert [t.id for t in reg.all()] == [3]
    assert registry.load_all(repo).count() == 3  # p/2's link resolves across the union
    # the remaining file stays valid YAML with its structure
    assert registry.load(repo).max_id("p") == 3


def test_root_archives_still_count(repo):
    """Frozen archives in the legacy root home stay in the identity union."""
    (repo / "archive_v0.5.0.yml").write_text(
        "tasks:\n  p:\n    - id: 9\n      summary: old archive\n", encoding="utf-8"
    )
    assert registry.load_all(repo).count() == 4  # 3 registry tasks + 1 root archive


def test_second_archive_same_tag_rejected(repo):
    _merge_branch(repo, "feature/p/1-a")
    # the charter lifecycle: the merged branch is deleted — only then is the task quiet
    gitwrap.run(["branch", "-q", "-D", "feature/p/1-a"], repo)
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/p/1-a"], repo)
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
    # their stale branches remain on origin but are no longer "unknown":
    # the union identity knows the archived tasks, so the branches are
    # absorbed — loud orphans exist only for truly unknown taxonomy
    # (task tooling/40; a retake creates a fresh branch and shows in_progress)
    assert "branches without a registry task" not in out
    assert "feature/p/1-a" not in out and "feature/p/2-b" not in out


def test_retake_after_archive_shows_in_progress(repo, capsys):
    """task tooling/40: the review's E2E — merge, tag, archive, take --type fix, on the board."""
    from jearless import config as config_mod
    from jearless import state as state_mod
    from jearless import take as take_mod

    _merge_branch(repo, "feature/p/1-a")
    # the charter lifecycle: the merged branch is deleted — only then is the task quiet
    gitwrap.run(["branch", "-q", "-D", "feature/p/1-a"], repo)
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/p/1-a"], repo)
    gitwrap.run(["tag", "v0.1.0"], repo)
    gitwrap.run(["push", "-q", "origin", "v0.1.0"], repo)
    assert archive_mod.run(repo, "v0.1.0") == 0
    reg = registry.load(repo)
    assert reg.tasks.get("p") and all(t.id != 1 for t in reg.tasks["p"])  # moved out

    # a quiet archived task stays off the working set
    view = state_mod.compute(repo, config_mod.load(repo), registry.load_all(repo))
    assert all(tv.task.id != 1 for tv in view.tasks)

    # feature-kind retake refuses: archived means shipped
    with pytest.raises(JearlessError, match="archived .* --type fix"):
        take_mod.take(repo, "p", 1)

    # the declared rework takes it and the board shows it in progress
    branch = take_mod.take(repo, "p", 1, kind="fix")
    assert branch == "fix/p/1-first-task"
    view = state_mod.compute(repo, config_mod.load(repo), registry.load_all(repo))
    tv = next(tv for tv in view.tasks if tv.task.id == 1)
    assert tv.state == state_mod.IN_PROGRESS and tv.task.archived
