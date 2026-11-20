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
    """The artifacts land via the release PR; the tag lands at finalize (tooling/51)."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    assert release_mod.run(repo) == 0
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Merge pull request #7: release v0.1.0",
                 "release/v0.1.0"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert release_mod.finalize(repo, "v0.1.0") == 0
    out = capsys.readouterr().out
    # the publish hint (task tooling/23): the release is local until published
    assert "uv build && uv publish" in out
    assert "refs/tags/v0.1.0" in gitwrap.out(["ls-remote", "--tags", "origin"], repo)
    text = gitwrap.out(["show", "main:CHANGELOG.md"], repo)
    assert "## v0.1.0 (" in text and "- p-1: first task" in text
    snap = gitwrap.out(["show", "main:.jearless/snapshots/timeline-v0.1.0.mmd"], repo)
    assert snap.startswith("%%{init:") and "\ngantt\n" in snap
    assert "p_1, 2026-11-01T10:00:00" in snap
    report = gitwrap.out(["show", "main:.jearless/reports/report-v0.1.0.md"], repo)
    assert report.startswith("# Report v0.1.0") and "## Velocity" in report
    assert gitwrap.out(["status", "--porcelain"], repo) == ""
    # the release artifacts are sanctioned: doctor stays silent about them
    assert doctor_mod.run(repo) == 0


def _release(repo, tag):
    """prepare -> PR merge -> finalize, the forge flow (task tooling/51)."""
    release_mod.run(repo, tag=tag)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge pull request #7: release {tag}",
                 f"release/{tag}"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    gitwrap.run(["branch", "-q", "-D", f"release/{tag}"], repo)
    release_mod.finalize(repo, tag)


def test_second_release_prepends_and_respects_range(repo):
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    _release(repo, "v0.1.0")
    (repo / "env.yml").write_text("# flow version\nversion: v0.2.0\n", encoding="utf-8")
    gitwrap.run(["add", "env.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "version bump"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    _merge_branch(repo, "feature/p/2-second", "2026-11-04T10:00:00")
    _release(repo, "v0.2.0")
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.index("## v0.2.0") < text.index("## v0.1.0")
    assert "- p-2: second task" in text
    v02 = text[: text.index("## v0.1.0")]
    assert "- p-1" not in v02  # the range is v0.1.0..HEAD, not the whole history


def test_authored_release_md_is_printed(repo, capsys):
    """Task tooling/30: the authored checklist (.jearless/release.md) is the
    single carrier — the release prints it instead of the fallback line."""
    (repo / ".jearless").mkdir(exist_ok=True)
    (repo / ".jearless" / "release.md").write_text(
        "# our own checklist\nrefresh the dashboard\n", encoding="utf-8"
    )
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    release_mod.run(repo)  # prepare: the checklist belongs to finalize
    capsys.readouterr()
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Merge pull request #7: release v0.1.0",
                 "release/v0.1.0"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert release_mod.finalize(repo, "v0.1.0") == 0
    out = capsys.readouterr().out
    assert "# our own checklist" in out and "refresh the dashboard" in out
    assert "uv build && uv publish" not in out  # the fallback yields to the authored file


def test_dirty_tree_rejected(repo):
    (repo / "junk.txt").write_text("x", encoding="utf-8")
    with pytest.raises(JearlessError, match="dirty"):
        release_mod.run(repo)


def test_duplicate_tag_rejected(repo):
    _release(repo, "v0.1.0")
    with pytest.raises(JearlessError, match="already exists"):
        release_mod.run(repo)  # the flow version has not moved since


def test_release_runs_on_trunk_only(repo):
    """Trunk is configurable (task tooling/33): the check follows cfg.trunk_ref."""
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-first"], repo)
    with pytest.raises(JearlessError, match="on the trunk"):
        release_mod.run(repo)


def test_two_phase_release(repo, monkeypatch, capsys):
    """task tooling/51: prepare rides a branch, finalize tags the merge commit."""
    monkeypatch.setattr(release_mod, "_open_pr", lambda *a, **k: "https://example/pr/1")
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    assert release_mod.run(repo) == 0  # PREPARE
    out = capsys.readouterr().out
    assert "release v0.1.0: artifacts on release/v0.1.0" in out
    assert "--finalize v0.1.0" in out and "https://example/pr/1" in out
    assert gitwrap.out(["symbolic-ref", "--short", "HEAD"], repo) == "main"  # prepare returns to trunk
    assert "refs/tags/v0.1.0" not in gitwrap.out(["ls-remote", "--tags", "origin"], repo)  # no tag yet
    text = gitwrap.out(["show", "release/v0.1.0:CHANGELOG.md"], repo)
    assert "## v0.1.0 (" in text and "- p-1: first task" in text  # artifacts on the branch

    # the PR merges (the forge flow): merge commit + branch deleted
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge pull request #7 from AndrewZakh/release/v0.1.0",
         "release/v0.1.0"],
        repo,
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    gitwrap.run(["branch", "-q", "-D", "release/v0.1.0"], repo)

    assert release_mod.finalize(repo, "v0.1.0") == 0  # FINALIZE
    out = capsys.readouterr().out
    assert "finalized v0.1.0" in out
    tip = gitwrap.out(["rev-parse", "origin/main"], repo)
    # an annotated tag dereferences to its commit via ^{commit}
    assert gitwrap.out(["rev-parse", "v0.1.0^{commit}"], repo) == tip  # the tag IS the merge commit
    assert "refs/tags/v0.1.0" in gitwrap.out(["ls-remote", "--tags", "origin"], repo)
    assert gitwrap.out(["status", "--porcelain"], repo) == ""
    assert doctor_mod.run(repo) == 0  # the artifacts remain sanctioned on main


def test_finalize_requires_landed_artifacts(repo):
    """task tooling/51: finalize before the PR merges refuses — the artifacts
    must exist at the origin tip, not just on the release branch."""
    _merge_branch(repo, "feature/p/1-first", "2026-11-02T10:00:00")
    release_mod.run(repo)  # prepare: the artifacts are on release/v0.1.0, main unchanged
    with pytest.raises(JearlessError, match="merge the release PR first"):
        release_mod.finalize(repo, "v0.1.0")
