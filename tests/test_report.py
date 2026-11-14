import pytest

from jearless import gitwrap
from jearless import report as report_mod

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


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone,
                env={"GIT_COMMITTER_DATE": "2026-11-14T11:00:00"})
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_branch(clone, branch: str, who: str, start: str, end: str):
    env = {"GIT_AUTHOR_DATE": start, "GIT_COMMITTER_DATE": start}
    if who:
        env |= {"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": f"{who.lower()}@x"}
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", start], clone, env=env)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": end},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_report_velocity_cycle_rework_attribution(repo, capsys):
    _merge_branch(repo, "feature/p/1-a", "Alice", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    _merge_branch(repo, "feature/p/2-b", "Bob", "2026-11-03T10:00:00", "2026-11-05T10:00:00")
    gitwrap.run(["tag", "v0.1.0"], repo)
    # unplanned: a task born after the plan birth, plus an ad-hoc fix merge
    plan_path = repo / ".jearless" / "plans" / "sprint_1.yml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("plan:\n  goal: next\n  tasks:\n    - task: p/2\n", encoding="utf-8")
    gitwrap.run(["add", str(plan_path)], repo)
    gitwrap.run(["commit", "-q", "-m", "sprint 1 contract"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-14T12:00:00"})
    text = (repo / "tasks.yml").read_text(encoding="utf-8") + "    - id: 3\n      summary: crash fix\n      story_points: 1\n"
    (repo / "tasks.yml").write_text(text, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "one more task"], repo,
                env={"GIT_COMMITTER_DATE": "2026-11-14T13:00:00"})
    _merge_branch(repo, "fix/p/hotfix-crash", "Alice", "2026-11-06T09:00:00", "2026-11-06T10:00:00")
    _merge_branch(repo, "feature/p/3-c", "Alice", "2026-11-06T11:00:00", "2026-11-07T11:00:00")
    gitwrap.run(["tag", "v0.2.0"], repo)

    assert report_mod.run(repo, "v0.2.0") == 0
    out = capsys.readouterr().out
    # velocity: only p/3 shipped since v0.1.0 (first arrival; p/1, p/2 shipped before)
    assert "p: 1 pt" in out
    # cycle time: p/3 lived exactly 24h
    assert "median 24.0h" in out and "p85 24.0h" in out
    assert "client clocks" in out
    # rework: the ad-hoc fix merge counts — 1 fix / 2 merges
    assert "1 fix / 2 merges (50%)" in out
    # scope creep: p/3 born after the plan's birth; p/1, p/2 were born before
    assert "p/3  crash fix" in out and "born 2026-11" in out
    assert "p/1" not in out.split("## Scope creep")[1].split("##")[0]
    # attribution: p/3's branch had only Alice's commits
    assert "p/3 — Alice" in out


def test_prev_tag(repo):
    _merge_branch(repo, "feature/p/1-a", "Alice", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    gitwrap.run(["tag", "v0.1.0"], repo)
    _merge_branch(repo, "feature/p/2-b", "Bob", "2026-11-03T10:00:00", "2026-11-04T10:00:00")
    gitwrap.run(["tag", "v0.2.0"], repo)
    assert report_mod._prev_tag(repo, "v0.2.0") == "v0.1.0"
    assert report_mod._prev_tag(repo, "v0.1.0") is None  # whole history is the range
