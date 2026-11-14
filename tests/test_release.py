import pytest

from jearless import doctor as doctor_mod
from jearless import gitwrap
from jearless import release as release_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
"""

ENV = "# flow version\nversion: v0.1.0\n"


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    (clone / "env.yml").write_text(ENV, encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _merge_branch(clone, branch: str, committer: str):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "wip", "--date", "2026-11-01T10:00:00"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch],
        clone,
        env={"GIT_COMMITTER_DATE": committer},
    )
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_first_release(repo, capsys):
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    assert release_mod.run(repo) == 0
    assert "released v0.1.0" in capsys.readouterr().out
    assert "refs/tags/v0.1.0" in gitwrap.out(["ls-remote", "--tags", "origin"], repo)
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v0.1.0 (" in text and "- p-1: first task" in text
    snap = (repo / "snapshots" / "timeline-v0.1.0.mmd").read_text(encoding="utf-8")
    assert snap.startswith("%%{init:") and "\ngantt\n" in snap
    assert "p_1, 2026-11-01T10:00:00" in snap
    assert gitwrap.out(["status", "--porcelain"], repo) == ""
    # the release artifacts are sanctioned: doctor stays silent about them
    assert doctor_mod.run(repo) == 0


def test_second_release_prepends_and_respects_range(repo):
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    release_mod.run(repo)
    (repo / "env.yml").write_text("# flow version\nversion: v0.2.0\n", encoding="utf-8")
    gitwrap.run(["add", "env.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "version bump"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00")
    release_mod.run(repo)
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.index("## v0.2.0") < text.index("## v0.1.0")
    assert "- p-2: second task" in text
    v02 = text[: text.index("## v0.1.0")]
    assert "- p-1" not in v02  # the range is v0.1.0..HEAD, not the whole history


def test_dirty_tree_rejected(repo):
    (repo / "junk.txt").write_text("x", encoding="utf-8")
    with pytest.raises(JearlessError, match="dirty"):
        release_mod.run(repo)


def test_duplicate_tag_rejected(repo):
    release_mod.run(repo)
    with pytest.raises(JearlessError, match="already exists"):
        release_mod.run(repo)  # the flow version has not moved since


def test_release_runs_on_main_only(repo):
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-first"], repo)
    with pytest.raises(JearlessError, match="on main"):
        release_mod.run(repo)
