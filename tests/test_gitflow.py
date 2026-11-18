import pytest

from jearless import changelog as changelog_mod
from jearless import config as config_mod
from jearless import gitwrap
from jearless import registry as registry_mod
from jearless import state as state_mod
from jearless import take as take_mod
from jearless.config import ConfigError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: the feature
      story_points: 2
"""


@pytest.fixture
def gitflow(origin_and_clone):
    _bare, clone = origin_and_clone
    (clone / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "staging"\n', encoding="utf-8"
    )
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", ".jearless.toml"], clone)
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "gitflow config + registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", "main:staging"], clone)
    return clone


def _take_feature(clone):
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-the-feature"], clone)
    (clone / "f.txt").write_text("x", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "the work"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/p/1-the-feature"], clone)


def _integrate_to_staging_and_delete_branch(clone, branch: str):
    """Merge the feature into STAGING (--no-ff), then the forge deletes the branch."""
    gitwrap.run(["fetch", "-q", "origin"], clone)  # the staging push happened on this same clone
    gitwrap.run(["checkout", "-q", "-b", "staging", "origin/staging"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "staging"], clone)
    gitwrap.run(["push", "-q", "origin", "--delete", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)


def test_no_flicker_done_via_staging(gitflow):
    """The core fix (task tooling/32): integrated-then-branch-deleted = DONE, not available."""
    _take_feature(gitflow)
    _integrate_to_staging_and_delete_branch(gitflow, "feature/p/1-the-feature")
    cfg = config_mod.load(gitflow)
    view = state_mod.compute(gitflow, cfg, registry_mod.load(gitflow))
    assert view.tasks[0].state == "done"  # no available-flicker


def test_trunk_mode_still_flickers_without_config(origin_and_clone):
    """The documented trunk behavior: same scenario, no integration_ref — available."""
    _bare, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", "main:staging"], clone)
    _take_feature(clone)
    gitwrap.run(["checkout", "-q", "-b", "staging", "origin/staging"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-the-feature'", "feature/p/1-the-feature"], clone)
    gitwrap.run(["push", "-q", "origin", "staging"], clone)
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/p/1-the-feature"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    view = state_mod.compute(clone, config_mod.load(clone), registry_mod.load(clone))
    assert view.tasks[0].state == "available"  # the trunk honest-flicker, documented


def test_changelog_reads_integration_tip_pre_promotion(gitflow, capsys):
    _take_feature(gitflow)
    gitwrap.run(["fetch", "-q", "origin"], gitflow)
    gitwrap.run(["checkout", "-q", "-b", "staging", "origin/staging"], gitflow)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-the-feature'", "feature/p/1-the-feature"], gitflow)
    gitwrap.run(["push", "-q", "origin", "staging"], gitflow)
    gitwrap.run(["checkout", "-q", "main"], gitflow)
    assert changelog_mod.run(gitflow) == 0
    assert "p-1: the feature" in capsys.readouterr().out  # the unreleased view reads the integration tip


def test_take_forks_from_integration_tip(gitflow):
    branch = take_mod.take(gitflow, "p", 1)  # the fixture already committed the registry
    base = gitwrap.out(["merge-base", "origin/staging", branch], gitflow)
    staging_tip = gitwrap.out(["rev-parse", "origin/staging"], gitflow)
    assert base == staging_tip  # the new task stacks on the integration state


def test_bad_integration_ref_rejected(tmp_path):
    (tmp_path / ".jearless.toml").write_text('[git]\nintegration_ref = "bad ref!"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        config_mod.load(tmp_path)
