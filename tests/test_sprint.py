import pytest

from jearless import cli, gitwrap
from jearless import sprint as sprint_mod
from jearless import state as state_mod
from jearless import take as take_mod

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


@pytest.fixture
def board(origin_and_clone):
    """A bare origin with three tasks on main: the sprint playground."""
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_task(clone, num: int, slug: str):
    """Walk a task through the full charter: branch, commit, push, --no-ff merge."""
    branch = f"feature/p/{num}-{slug}"
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"task{num}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", f"task{num}.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", f"task {num}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    # the branch is deliberately kept on origin: done must override in_progress


def test_merge_subject_forms():
    assert state_mod.branch_from_merge_subject("Merge branch 'feature/p/1-x'") == "feature/p/1-x"
    assert (
        state_mod.branch_from_merge_subject("Merge pull request #7 from owner/feature/p/1-x")
        == "feature/p/1-x"
    )
    assert state_mod.branch_from_merge_subject("Merge remote-tracking branch 'origin/x'") is None
    assert state_mod.branch_from_merge_subject("task 16 squashed") is None


def test_sprint_three_states(board, capsys):
    take_mod.take(board, "p", 2)  # in_progress
    _merge_task(board, 3, "done-thing")  # done (branch kept — override tested)
    gitwrap.run(["push", "-q", "origin", "main:refs/heads/feature/p/77-ghost"], board)  # orphan
    assert sprint_mod.run(board) == 0
    out = capsys.readouterr().out
    assert "in_progress (1):" in out and "p/2" in out
    assert "after p/1" in out  # the dependency annotation (task tooling/12)
    assert "done (1):" in out and "p/3" in out
    assert "available (1):" in out and "p/1" in out
    assert "feature/p/77-ghost" in out  # the visible orphan


def test_deleting_branch_returns_task_to_available(board, capsys):
    """Phase 1 DoD: drop the branch — the task is available again."""
    take_mod.take(board, "p", 1)
    sprint_mod.run(board)
    assert "in_progress (1):" in capsys.readouterr().out
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/p/1-first-task"], board)
    sprint_mod.run(board)
    out = capsys.readouterr().out
    assert "in_progress (0):" in out
    # p/2 and p/3 were never taken: all three are available again
    assert "available (3):" in out and "p/1" in out


def test_sprint_requires_a_remote(empty_repo, monkeypatch, capsys):
    monkeypatch.chdir(empty_repo)
    with pytest.raises(Exception, match="cannot fetch"):
        sprint_mod.run(empty_repo)


# --- the markdown dashboard (task tooling/13) ---


def test_bare_sprint_stays_pure_print(board):
    assert sprint_mod.run(board) == 0
    assert not (board / "sprint.md").exists()  # peeking never writes


def test_write_creates_dashboard_with_markers_and_stamp(board):
    assert sprint_mod.run(board, write="") == 0  # empty string = the default path
    text = (board / "sprint.md").read_text(encoding="utf-8")
    assert text.startswith("# Sprint")
    assert sprint_mod.CHUNK_BEGIN in text and sprint_mod.CHUNK_END in text
    assert "_generated" in text and "git@" in text
    assert "### available (3)" in text and "- **p/1** — first task" in text
    assert "after p/1" in text  # the depends_on annotation renders too


def test_write_replaces_chunk_preserving_human_text(board):
    sprint_mod.run(board, write="")
    (board / "sprint.md").open("a", encoding="utf-8").write("\n## My notes\nhuman text\n")
    take_mod.take(board, "p", 2)  # the state changes: p/2 goes in_progress
    assert sprint_mod.run(board, write="") == 0
    text = (board / "sprint.md").read_text(encoding="utf-8")
    assert "human text" in text  # untouched
    assert "### in_progress (1)" in text and "`feature/p/2-second-task`" in text


def test_write_noop_leaves_tree_clean(board):
    sprint_mod.run(board, write="")
    before = (board / "sprint.md").read_bytes()
    assert sprint_mod.run(board, write="") == 0
    assert (board / "sprint.md").read_bytes() == before  # byte-identical


def test_write_refuses_a_human_file(board):
    (board / "NOTES.md").write_text("# my notes\nno markers here\n", encoding="utf-8")
    with pytest.raises(Exception, match="never overwritten") as exc:
        sprint_mod.run(board, write="NOTES.md")
    assert (board / "NOTES.md").read_text(encoding="utf-8") == "# my notes\nno markers here\n"
    assert "jear:sprint:begin" in str(exc.value)  # the paste-ready snippet rides the error


def test_write_explicit_path(board):
    assert sprint_mod.run(board, write="dash.md") == 0
    assert (board / "dash.md").exists()
    assert not (board / "sprint.md").exists()  # the default path untouched


def test_sprint_write_cli_wiring(board, monkeypatch):
    monkeypatch.chdir(board)
    assert cli.main(["sprint", "--write", "via-cli.md"]) == 0
    assert (board / "via-cli.md").exists()
