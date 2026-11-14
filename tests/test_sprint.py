import pytest

from jearless import cli, gitwrap
from jearless import sprint as sprint_mod
from jearless import state as state_mod
from jearless import take as take_mod

RAG_PLAN = "plan:\n  goal: rag\n  tasks:\n    - task: p/1\n    - task: p/2\n    - task: p/3\n"

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


def test_double_merge_done_is_set_semantics(board, capsys):
    """Task tooling/11: sprint is expected safe — done is a set, a re-merge adds nothing."""
    _merge_task(board, 1, "first-task")
    gitwrap.run(["checkout", "-q", "feature/p/1-first-task"], board)
    (board / "extra.txt").write_text("second round", encoding="utf-8")
    gitwrap.run(["add", "extra.txt"], board)
    gitwrap.run(["commit", "-q", "-m", "second round"], board)
    gitwrap.run(["push", "-q", "origin", "feature/p/1-first-task"], board)
    gitwrap.run(["checkout", "-q", "main"], board)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-first-task'",
         "feature/p/1-first-task"],
        board,
    )
    gitwrap.run(["push", "-q", "origin", "main"], board)
    assert sprint_mod.run(board) == 0
    assert "done (1):" in capsys.readouterr().out  # not (2)


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


# --- the RAG view (task tooling/18) ---


def _write_rag_plan(board):
    plan_path = board / ".jearless" / "plans" / "sprint_9.yml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(RAG_PLAN, encoding="utf-8")
    return plan_path


def _merge_planned(board, branch: str):
    """Walk a planned task through the charter: branch, commit, push, --no-ff merge."""
    gitwrap.run(["checkout", "-q", "-b", branch], board)
    (board / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], board)
    gitwrap.run(["commit", "-q", "-m", "wip"], board)
    gitwrap.run(["push", "-q", "-u", "origin", branch], board)
    gitwrap.run(["checkout", "-q", "main"], board)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], board)
    gitwrap.run(["push", "-q", "origin", "main"], board)


def test_rag_pending_and_blocked(board, capsys):
    """Nothing taken: p/1 pending; p/2 red — blocked by the undone p/1."""
    plan_path = _write_rag_plan(board)
    assert sprint_mod.run(board, rag=str(plan_path)) == 0
    out = capsys.readouterr().out
    assert "rag (plan sprint_9.yml, aging 3 days):" in out
    assert "PENDING p/1" in out and "not taken" in out
    assert "RED     p/2" in out and "blocked by p/1 (not done)" in out


def test_rag_green_then_done(board, capsys):
    plan_path = _write_rag_plan(board)
    take_mod.take(board, "p", 1)
    (board / "w1.txt").write_text("work", encoding="utf-8")
    gitwrap.run(["add", "w1.txt"], board)
    gitwrap.run(["commit", "-q", "-m", "fresh work"], board)  # no env: born now
    gitwrap.run(["push", "-q", "origin", "feature/p/1-first-task"], board)
    capsys.readouterr()
    assert sprint_mod.run(board, rag=str(plan_path)) == 0
    out = capsys.readouterr().out
    assert "GREEN   p/1" in out and "alive" in out and "(0 days ago)" in out
    # merging makes it done; p/2's block dissolves into pending
    gitwrap.run(["checkout", "-q", "main"], board)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-first-task'",
         "feature/p/1-first-task"],
        board,
    )
    gitwrap.run(["push", "-q", "origin", "main"], board)
    capsys.readouterr()
    assert sprint_mod.run(board, rag=str(plan_path)) == 0
    out = capsys.readouterr().out
    assert "DONE    p/1" in out
    assert "PENDING p/2" in out  # the block dissolved: p/1 is done


def test_rag_yellow_stalled_and_taken(board, capsys):
    from datetime import UTC, datetime, timedelta

    plan_path = _write_rag_plan(board)
    # p/1 merges first: p/2's block dissolves, its own aging becomes visible
    _merge_planned(board, "feature/p/1-first-task")
    take_mod.take(board, "p", 2)
    stale = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
    (board / "w2.txt").write_text("slow", encoding="utf-8")
    gitwrap.run(["add", "w2.txt"], board)
    gitwrap.run(["commit", "-q", "-m", "stalled work"], board,
                env={"GIT_COMMITTER_DATE": stale, "GIT_AUTHOR_DATE": stale})
    gitwrap.run(["push", "-q", "origin", "feature/p/2-second-task"], board)
    take_mod.take(board, "p", 3)  # claimed, zero commits, fresh branch point
    capsys.readouterr()
    assert sprint_mod.run(board, rag=str(plan_path)) == 0
    out = capsys.readouterr().out
    assert "YELLOW  p/2" in out and "stalled" in out and "(10 days ago)" in out
    assert "TAKEN   p/3" in out and "not started" in out  # fresh branch point: not yellow yet


def test_rag_aging_config_turns_yellow_green(board, capsys):
    from datetime import UTC, datetime, timedelta

    (board / ".jearless.toml").write_text("[rag]\naging_days = 30\n", encoding="utf-8")
    plan_path = _write_rag_plan(board)
    _merge_planned(board, "feature/p/1-first-task")
    take_mod.take(board, "p", 2)
    stale = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
    (board / "w2.txt").write_text("slow", encoding="utf-8")
    gitwrap.run(["add", "w2.txt"], board)
    gitwrap.run(["commit", "-q", "-m", "stalled work"], board,
                env={"GIT_COMMITTER_DATE": stale, "GIT_AUTHOR_DATE": stale})
    gitwrap.run(["push", "-q", "origin", "feature/p/2-second-task"], board)
    capsys.readouterr()
    assert sprint_mod.run(board, rag=str(plan_path)) == 0
    out = capsys.readouterr().out
    assert "GREEN   p/2" in out  # 10 days < 30: alive again
    assert "aging 30 days" in out


def test_rag_missing_plan_file_refused(board):
    with pytest.raises(Exception, match="no such plan file"):
        sprint_mod.run(board, rag=str(board / "nope.yml"))
