import pytest

from jearless import doctor as doctor_mod
from jearless import gitwrap

REGISTRY = "tasks:\n  p:\n    - id: 1\n      summary: a\n"


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def test_clean_repo_passes(repo, capsys):
    assert doctor_mod.run(repo) == 0
    assert "0 finding" in capsys.readouterr().out


def test_squash_commit_is_the_visible_hole(repo, capsys):
    """Phase 2 DoD: a squash commit is highlighted loudly, not lost silently."""
    (repo / "code.py").write_text("print('squashed work')", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "task 16 squashed"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out
    assert "unattributed commit" in out
    assert "task 16 squashed" in out
    assert "squash or fast-forward suspected" in out


def test_registry_edits_are_attributed(repo, capsys):
    (repo / "tasks.yml").write_text(
        REGISTRY + "    - id: 2\n      summary: b\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "one more task"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0


def test_branch_naming_violation(repo, capsys):
    gitwrap.run(["push", "-q", "origin", "main:refs/heads/feature/typo"], repo)
    assert doctor_mod.run(repo) == 1
    assert "'feature/typo'" in capsys.readouterr().out


def test_invalid_registry_reported(repo, capsys):
    # the working tree is sick (a stored status) — doctor reads it before any commit
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      status: available\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    assert "status" in capsys.readouterr().out
