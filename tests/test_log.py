import pytest

from jearless import gitwrap
from jearless import log as log_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  tooling:
    - id: 21
      summary: registry race — test two concurrent adds
      story_points: 1
    - id: 22
      summary: never touched
      story_points: 1
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _work_and_merge(clone, branch: str, workfile: str, commits: int, tag_date: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    for i in range(commits):
        (clone / f"{workfile}{i}.txt").write_text(f"work {i}", encoding="utf-8")
        gitwrap.run(["add", "."], clone)
        gitwrap.run(["commit", "-q", "-m", f"work {workfile} {i}"], clone,
                    env={"GIT_COMMITTER_DATE": f"2026-11-{15 + i:02d}T10:00:00"})
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": f"{tag_date}T12:00:00"},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_log_full_retake_story(repo, capsys):
    """Task tooling/34: shipped, then the fix branch, then that merge — one journal."""
    _work_and_merge(repo, "feature/tooling/21-registry-race", "feat", 2, "2026-11-17")
    _work_and_merge(repo, "fix/tooling/21-registry-race-follow-up", "fix", 1, "2026-11-18")
    assert log_mod.run(repo, "tooling", 21) == 0
    out = capsys.readouterr().out
    assert "tooling/21 — registry race — test two concurrent adds" in out
    assert "branch feature/tooling/21-registry-race" in out
    assert "branch fix/tooling/21-registry-race-follow-up" in out
    assert "merged into the trunk 2026-11-17" in out
    assert "merged into the trunk 2026-11-18" in out
    assert "2 own commit(s)" in out
    assert "1 own commit(s)" in out
    # the branches read oldest-first: the feature journal precedes the fix one
    assert out.index("feature/tooling/21") < out.index("fix/tooling/21")


def test_log_live_branch_not_yet_merged(repo, capsys):
    gitwrap.run(["checkout", "-q", "-b", "feature/tooling/22-wip"], repo)
    (repo / "w.txt").write_text("wip", encoding="utf-8")
    gitwrap.run(["add", "."], repo)
    gitwrap.run(["commit", "-q", "-m", "wip"], repo)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/tooling/22-wip"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    assert log_mod.run(repo, "tooling", 22) == 0
    out = capsys.readouterr().out
    assert "branch feature/tooling/22-wip [feature]" in out
    assert "live — not yet merged" in out


def test_log_unknown_task_refused(repo):
    with pytest.raises(JearlessError, match="no such task"):
        log_mod.run(repo, "tooling", 99)
