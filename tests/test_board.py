import pytest

from jearless import board as board_mod
from jearless import gitwrap
from jearless import take as take_mod

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
      story_points: 2
    - id: 2
      summary: second task
    - id: 3
      summary: third task
    - id: 4
      summary: fourth task
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_task(clone, num: int, slug: str):
    branch = f"feature/p/{num}-{slug}"
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", f"task {num}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_columns_follow_states(repo, capsys):
    take_mod.take(repo, "p", 2)  # in_progress
    _merge_task(repo, 1, "first")  # done (branch stays — override tested)
    assert board_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert out.startswith("kanban")
    assert "available[Available]" in out and "in_progress[In progress]" in out and "done[Done]" in out
    assert "p_1[" in out.split("done[")[1]  # p/1 in the Done column
    assert "p_2[" in out.split("in_progress[")[1].split("done[")[0]
    assert "p_3[" in out.split("available[")[1].split("inprogress[")[0]
    assert "(2 pt)" in out  # points on the card


def test_plan_mode_uses_plan_order_and_shows_unplanned_work(repo, capsys):
    take_mod.take(repo, "p", 1)  # planned below
    take_mod.take(repo, "p", 2)  # NOT planned — unplanned work must still show
    plan_path = repo / ".jearless" / "plans" / "sprint_1.yml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        "plan:\n  goal: x\n  tasks:\n    - task: p/1\n    - task: p/3\n", encoding="utf-8"
    )
    gitwrap.run(["add", str(plan_path)], repo)
    gitwrap.run(["commit", "-q", "-m", "contract"], repo)
    capsys.readouterr()
    assert board_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "%% sprint_1" in out
    # unplanned in-progress work is not hidden
    assert "p_2[" in out.split("in_progress[")[1].split("done[")[0]
    # plan-only available task shows; unplanned available (p/2 is in_progress; nothing else) — p/4 unplanned+available is NOT shown
    assert "p_4[" not in out


def test_fallback_limits_available_by_id(repo, capsys):
    # p/1..p/4 all available; limit 2 keeps the LAST two by id
    assert board_mod.run(repo, show_all=True, limit=2) == 0
    out = capsys.readouterr().out
    assert "%% and 2 more available" in out
    assert "p_4[" in out and "p_3[" in out
    assert "p_1[" not in out and "p_2[" not in out


def test_fallback_limits_done_by_merge_date(repo, capsys):
    _merge_task(repo, 1, "first")
    _merge_task(repo, 2, "second")  # merged later
    _merge_task(repo, 3, "third")  # merged last
    assert board_mod.run(repo, show_all=True, limit=2) == 0
    out = capsys.readouterr().out
    assert "%% and 1 more done" in out
    assert "p_2[" in out.split("done[")[1] and "p_3[" in out.split("done[")[1]
    assert "p_1[" not in out.split("done[")[1]  # the oldest merge is cut


def test_no_plan_is_disclosed(repo, capsys):
    assert board_mod.run(repo) == 0
    assert "%% no plan committed — showing everything" in capsys.readouterr().out


def test_board_requires_remote(repo, monkeypatch):
    monkeypatch.setattr(gitwrap, "run", lambda *a, **k: (_ for _ in ()).throw(
        gitwrap.GitError("no remote")))
    with pytest.raises(Exception, match="cannot fetch"):
        board_mod.run(repo)


def test_missing_explicit_plan_refused(repo):
    with pytest.raises(Exception, match="no such plan file"):
        board_mod.run(repo, plan_path=str(repo / "nope.yml"))
