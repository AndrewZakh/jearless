from pathlib import Path

import pytest

from jearless import __version__, cli

ALL_COMMANDS = ["add", "take", "sprint", "changelog", "doctor", "timeline", "retro", "archive"]


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


@pytest.mark.parametrize(
    "argv",
    [
        ["changelog", "--from", "v1.0", "--to", "v1.1", "--dry-run"],
        ["doctor"],
        ["timeline", "--live"],
        ["timeline", "--snapshot", "v1.1"],
        ["retro", "plan.md"],
        ["archive"],
    ],
)
def test_stubs_exit_cleanly(argv, capsys):
    assert cli.main(argv) == 0
    assert "not implemented" in capsys.readouterr().out


def test_sprint_without_remote_fails_cleanly(empty_repo: Path, monkeypatch, capsys):
    """A clean single-line error, not a traceback (the charter for every empty state)."""
    monkeypatch.chdir(empty_repo)
    assert cli.main(["sprint"]) == 1
    assert "cannot fetch" in capsys.readouterr().err
