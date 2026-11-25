from datetime import datetime

import pytest

from jearless import gitwrap
from jearless import rhythm as rhythm_mod

COMMITS = [
    ("Alice", "2026-11-16T10:00:00+03:00"),
    ("Alice", "2026-11-16T11:00:00+03:00"),
    ("Bob", "2026-11-20T23:00:00+02:00"),
]


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: seed\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    for i, (who, when) in enumerate(COMMITS, start=2):
        (clone / f"f{i}.txt").write_text("work", encoding="utf-8")
        env = {
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_AUTHOR_NAME": who,
            "GIT_AUTHOR_EMAIL": f"{who.lower()}@x",
        }
        gitwrap.run(["add", f"f{i}.txt"], clone)
        gitwrap.run(["commit", "-q", "-m", f"work {i}"], clone, env=env)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    return clone


def test_team_aggregate_hours_and_weekdays(repo, capsys):
    assert rhythm_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "rhythm: 4 landed commit(s)" in out  # the seed + 3 work commits
    assert "\n   10" in out or "  10" in out  # Alice's local hour (10:00 +03)
    assert "\n   23" in out or "  23" in out  # Bob's local hour (23:00 +02)
    mon = datetime(2026, 11, 16).strftime("%a")
    fri = datetime(2026, 11, 20).strftime("%a")
    assert mon in out and fri in out


def test_per_author_mode_filters(repo, capsys):
    assert rhythm_mod.run(repo, author="Alice") == 0
    out = capsys.readouterr().out
    assert "rhythm: 2 landed commit(s) by 'Alice'" in out
    assert "assignment hints" in out
    assert "never workload evidence" in out


def test_unknown_author(repo, capsys):
    assert rhythm_mod.run(repo, author="Mallory") == 0
    out = capsys.readouterr().out
    assert "no landed commits by 'Mallory'" in out


def test_merges_excluded(repo, capsys):
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-x"], repo)
    (repo / "y.txt").write_text("y", encoding="utf-8")
    gitwrap.run(["add", "y.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "branch work"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-x'", "feature/p/1-x"],
        repo,
    )
    assert rhythm_mod.run(repo) == 0
    assert "4 landed commit(s)" in capsys.readouterr().out  # the merge commit is not counted


def test_week_and_month_cuts(repo, capsys):
    """task tooling/65: the calendar lens — weeks and months."""
    gitwrap.run(["checkout", "-q", "-b", "feature/p/2-b"], repo)
    (repo / "oct.txt").write_text("oct\n", encoding="utf-8")
    env = {
        "GIT_AUTHOR_DATE": "2026-10-20T10:00:00+03:00",
        "GIT_COMMITTER_DATE": "2026-10-20T10:00:00+03:00",
    }
    gitwrap.run(["add", "oct.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "october work"], repo, env=env)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/2-b'", "feature/p/2-b"],
        repo,
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)  # rhythm reads origin/main
    assert rhythm_mod.run(repo) == 0
    out = capsys.readouterr().out
    assert "week" in out and "2026-W43" in out  # Oct 20 = ISO week 43
    assert "month" in out and "2026-10" in out and "2026-11" in out
