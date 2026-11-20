import pytest

from jearless import gitwrap
from jearless import retro as retro_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
    - id: 3
      summary: third task
"""

PLAN = """\
plan:
  goal: the contract
  tasks:
    - task: p/1
      planned: {start: 2026-11-01, end: 2026-11-02}
    - task: p/3
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


def test_retro_join_shift_plan_only(repo, capsys):
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-03T18:00:00")
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00", "2026-11-04T12:00:00")
    (repo / "sprint_1.yml").write_text(PLAN, encoding="utf-8")
    gitwrap.run(["add", "sprint_1.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "the contract"], repo)  # born: the window opens
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    out = capsys.readouterr().out
    assert "retro: sprint_1.yml vs actual (1 joined)" in out
    # the planned window drifted: actual end is a day late
    assert "p/1: planned 11-01→11-02, actual 11-01→11-03, end +1d" in out
    assert "plan-only: p/3 — not done yet (or never taken)" in out
    # p/2 merged BEFORE the plan's birth: pre-plan history, not a hole
    assert "actual-only: none — the scope held inside the plan's lifetime" in out


def test_retro_actual_only_inside_the_window(repo, capsys):
    """Unplanned work merged after the plan's birth is the visible hole;
    pre-plan merges are history."""
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00", "2026-11-04T12:00:00")
    (repo / "sprint_1.yml").write_text(PLAN, encoding="utf-8")
    gitwrap.run(["add", "sprint_1.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "the contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-05T09:00:00"})
    # an unplanned task, added and merged after the plan's birth
    text = (repo / "tasks.yml").read_text(encoding="utf-8") + "    - id: 4\n      summary: surprise\n"
    (repo / "tasks.yml").write_text(text, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "surprise task"], repo)
    _merge_branch(repo, "feature/p/4-surprise", "2026-11-06T10:00:00", "2026-11-06T11:00:00")
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    out = capsys.readouterr().out
    assert "actual-only: p/4 — the work nobody planned" in out
    assert "actual-only: p/2" not in out  # pre-plan history is not a hole


def test_undated_entry_joins_without_window(repo, capsys):
    """An undated planned entry joins by membership — merged, but no window to judge."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T09:00:00")
    (repo / "sprint_1.yml").write_text(
        "plan:\n  goal: x\n  tasks:\n    - task: p/1\n", encoding="utf-8"
    )
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    assert "p/1: merged 11-02 — no planned window" in capsys.readouterr().out


def test_retro_on_time(repo, capsys):
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T09:00:00")
    (repo / "sprint_1.yml").write_text(PLAN, encoding="utf-8")
    retro_mod.run(repo, repo / "sprint_1.yml")
    assert "p/1: planned 11-01→11-02, actual 11-01→11-02, on time" in capsys.readouterr().out


def test_retro_plan_order_is_the_output_order(repo, capsys):
    """Rows follow the plan's own order — top-down is the sprint priority."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00", "2026-11-05T10:00:00")
    (repo / "sprint_1.yml").write_text(
        "plan:\n  goal: x\n  tasks:\n    - task: p/2\n    - task: p/1\n", encoding="utf-8"
    )
    retro_mod.run(repo, repo / "sprint_1.yml")
    out = capsys.readouterr().out
    assert out.index("p/2") < out.index("p/1")


def test_missing_plan_file_refused(repo):
    with pytest.raises(JearlessError, match="no such plan file"):
        retro_mod.run(repo, repo / "no-such-plan.yml")


def test_malformed_plan_refused(repo):
    (repo / "sprint_1.yml").write_text("tasks:\n  p: [unclosed\n", encoding="utf-8")
    with pytest.raises(JearlessError):
        retro_mod.run(repo, repo / "sprint_1.yml")


def test_planned_entry_without_dates_field_is_undated(repo, capsys):
    """The dates are optional per entry: absent 'planned' = membership only."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T09:00:00")
    (repo / "sprint_1.yml").write_text(
        "plan:\n  goal: x\n  tasks:\n    - task: p/1\n      planned:\n", encoding="utf-8"
    )
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    assert "no planned window" in capsys.readouterr().out


def test_retro_fix_bar_does_not_overwrite_the_join(repo, capsys):
    """Task tooling/26: a fix re-take bar is rework — the join keeps the feature bar."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T09:00:00")
    _merge_branch(repo, "fix/p/1-rework", "2026-11-06T10:00:00", "2026-11-06T12:00:00")
    (repo / "sprint_1.yml").write_text(PLAN, encoding="utf-8")
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    out = capsys.readouterr().out
    assert out.count("p/1:") == 1
    # the join keeps the feature bar: on time; the fix bar is not the planned completion
    assert "p/1: planned 11-01→11-02, actual 11-01→11-02, on time" in out


def test_window_closes_at_next_plan_birth(repo, capsys):
    """task tooling/42: an old retro never picks up the next sprint's unplanned work."""
    (repo / "sprint_1.yml").write_text(PLAN, encoding="utf-8")
    gitwrap.run(["add", "sprint_1.yml"], repo)
    gitwrap.run(
        ["commit", "-q", "-m", "the contract"],
        repo,
        env={"GIT_COMMITTER_DATE": "2026-11-03T08:00:00"},
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    _merge_branch(repo, "feature/p/1-first", "2026-11-04T10:00:00", "2026-11-04T12:00:00")
    _merge_branch(repo, "feature/p/3-third", "2026-11-05T10:00:00", "2026-11-05T12:00:00")
    # sprint_2 is born AFTER the unplanned-in-1 merge (p/2 lands next): the boundary
    plans = repo / ".jearless" / "plans"
    plans.mkdir(parents=True)
    (plans / "sprint_2.yml").write_text(
        "plan:\n  goal: next\n  tasks:\n    - task: p/2\n      planned: {start: 2026-11-07, end: 2026-11-08}\n",
        encoding="utf-8",
    )
    gitwrap.run(["add", ".jearless/plans/sprint_2.yml"], repo)
    gitwrap.run(
        ["commit", "-q", "-m", "sprint_2 born"],
        repo,
        env={"GIT_COMMITTER_DATE": "2026-11-06T08:00:00"},
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    _merge_branch(repo, "feature/p/2-second", "2026-11-07T10:00:00", "2026-11-07T12:00:00")

    # sprint_1: p/2 merged at 11-07 — AFTER sprint_2's birth, out of the window
    assert retro_mod.run(repo, repo / "sprint_1.yml") == 0
    out = capsys.readouterr().out
    assert "window: closes at the next plan's birth (2026-11-06T08:00:00)" in out
    assert "plan@" in out and "history@" in out  # the recount is reproducible
    assert "actual-only: p/2" not in out  # the leak the review caught
    assert "actual-only: none — the scope held inside the plan's lifetime" in out

    # sprint_2 (the latest): window open; its unplanned-in-2 pre-birth work stays out
    assert retro_mod.run(repo, plans / "sprint_2.yml") == 0
    out = capsys.readouterr().out
    assert "window: open — the latest plan" in out
    assert "p/2: planned 11-07" in out  # joined as planned (it owns the window's task)
    assert "actual-only: p/3" not in out  # pre-birth work is not a hole in sprint_2 either


def test_stamp_names_the_version_actually_read(repo, capsys):
    """task tooling/48: the stamp reflects the plan version the retro read —
    a dirty worktree edit is labeled; a committed amendment moves content@."""
    plan_path = repo / "sprint_1.yml"
    plan_path.write_text(PLAN, encoding="utf-8")
    gitwrap.run(["add", "sprint_1.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "the contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-03T08:00:00"})
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    _merge_branch(repo, "feature/p/1-first", "2026-11-04T10:00:00", "2026-11-04T12:00:00")

    assert retro_mod.run(repo, plan_path) == 0
    out = capsys.readouterr().out
    assert "plan@" in out and " (window origin)" in out and "content@" in out
    assert "uncommitted" not in out

    # the review's state 1: a dirty edit at the same HEAD must be visible in the stamp
    plan_path.write_text(PLAN + "    - task: p/2\n", encoding="utf-8")
    assert retro_mod.run(repo, plan_path) == 0
    out = capsys.readouterr().out
    assert "content@worktree (uncommitted edits)" in out
    assert "plan-only: p/2" in out  # the membership truly came from the edited file

    # the review's state 2: after the commit, content@ names the holding commit
    gitwrap.run(["add", "sprint_1.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "amend the contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-05T08:00:00"})
    assert retro_mod.run(repo, plan_path) == 0
    out = capsys.readouterr().out
    assert "uncommitted" not in out
    assert "plan-only: p/2" in out  # the amendment is part of the read membership
