import pytest

from jearless import gitwrap
from jearless import take as take_mod
from jearless import timeline as timeline_mod

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_with_dates(clone, branch: str, author: str, committer: str):
    subject = f"Merge branch '{branch}'"
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / "work.txt").write_text(branch, encoding="utf-8")
    gitwrap.run(["add", "work.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", author], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", subject, branch],
        clone,
        env={"GIT_COMMITTER_DATE": committer},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_empty_repo_timeline_is_valid_gantt(repo, capsys):
    assert timeline_mod.run(repo, snapshot="origin/main") == 0
    out = capsys.readouterr().out
    assert out.startswith("gantt") and "section" not in out
    # mermaid tokens, not strftime patterns — %Y in dateFormat would not render
    assert "dateFormat YYYY-MM-DDTHH:mm:ss" in out


def test_snapshot_carries_author_and_committer_dates(repo, capsys):
    """Phase 3 DoD: the snapshot carries the author date of the first own
    commit and the committer date of the merge."""
    _merge_with_dates(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-03T18:00:00")
    gitwrap.run(["tag", "v0.1.0"], repo)
    assert timeline_mod.run(repo, snapshot="v0.1.0") == 0
    out = capsys.readouterr().out
    assert "section p" in out and "first task" in out
    assert "p_1, 2026-11-01T10:00:00, 2026-11-03T18:00:00" in out


def test_times_render_in_utc_regardless_of_recorded_offset(repo, capsys):
    """Task tooling/14's bot catch: a commit recorded in +03 must render in UTC.

    Mixed timezones made an open bar run backwards (local author date vs UTC
    "now" on the runner) — all rendered times are UTC, one clock for the chart.
    """
    _merge_with_dates(repo, "feature/p/1-first", "2026-11-01T10:00:00+03:00", "2026-11-02T10:00:00+03:00")
    gitwrap.run(["tag", "v0.1.0"], repo)
    assert timeline_mod.run(repo, snapshot="v0.1.0") == 0
    out = capsys.readouterr().out
    assert "p_1, 2026-11-01T07:00:00, 2026-11-02T07:00:00" in out


def test_double_merge_one_bar_first_arrival(repo, capsys):
    """Task tooling/11: two merges naming one branch — ONE bar, the first arrival."""
    _merge_with_dates(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    # a second round on the same branch, merged again
    gitwrap.run(["checkout", "-q", "feature/p/1-first"], repo)
    (repo / "work.txt").write_text("second round", encoding="utf-8")
    gitwrap.run(["add", "work.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "second round"], repo)
    gitwrap.run(["push", "-q", "origin", "feature/p/1-first"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-first'", "feature/p/1-first"],
        repo,
        env={"GIT_COMMITTER_DATE": "2026-11-05T10:00:00"},
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert timeline_mod.run(repo, snapshot="origin/main") == 0
    out = capsys.readouterr().out
    assert out.count("p_1,") == 1  # one bar — the duplicate mermaid id would break the render
    assert "p_1, 2026-11-01T10:00:00, 2026-11-02T10:00:00" in out  # the first arrival
    assert "2026-11-05" not in out  # the re-merge is discarded


def test_live_open_bar_and_zero_commit_branch_skipped(repo, capsys):
    _merge_with_dates(repo, "feature/p/1-first", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    take_mod.take(repo, "p", 2)  # zero commits: claimed, no work started — no bar
    capsys.readouterr()
    assert timeline_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "p_1, 2026-11-01T10:00:00" in out  # done bar with real dates
    assert "p_2" not in out  # claimed but no own commits yet
    # work arrives on the taken branch — the bar is born
    (repo / "work2.txt").write_text("wip", encoding="utf-8")
    gitwrap.run(["add", "work2.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", "2026-11-05T09:00:00"], repo)
    gitwrap.run(["push", "-q", "origin", "feature/p/2-second-task"], repo)
    capsys.readouterr()
    timeline_mod.run(repo)
    out = capsys.readouterr().out
    assert "p_2, 2026-11-05T09:00:00" in out
