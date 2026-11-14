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


def test_merge_arrivals_are_attributed(repo, capsys):
    """WIP that arrived inside a --no-ff merge must not be flagged — only the chain is audited."""
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-thing"], repo)
    (repo / "code.py").write_text("work", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "wip inside the branch"], repo)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/p/1-thing"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-thing'", "feature/p/1-thing"],
        repo,
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0


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


def test_broken_link_is_a_finding(repo, capsys):
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      depends_on: 99\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    assert "links:" in capsys.readouterr().out


def test_link_cycle_is_a_finding(repo, capsys):
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n"
        "    - id: 1\n      summary: a\n      depends_on: 2\n"
        "    - id: 2\n      summary: b\n      depends_on: 1\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out  # one drain: a second readouterr() returns empty
    assert "links:" in out and "cycle" in out


# --- *.md = documentation bookkeeping (task tooling/13) ---


def test_md_only_commit_is_sanctioned(repo, capsys):
    (repo / "NOTES.md").write_text("notes\n", encoding="utf-8")
    gitwrap.run(["add", "NOTES.md"], repo)
    gitwrap.run(["commit", "-q", "-m", "docs: notes"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0  # documentation bookkeeping


def test_md_plus_code_commit_is_flagged(repo, capsys):
    (repo / "NOTES.md").write_text("notes\n", encoding="utf-8")
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    gitwrap.run(["add", "."], repo)
    gitwrap.run(["commit", "-q", "-m", "docs and code mixed"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1  # code inside: still a hole
