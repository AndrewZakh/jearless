import pytest

from jearless import gitwrap
from jearless import retro as retro_mod

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
"""

PLAN = """\
gantt
    title the contract
    dateFormat YYYY-MM-DDTHH:mm:ss
    axisFormat %d.%m
    section p
    first :p_1, 2026-11-01T09:00:00, 2026-11-02T09:00:00
    someday :p_9, 2026-11-10T09:00:00, 2026-11-11T09:00:00
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_branch(clone, branch: str, author: str, committer: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", author], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": committer},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_retro_join_shift_and_orphans(repo, capsys):
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-03T18:00:00")
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00", "2026-11-04T12:00:00")
    (repo / "plan.md").write_text(PLAN, encoding="utf-8")
    assert retro_mod.run(repo, repo / "plan.md") == 0
    out = capsys.readouterr().out
    assert "retro: plan.md vs actual (1 joined)" in out
    assert "p_1: planned 11-01→11-02, actual 11-01→11-03, end +1d" in out
    assert "plan-only: p_9" in out
    assert "actual-only: p_2 — the work nobody planned" in out


def test_retro_on_time(repo, capsys):
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T09:00:00")
    (repo / "plan.md").write_text(PLAN, encoding="utf-8")
    retro_mod.run(repo, repo / "plan.md")
    assert "p_1: planned 11-01→11-02, actual 11-01→11-02, on time" in capsys.readouterr().out


def test_retro_sub_day_earliness_is_not_a_day(repo, capsys):
    """Finishing 20 minutes early is 'on time', not 'a day early' (timedelta floor trap)."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T08:40:00")
    (repo / "plan.md").write_text(PLAN, encoding="utf-8")
    retro_mod.run(repo, repo / "plan.md")
    assert "actual 11-01→11-02, on time" in capsys.readouterr().out


def test_retro_missing_plan(repo):
    with pytest.raises(Exception, match="cannot read the plan"):
        retro_mod.run(repo, repo / "no-such-plan.md")
