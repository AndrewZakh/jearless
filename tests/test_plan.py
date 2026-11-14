import pytest

from jearless import gitwrap, plan
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
    - id: 3
      summary: third task
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _write_plan(path, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


PLAN = """\
plan:
  goal: paint the door family
  tasks:
    - task: p/1
      planned: {start: 2026-11-20, end: 2026-11-25}
    - task: p/2
    - task: p/3
"""


def test_valid_plan_review(repo, capsys):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, PLAN)
    gitwrap.run(["add", str(path)], repo)
    gitwrap.run(["commit", "-q", "-m", "sprint 1 contract"], repo)
    assert plan.run(repo, path) == 0
    out = capsys.readouterr().out
    assert "sprint_1: paint the door family" in out
    assert "sprint start: " in out and "git birth" in out
    assert "committed: 3 task(s)" in out and "total: 5 pt" in out  # p/3 has no points — counted as none
    # the file order is the sprint priority: numbered, not sorted
    assert out.index("1. p/1") < out.index("2. p/2") < out.index("3. p/3")
    assert "planned 11-20 → 11-25" in out and "(2 pt)" in out


def test_unborn_plan(repo, capsys):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, PLAN)  # written but not committed
    assert plan.run(repo, path) == 0
    assert "unborn — commit the plan to start the sprint" in capsys.readouterr().out


def test_unknown_id_refuses(repo):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, "plan:\n  tasks:\n    - task: p/99\n")
    with pytest.raises(JearlessError, match="no such task"):
        plan.load_plan(path, registry_for(repo))


def registry_for(repo):
    from jearless import registry

    return registry.load_all(repo)


def test_duplicate_refuses(repo):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, "plan:\n  tasks:\n    - task: p/1\n    - task: p/1\n")
    with pytest.raises(JearlessError, match="planned twice"):
        plan.load_plan(path, registry_for(repo))


def test_end_before_start_refuses(repo):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(
        path,
        "plan:\n  tasks:\n    - task: p/1\n      planned: {start: 2026-11-25, end: 2026-11-20}\n",
    )
    with pytest.raises(JearlessError, match="end before start"):
        plan.load_plan(path, registry_for(repo))


def test_malformed_task_spec_refuses(repo):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, "plan:\n  tasks:\n    - task: p-one\n")
    with pytest.raises(JearlessError, match="project/number"):
        plan.load_plan(path, registry_for(repo))


def test_gantt_renders_dated_and_notes_undated(repo, capsys):
    path = repo / ".jearless" / "plans" / "sprint_1.yml"
    _write_plan(path, PLAN)
    assert plan.run(repo, path, gantt=True) == 0
    out = capsys.readouterr().out
    assert "gantt" in out and "dateFormat YYYY-MM-DD" in out
    assert "p_1, 2026-11-20, 2026-11-25" in out  # the dated window
    assert "%% undated" in out and "p/2" in out  # undated tasks disclosed


def test_next_plan_number(tmp_path):
    assert plan.next_plan_number(tmp_path) == 1
    d = tmp_path / ".jearless" / "plans"
    d.mkdir(parents=True)
    (d / "sprint_1.yml").write_text("plan: {}\n")
    (d / "sprint_3.yml").write_text("plan: {}\n")
    assert plan.next_plan_number(tmp_path) == 4  # max + 1, eternal
