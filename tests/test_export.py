import csv
import io
import json

import pytest

from jearless import export as export_mod
from jearless import forge as forge_mod
from jearless import gitwrap

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
      description: |
        A multiline story:
        line two, with a "quote" and a comma.
      story_points: 2
      depends_on: 2
    - id: 2
      summary: second task
      story_points: 1
    - id: 3
      summary: still open
"""


@pytest.fixture
def repo(origin_and_clone):
    _bare, clone = origin_and_clone
    (clone / ".jearless").mkdir()
    (clone / ".jearless" / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", ".jearless"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    return clone


def _merge(clone, branch, file, content, author, start, end):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / file).write_text(content, encoding="utf-8")
    gitwrap.run(["add", file], clone)
    gitwrap.run(
        ["commit", "-q", "-m", f"work {branch}", "--date", start],
        clone,
        env={"GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": f"{author.lower()}@x"},
    )
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": end},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def _rows_csv(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def test_export_csv_rows_and_quoting(repo, monkeypatch, capsys):
    _merge(repo, "feature/p/2-b", "two.txt", "2", "Bob", "2026-11-03T10:00:00", "2026-11-05T10:00:00")
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-a"], repo)
    (repo / "one.txt").write_text("1", encoding="utf-8")
    gitwrap.run(["add", "one.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "wip one"], repo)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/p/1-a"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)

    assert export_mod.run(repo) == 0
    rows = _rows_csv(capsys.readouterr().out)
    assert rows[0][:3] == ["project", "id", "summary"]
    assert rows[0][-1] == "in_period"
    by_id = {row[1]: row for row in rows[1:]}
    first = by_id["1"]
    assert first[2] == "first task"
    assert 'line two, with a "quote" and a comma.' in first[3]  # multiline survives
    assert first[4] == "2" and first[5] == "p/2"  # points, depends_on (canonical form)
    assert first[8] == "in_progress" and first[9] == "feature/p/1-a"
    assert first[11] != "" and first[12] == ""  # taken, not merged
    assert first[-1] == "true"  # no bounds: everything is in period
    second = by_id["2"]
    assert second[8] == "done" and second[12] == "2026-11-05T10:00:00"
    third = by_id["3"]
    assert third[8] == "available" and third[12] == ""


def test_export_json_shape_and_forge_times(repo, monkeypatch, capsys):
    _merge(repo, "feature/p/2-b", "two.txt", "2", "Bob", "2026-11-03T10:00:00", "2026-11-05T10:00:00")
    monkeypatch.setattr(forge_mod, "pr_times_map", lambda *a, **k: {
        "feature/p/2-b": ("2026-11-03T12:00:00Z", "2026-11-04T12:00:00Z"),
    })
    assert export_mod.run(repo, fmt="json") == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 3
    second = next(r for r in rows if r["id"] == 2)
    assert second["pr_created_at"] == "2026-11-03T12:00:00Z"  # server clocks
    assert second["pr_merged_at"] == "2026-11-04T12:00:00Z"
    assert second["in_period"] is True
    first = next(r for r in rows if r["id"] == 1)
    assert first["pr_merged_at"] is None  # no forge data -> null, not a fake


def test_export_period_marks_in_period(repo, capsys):
    _merge(repo, "feature/p/1-a", "one.txt", "1", "Alice", "2026-11-01T10:00:00", "2026-11-02T10:00:00")
    _merge(repo, "feature/p/2-b", "two.txt", "2", "Bob", "2026-11-03T10:00:00", "2026-11-20T10:00:00")
    assert export_mod.run(repo, from_boundary="2026-11-15") == 0
    rows = {r[1]: r[-1] for r in _rows_csv(capsys.readouterr().out)[1:]}
    assert rows["1"] == "false"  # merged before the window
    assert rows["2"] == "true"   # merged inside
    assert rows["3"] == "false"  # undelivered: never in a delivery period

    capsys.readouterr()
    assert export_mod.run(repo, from_boundary="2026-11-01", to_boundary="2026-11-15") == 0
    rows = {r[1]: r[-1] for r in _rows_csv(capsys.readouterr().out)[1:]}
    assert rows["1"] == "true" and rows["2"] == "false"


def test_export_boundary_task_anchor(repo, capsys):
    """--from p/2 anchors the period at task 2's delivery moment."""
    _merge(repo, "feature/p/2-b", "two.txt", "2", "Bob", "2026-11-03T10:00:00", "2026-11-20T10:00:00")
    assert export_mod.run(repo, from_boundary="p/2") == 0
    rows = {r[1]: r[-1] for r in _rows_csv(capsys.readouterr().out)[1:]}
    assert rows["2"] == "true" and rows["1"] == "false"  # the anchor itself is in


def test_export_boundary_task_not_delivered_refused(repo):
    with pytest.raises(Exception, match="p/3: not delivered"):
        export_mod.run(repo, from_boundary="p/3")


def test_export_boundary_sprint_branch_anchor(repo, capsys):
    """--from sprint-27 anchors at that branch's promotion merge on main."""
    gitwrap.run(["checkout", "-q", "-b", "sprint-27"], repo)
    (repo / "s.txt").write_text("s", encoding="utf-8")
    gitwrap.run(["add", "s.txt"], repo)
    gitwrap.run(["commit", "-q", "-m", "sprint 27 content"], repo)
    gitwrap.run(["push", "-q", "-u", "origin", "sprint-27"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Promote sprint-27 to main", "sprint-27"],
        repo,
        env={"GIT_COMMITTER_DATE": "2026-11-25T09:00:00"},
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert export_mod.run(repo, from_boundary="sprint-27") == 0
    out = capsys.readouterr().out
    rows = {r[1]: r[-1] for r in _rows_csv(out)[1:]}
    assert all(v == "false" for v in rows.values())  # nothing delivered after the promotion


def test_export_output_file(repo, tmp_path, capsys):
    target = tmp_path / "tasks.csv"
    assert export_mod.run(repo, output=str(target)) == 0
    out = capsys.readouterr().out
    assert "3 row(s)" in out and "tasks.csv" in out
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("project,id,summary")


def test_export_requires_remote(repo, monkeypatch):
    def no_fetch(*args, **kwargs):
        raise gitwrap.GitError("no remote")

    monkeypatch.setattr(gitwrap, "run", no_fetch)
    with pytest.raises(Exception, match="cannot fetch"):
        export_mod.run(repo)
