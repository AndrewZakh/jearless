from pathlib import Path

import pytest

from jearless import __version__, cli

ALL_COMMANDS = [
    "add", "take", "sprint", "changelog", "doctor", "graph", "timeline", "retro", "archive",
    "release",
]


def test_version():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_subcommand_help(command):
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--help"])
    assert exc.value.code == 0


def test_sprint_without_remote_fails_cleanly(empty_repo: Path, monkeypatch, capsys):
    """A clean single-line error, not a traceback (the charter for every empty state)."""
    monkeypatch.chdir(empty_repo)
    assert cli.main(["sprint"]) == 1
    assert "cannot fetch" in capsys.readouterr().err
