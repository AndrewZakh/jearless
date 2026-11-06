from pathlib import Path

import pytest

from jearless import add as add_mod
from jearless import gitwrap
from jearless.errors import JearlessError

REGISTRY_WITH_COMMENT = """\
# The eternal registry header comment — must survive the append.
tasks:
  tooling:
    - id: 1
      summary: first
"""


def test_append_preserves_comments_and_style(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(REGISTRY_WITH_COMMENT, encoding="utf-8")
    new_id = add_mod.add(tmp_path, "tooling", "second task", points=2)
    assert new_id == 2
    text = (tmp_path / "tasks.yml").read_text(encoding="utf-8")
    assert "The eternal registry header comment — must survive the append." in text
    assert "    - id: 2\n      summary: second task\n      story_points: 2\n" in text


def test_append_new_project_starts_from_one(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  tooling:\n    - id: 1\n      summary: a\n", encoding="utf-8"
    )
    # numbering is per subproject (README): door_design starts its own sequence
    assert add_mod.add(tmp_path, "door_design", "paint it black") == 1
    text = (tmp_path / "tasks.yml").read_text(encoding="utf-8")
    assert "  door_design:\n    - id: 1\n      summary: paint it black\n" in text


def test_registry_birth_from_template(tmp_path: Path):
    assert add_mod.add(tmp_path, "tooling", "the very first task") == 1
    text = (tmp_path / "tasks.yml").read_text(encoding="utf-8")
    assert text.startswith("# The eternal jearless task registry")
    assert "tasks:" in text


def test_next_id_accounts_for_branches(origin_and_clone):
    _, clone = origin_and_clone
    # the registry on main knows id 2; a branch for id 12 already exists on origin
    (clone / "tasks.yml").write_text(
        "tasks:\n  tooling:\n    - id: 1\n      summary: a\n    - id: 2\n      summary: b\n",
        encoding="utf-8",
    )
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", "main:refs/heads/feature/tooling/12-future-task"], clone)
    assert add_mod.add(clone, "tooling", "c") == 13


def test_offline_falls_back_to_registry(tmp_path: Path, capsys):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 4\n      summary: a\n", encoding="utf-8"
    )
    # not even a git repo: origin is unreachable, the warning goes to stderr
    assert add_mod.add(tmp_path, "p", "b") == 5
    assert "registry only" in capsys.readouterr().err


def test_invalid_project_rejected(tmp_path: Path):
    with pytest.raises(JearlessError, match="project names"):
        add_mod.add(tmp_path, "Bad-Name", "x")
