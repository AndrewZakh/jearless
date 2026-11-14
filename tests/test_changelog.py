import pytest

from jearless import changelog as changelog_mod
from jearless import gitwrap

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
    - id: 3
      summary: third task
"""


@pytest.fixture
def history(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_branch(clone, branch: str, subject: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", f"work on {branch}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", subject, branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_both_merge_forms_and_sections(history, capsys):
    clone = history
    _merge_branch(clone, "feature/p/1-first", "Merge branch 'feature/p/1-first'")
    _merge_branch(
        clone, "feature/p/2-second", "Merge pull request #7 from owner/feature/p/2-second"
    )
    _merge_branch(clone, "fix/p/3-third", "Merge branch 'fix/p/3-third'")
    _merge_branch(clone, "docs/readme", "Merge branch 'docs/readme'")  # off-taxonomy
    assert changelog_mod.run(clone) == 0
    out = capsys.readouterr().out
    assert "### Added" in out and "- p-1: first task" in out and "- p-2: second task" in out
    assert "### Fixed" in out and "- p-3: third task" in out
    assert "docs/readme" not in out
    assert "1 off-taxonomy merge(s) skipped" in out


def test_range_by_tag_and_header(history, capsys):
    clone = history
    _merge_branch(clone, "feature/p/1-first", "Merge branch 'feature/p/1-first'")
    gitwrap.run(["tag", "v0.1.0"], clone)
    _merge_branch(clone, "feature/p/2-second", "Merge branch 'feature/p/2-second'")
    capsys.readouterr()
    changelog_mod.run(clone, from_tag="v0.1.0")
    out = capsys.readouterr().out
    assert "## Unreleased" in out and "- p-2: second task" in out
    assert "- p-1" not in out
    changelog_mod.run(clone, to_tag="v0.1.0")
    out = capsys.readouterr().out
    assert "## v0.1.0 (" in out and "- p-1: first task" in out
    assert "- p-2" not in out


def test_orphan_falls_back_to_slug(history, capsys):
    _merge_branch(history, "feature/p/99-ghost-task", "Merge branch 'feature/p/99-ghost-task'")
    changelog_mod.run(history)
    assert "- p-99: ghost task" in capsys.readouterr().out


def test_archives_extend_identity(history, capsys):
    (history / "archive_v0.9.yml").write_text(
        "tasks:\n  p:\n    - id: 77\n      summary: archived task\n", encoding="utf-8"
    )
    _merge_branch(history, "feature/p/77-old-thing", "Merge branch 'feature/p/77-old-thing'")
    changelog_mod.run(history)
    assert "- p-77: archived task" in capsys.readouterr().out


# --- double-merge resilience (task tooling/11): merge → restore → merge again ---


def _remerge_branch(clone, branch: str):
    """A second round on the same task branch: extra commit, merged again."""
    gitwrap.run(["checkout", "-q", branch], clone)
    (clone / f"{branch.replace('/', '_')}_more.txt").write_text("second round", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "second round"], clone)
    gitwrap.run(["push", "-q", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_double_merge_single_entry(history, capsys):
    clone = history
    _merge_branch(clone, "feature/p/1-first", "Merge branch 'feature/p/1-first'")
    _remerge_branch(clone, "feature/p/1-first")
    assert changelog_mod.run(clone) == 0
    out = capsys.readouterr().out
    assert out.count("- p-1: first task") == 1  # collapsed, not duplicated
    assert "1 re-merge(s) collapsed" in out  # collapsed aloud


def test_first_merge_predates_range(history, capsys):
    clone = history
    _merge_branch(clone, "feature/p/1-first", "Merge branch 'feature/p/1-first'")
    gitwrap.run(["tag", "v0.1.0"], clone)
    _remerge_branch(clone, "feature/p/1-first")
    capsys.readouterr()
    changelog_mod.run(clone, from_tag="v0.1.0")
    out = capsys.readouterr().out
    assert "- p-1" not in out  # shipped in v0.1.0; the re-merge is not a new entry
    assert "1 re-merge(s) collapsed" in out


def test_single_merge_has_no_remerge_footer(history, capsys):
    _merge_branch(history, "feature/p/1-first", "Merge branch 'feature/p/1-first'")
    changelog_mod.run(history)
    out = capsys.readouterr().out
    assert "- p-1: first task" in out and "re-merge" not in out
