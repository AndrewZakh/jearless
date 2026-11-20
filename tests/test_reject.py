import pytest

from jearless import config as config_mod
from jearless import errors, gitwrap
from jearless import registry as registry_mod
from jearless import reject as reject_mod
from jearless import state as state_mod
from jearless import take as take_mod

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
      story_points: 2
    - id: 2
      summary: second task
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / ".jearless").mkdir()
    (clone / ".jearless" / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", ".jearless/tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _view(repo):
    return state_mod.compute(repo, config_mod.load(repo), registry_mod.load(repo))


def _state_of(repo, num: int) -> str:
    return next(tv.state for tv in _view(repo).tasks if tv.task.id == num)


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


def test_reject_writes_field_and_stages(repo, capsys):
    assert reject_mod.run(repo, "p", 1, "too expensive for the value") == 0
    out = capsys.readouterr().out
    assert "cause: too expensive for the value" in out
    assert "revival" in out  # the reversible-exit is disclosed
    text = (repo / ".jearless" / "tasks.yml").read_text(encoding="utf-8")
    assert "rejected: too expensive for the value" in text
    # the manual-mode stand-in commits like the human would (task tooling/53)
    committed = gitwrap.out(["show", "HEAD:.jearless/tasks.yml"], repo)
    assert "rejected: too expensive for the value" in committed


def test_state_derives_rejected(repo):
    reject_mod.run(repo, "p", 1, "not wanted")
    assert _state_of(repo, 1) == state_mod.REJECTED
    assert _state_of(repo, 2) == state_mod.AVAILABLE  # the sibling is untouched


def test_rejected_wins_over_in_progress(repo):
    take_mod.take(repo, "p", 1)  # live branch on origin
    reject_mod.run(repo, "p", 1, "superseded")
    assert _state_of(repo, 1) == state_mod.REJECTED


def test_rejected_wins_over_done(repo):
    _merge_task(repo, 1, "first")  # merged: done
    assert _state_of(repo, 1) == state_mod.DONE
    reject_mod.run(repo, "p", 1, "shipped, then withdrawn")
    assert _state_of(repo, 1) == state_mod.REJECTED  # the merge stays in history


def test_revival_removing_field_returns_available(repo):
    reject_mod.run(repo, "p", 1, "changed my mind")
    (repo / ".jearless" / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    assert _state_of(repo, 1) == state_mod.AVAILABLE  # git remembers the story


def test_unknown_task_refused(repo):
    with pytest.raises(errors.JearlessError, match="p/9: no such task"):
        reject_mod.run(repo, "p", 9, "cause")


def test_empty_cause_refused(repo):
    with pytest.raises(errors.JearlessError, match="cause is required"):
        reject_mod.run(repo, "p", 1, "   ")
    text = (repo / ".jearless" / "tasks.yml").read_text(encoding="utf-8")
    assert "rejected" not in text  # nothing written on a bare rejection


def test_already_rejected_refused(repo):
    reject_mod.run(repo, "p", 1, "first verdict")
    with pytest.raises(errors.JearlessError, match="already rejected"):
        reject_mod.run(repo, "p", 1, "second verdict")


def test_loader_refuses_bare_rejection(tmp_path):
    (tmp_path / "tasks.yml").write_text(
        """\
tasks:
  p:
    - id: 1
      summary: first task
      rejected:
""",
        encoding="utf-8",
    )
    with pytest.raises(registry_mod.RegistryError, match="requires a non-empty cause"):
        registry_mod.load_path(tmp_path / "tasks.yml")


def test_sprint_shows_rejected_section(repo, capsys):
    from jearless import sprint as sprint_mod

    reject_mod.run(repo, "p", 1, "too expensive")
    capsys.readouterr()
    assert sprint_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "rejected (1):" in out
    assert "p/1" in out.split("rejected (1):")[1]
    assert "[rejected: too expensive]" in out


def test_find_marks_rejected(repo, capsys):
    from jearless import find as find_mod

    reject_mod.run(repo, "p", 1, "not wanted")
    assert find_mod.run(repo, "first task") == 0
    assert "[rejected: not wanted]" in capsys.readouterr().out
