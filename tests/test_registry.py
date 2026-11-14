from pathlib import Path

import pytest

from jearless import registry
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
