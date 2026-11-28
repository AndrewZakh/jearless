from pathlib import Path

import pytest

from jearless import add as add_mod
from jearless import gitwrap, registry
from jearless.errors import JearlessError
from jearless.registry import RegistryError

MINIMAL = """\
tasks:
  door_design:
    - id: 1
      summary: Paint it black
      story_points: 2
    - id: 2
      summary: Open the door
"""


def test_missing_file_is_empty_state(tmp_path: Path):
    reg = registry.load(tmp_path)
    assert reg.count() == 0
    assert reg.max_id("door_design") == 0


def test_empty_file_is_empty_state(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text("", encoding="utf-8")
    assert registry.load(tmp_path).count() == 0


def test_minimal_registry(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(MINIMAL, encoding="utf-8")
    reg = registry.load(tmp_path)
    assert reg.count() == 2
    assert reg.max_id("door_design") == 2
    first = reg.tasks["door_design"][0]
    assert first.summary == "Paint it black"
    assert first.story_points == 2
    assert first.description == ""


def test_status_field_forbidden(tmp_path: Path):
    # A stored status is a second database; the registry must refuse (README).
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: x\n      status: available\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="status"):
        registry.load(tmp_path)


def test_entry_without_id_rejected(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - summary: no id\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="id"):
        registry.load(tmp_path)


def test_malformed_yaml_rejected(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text("tasks:\n  p: [незакрытая\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        registry.load(tmp_path)


# --- the .jearless/ home (task tooling/15) ---


def test_home_registry_wins(tmp_path: Path):
    (tmp_path / ".jearless").mkdir()
    (tmp_path / ".jearless" / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 7\n      summary: home task\n", encoding="utf-8"
    )
    reg = registry.load(tmp_path)
    assert reg.count() == 1 and reg.tasks["p"][0].summary == "home task"
    assert reg.path == tmp_path / ".jearless" / "tasks.yml"
    assert reg.nudge is False


def test_root_registry_is_the_legacy_fallback(tmp_path: Path, capsys):
    (tmp_path / "tasks.yml").write_text(MINIMAL, encoding="utf-8")
    reg = registry.load(tmp_path)
    assert reg.path == tmp_path / "tasks.yml" and reg.nudge is True
    assert "canonical home" in capsys.readouterr().err  # a warning: stderr, never stdout
    registry.load(tmp_path)  # the nudge prints once per registry path
    assert "canonical home" not in capsys.readouterr().err


def test_two_live_registries_refused(tmp_path: Path):
    (tmp_path / ".jearless").mkdir()
    (tmp_path / ".jearless" / "tasks.yml").write_text(MINIMAL, encoding="utf-8")
    (tmp_path / "tasks.yml").write_text(MINIMAL, encoding="utf-8")
    with pytest.raises(RegistryError, match="two live registries"):
        registry.load(tmp_path)


def test_birth_path_is_the_home(tmp_path: Path):
    reg = registry.load(tmp_path)  # no registry anywhere — not an error
    assert reg.count() == 0
    assert reg.path == tmp_path / ".jearless" / "tasks.yml"


def test_load_all_reads_archives_in_both_homes(tmp_path: Path):
    (tmp_path / "archive_v1.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: root archive\n", encoding="utf-8"
    )
    (tmp_path / ".jearless").mkdir()
    (tmp_path / ".jearless" / "archive_v2.yml").write_text(
        "tasks:\n  p:\n    - id: 2\n      summary: home archive\n", encoding="utf-8"
    )
    reg = registry.load_all(tmp_path)
    assert reg.count() == 2  # both homes feed the union


def test_depends_on_bare_and_cross_project(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n"
        "  p:\n"
        "    - id: 1\n      summary: a\n"
        "    - id: 2\n      summary: b\n      depends_on: [1, other/3]\n",
        encoding="utf-8",
    )
    reg = registry.load(tmp_path)
    assert reg.tasks["p"][1].depends_on == (("p", 1), ("other", 3))


def test_depends_on_invalid_entry_rejected(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      depends_on: p-1\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="depends_on"):
        registry.load(tmp_path)


def test_check_links_unknown_target():
    reg = registry.Registry(
        tasks={"p": [registry.Task("p", 1, "a", depends_on=(("p", 99),))]}
    )
    with pytest.raises(registry.RegistryError, match="no such task"):
        registry.check_links(reg)


def test_check_links_cycle():
    reg = registry.Registry(
        tasks={
            "p": [
                registry.Task("p", 1, "a", depends_on=(("p", 2),)),
                registry.Task("p", 2, "b", depends_on=(("p", 1),)),
            ]
        }
    )
    with pytest.raises(registry.RegistryError, match="cycle"):
        registry.check_links(reg)


def test_check_links_self_reference():
    reg = registry.Registry(tasks={"p": [registry.Task("p", 1, "a", depends_on=(("p", 1),))]})
    with pytest.raises(registry.RegistryError, match="cycle"):
        registry.check_links(reg)


def test_bool_id_refused(tmp_path):
    """task tooling/70: True is an int in Python — the loader refuses it."""
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: true\n      summary: bool id\n", encoding="utf-8"
    )
    with pytest.raises(RegistryError, match="booleans are integers"):
        registry.load_path(tmp_path / "tasks.yml")


def test_story_points_below_one_refused(tmp_path):
    """task tooling/70: negative and zero points refuse."""
    for points in ("-7", "0"):
        (tmp_path / "tasks.yml").write_text(
            f"tasks:\n  p:\n    - id: 1\n      summary: s\n      story_points: {points}\n",
            encoding="utf-8",
        )
        with pytest.raises(RegistryError, match="an integer >= 1"):
            registry.load_path(tmp_path / "tasks.yml")


def test_project_name_validated_on_load(tmp_path):
    """task tooling/70: the contract holds at the trust boundary — on read."""
    (tmp_path / "tasks.yml").write_text(
        'tasks:\n  "Bad/../Name":\n    - id: 1\n      summary: bad\n', encoding="utf-8"
    )
    with pytest.raises(RegistryError, match=r"not a \[a-z0-9_\] name"):
        registry.load_path(tmp_path / "tasks.yml")


def test_cli_points_below_one_refused(origin_and_clone):
    """task tooling/70: --points is validated in the CLI too."""
    _bare, clone = origin_and_clone
    (clone / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: seed\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    with pytest.raises(JearlessError, match="--points must be >= 1"):
        add_mod.add(clone, "p", "a task", points=-5)
