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
    # Хранимый статус — вторая база данных; реестр обязан отказаться (README).
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: x\n      status: available\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="status"):
        registry.load(tmp_path)


def test_entry_without_id_rejected(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - summary: нет id\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="id"):
        registry.load(tmp_path)


def test_malformed_yaml_rejected(tmp_path: Path):
    (tmp_path / "tasks.yml").write_text("tasks:\n  p: [незакрытая\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        registry.load(tmp_path)
