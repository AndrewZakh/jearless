import pytest

from jearless import find as find_mod

REGISTRY = """\
tasks:
  tooling:
    - id: 21
      summary: registry race — test two concurrent adds
      description: |
        The push race between two clones and the pull conflict flow.
      story_points: 1
  door:
    - id: 7
      summary: Paint the door Unbound
      description: |
        The door theme: unbounded colors.
      story_points: 2
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".jearless").mkdir()
    (tmp_path / ".jearless" / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    return tmp_path


def test_find_case_insensitive_across_projects(repo, capsys):
    assert find_mod.run(repo, "unbound") == 0
    out = capsys.readouterr().out
    assert "door/7" in out and "Paint the door Unbound" in out
    assert "1 match(es)" in out


def test_find_matches_description(repo, capsys):
    assert find_mod.run(repo, "pull conflict") == 0
    out = capsys.readouterr().out
    assert "tooling/21" in out and "(1 pt)" in out
    assert "1 match(es)" in out


def test_find_no_matches(repo, capsys):
    assert find_mod.run(repo, "nonexistent-needle") == 0
    assert "no tasks matching 'nonexistent-needle'" in capsys.readouterr().out


def test_find_multiple_matches_sorted(repo, capsys):
    assert find_mod.run(repo, "the") == 0  # both summaries contain "the"
    out = capsys.readouterr().out
    assert out.index("door/7") < out.index("tooling/21")  # sorted by project, id
    assert "2 match(es)" in out
