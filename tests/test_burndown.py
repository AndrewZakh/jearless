import pytest

from jearless import burndown as burndown_mod
from jearless import gitwrap
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
      story_points: 2
    - id: 2
      summary: second task
      story_points: 3
"""

PLAN = """\
plan:
  goal: the burn
  tasks:
    - task: p/1
      planned: {start: 2026-11-10, end: 2026-11-12}
    - task: p/2
      planned: {start: 2026-11-10, end: 2026-11-13}
"""


def _merge_branch(clone, branch: str, start: str, end: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", start], clone,
                env={"GIT_COMMITTER_DATE": start})
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": end},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone,
                env={"GIT_COMMITTER_DATE": "2026-11-09T10:00:00"})
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _commit_plan(repo, name: str = "sprint_1.yml"):
    path = repo / ".jearless" / "plans" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLAN, encoding="utf-8")
    gitwrap.run(["add", str(path)], repo)
    gitwrap.run(["commit", "-q", "-m", "contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-10T09:00:00"})  # birth = sprint start
    return path


def test_burndown_ideal_steps_and_actual_burn(repo, capsys):
    path = _commit_plan(repo)
    # p/1 lands a day EARLY (planned end 11-12, merged 11-11); p/2 on time (11-13)
    _merge_branch(repo, "feature/p/1-first", "2026-11-11T10:00:00", "2026-11-11T12:00:00")
    _merge_branch(repo, "feature/p/2-second", "2026-11-13T10:00:00", "2026-11-13T12:00:00")
    assert burndown_mod.run(repo, path) == 0
    out = capsys.readouterr().out
    assert "xychart-beta" in out and '"sprint_1 burn-down (planned 5 pt)"' in out
    assert '"2026-11-10"' in out and '"2026-11-13"' in out  # the window: birth -> last planned end
    # ideal steps at the planned ends: 5 -> 3 (p/1 burned on 11-12) -> 0 (p/2 on 11-13)
    assert "line [5, 5, 3, 0, 0" in out
    # actual: p/1 burns a day early on 11-11 (5 -> 3), p/2 on 11-13 (3 -> 0)
    assert "line [5, 3, 3, 0" in out
    # actual: p/1 burns on 11-11 (5 -> 3), p/2 on 11-13 (3 -> 0)
    assert "line [5, 3, 3, 0" in out


def test_unborn_plan_refused(repo):
    path = repo / ".jearless" / "plans" / "sprint_9.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLAN, encoding="utf-8")  # written, not committed
    with pytest.raises(JearlessError, match="unborn"):
        burndown_mod.run(repo, path)


def test_undated_plan_degrades_with_disclaimer(repo, capsys):
    path = repo / ".jearless" / "plans" / "sprint_2.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("plan:\n  goal: x\n  tasks:\n    - task: p/1\n", encoding="utf-8")
    gitwrap.run(["add", str(path)], repo)
    gitwrap.run(["commit", "-q", "-m", "undated contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-10T09:00:00"})
    assert burndown_mod.run(repo, path) == 0
    out = capsys.readouterr().out
    assert "%% plan has no dated windows" in out


def test_trend_renders_done_and_planned(repo, capsys):
    path = _commit_plan(repo)
    _merge_branch(repo, "feature/p/1-first", "2026-11-11T10:00:00", "2026-11-11T12:00:00")
    _merge_branch(repo, "feature/p/2-second", "2026-11-13T10:00:00", "2026-11-13T12:00:00")
    assert burndown_mod.run(repo, path, trend=True) == 0
    out = capsys.readouterr().out
    assert "bar [5, 5"[:6] in out or "bar [" in out  # the done bars
    assert "sprint_1" in out
    assert "line [5" in out  # the planned line


def test_trend_partial_completion(repo, capsys):
    """A sprint with only part of its scope merged shows honest done bars."""
    path = _commit_plan(repo)
    _merge_branch(repo, "feature/p/1-first", "2026-11-11T10:00:00", "2026-11-11T12:00:00")
    assert burndown_mod.run(repo, path, trend=True) == 0
    out = capsys.readouterr().out
    assert "bar [2]" in out  # 2 of 5 pt done
    assert "line [5]" in out  # the commitment stands at 5


def test_trend_no_plans(repo):
    with pytest.raises(JearlessError, match="no plans committed"):
        burndown_mod.run(repo, trend=True)
