from pathlib import Path

import pytest

from jearless import config
from jearless.config import ConfigError


def test_defaults_without_file(tmp_path: Path):
    cfg = config.load(tmp_path)
    m = cfg.match_branch("feature/door_design/16-paint-it-black")
    assert m is not None
    assert m.group("project") == "door_design"
    assert m.group("num") == "16"
    assert m.group("slug") == "paint-it-black"
    # без слага — тоже валидно; дефисы вместо слэшей — не наш формат
    assert cfg.match_branch("feature/door_design/16") is not None
    assert cfg.match_branch("feature-door_design-16") is None
    assert cfg.sections["feature"] == "Добавлено"


def test_custom_config_overrides(tmp_path: Path):
    # literal-string (одинарные кавычки): TOML не требует экранировать \d
    toml_text = (
        "[branch]\n"
        r"pattern = '^(?P<type>feat)/(?P<project>[a-z]+)/(?P<num>\d+)$'" + "\n"
        "\n"
        "[changelog.sections]\n"
        'feat = "Новые возможности"\n'
    )
    (tmp_path / ".jearless.toml").write_text(toml_text, encoding="utf-8")
    cfg = config.load(tmp_path)
    assert cfg.match_branch("feat/door/1") is not None
    assert cfg.match_branch("feature/door/1") is None
    assert cfg.sections["feat"] == "Новые возможности"
    assert cfg.sections["feature"] == "Добавлено"  # дефолты не затираются


def test_broken_pattern_rejected(tmp_path: Path):
    (tmp_path / ".jearless.toml").write_text('[branch]\npattern = "([a-z"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        config.load(tmp_path)


def test_pattern_without_required_groups_rejected(tmp_path: Path):
    (tmp_path / ".jearless.toml").write_text('[branch]\npattern = "^.*$"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        config.load(tmp_path)
