import time
from pathlib import Path

import pytest

from jearless import forge as _forge

_REAL_REGISTRY_PR = _forge.registry_pr
_REAL_ADD_RIDE = _forge.add_ride


def real_registry_pr(cwd, **kwargs):
    """The real ride — for tests that verify the forge flow itself."""
    return _REAL_REGISTRY_PR(cwd, **kwargs)


def real_add_ride(cwd, **kwargs):
    """The real add transport — for tests that verify the burst flow itself."""
    return _REAL_ADD_RIDE(cwd, **kwargs)

from jearless import gitwrap


@pytest.fixture(autouse=True)
def _utc_clock(monkeypatch):
    """One clock for every test: naive git dates are recorded as UTC."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """A fresh repo in a tmp_path subdirectory: tmp_path itself stays a non-repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    gitwrap.run(["init", "-q", "-b", "main"], repo)
    gitwrap.run(["config", "user.email", "test@example.com"], repo)
    gitwrap.run(["config", "user.name", "Test"], repo)
    return repo


@pytest.fixture
def repo_with_commit(empty_repo: Path) -> Path:
    (empty_repo / "base.txt").write_text("base", encoding="utf-8")
    gitwrap.run(["add", "base.txt"], empty_repo)
    gitwrap.run(["commit", "-q", "-m", "init"], empty_repo)
    return empty_repo


@pytest.fixture
def origin_and_clone(tmp_path: Path):
    """A bare origin plus a working clone: take/sprint truth lives on the remote."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    gitwrap.run(["init", "--quiet", "--bare", "-b", "main"], bare)
    clone = tmp_path / "work"
    clone.mkdir()
    gitwrap.run(["init", "-q", "-b", "main"], clone)
    gitwrap.run(["config", "user.email", "test@example.com"], clone)
    gitwrap.run(["config", "user.name", "Test"], clone)
    gitwrap.run(["remote", "add", "origin", str(bare)], clone)
    return bare, clone


@pytest.fixture(autouse=True)
def _forge_manual_mode(monkeypatch):
    """The default transport stand-in (task tooling/53): the 'human' commits
    the staged edit straight to the current branch — the pre-53 manual flow.
    Ride tests override this with the real forge or a PR-mocking fake."""
    def _manual(cwd, files, branch, title, body, label, base, trunk):
        import os

        from jearless import gitwrap

        rel = [os.path.relpath(os.path.join(str(cwd), str(item)), str(cwd)) for item in files]
        gitwrap.run(["add", *rel], cwd)  # the stand-in stages like the real ride does
        gitwrap.run(["commit", "-q", "-m", title, "--", *rel], cwd)
        # and pushes like the real ride does: take and the views read ORIGIN
        branch_now = gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd)
        gitwrap.run(["push", "-q", "origin", branch_now], cwd)
        return True

    def _manual_add(cwd, files, title, project, num, base, trunk, remote, apply_entry, **kwargs):
        import os

        from jearless import gitwrap

        # the stand-in writes and commits on the CURRENT branch — the pre-53
        # manual flow, so tests that read the worktree file keep passing
        rel = [os.path.relpath(os.path.join(str(cwd), str(item)), str(cwd)) for item in files]
        apply_entry(cwd)
        gitwrap.run(["add", *rel], cwd)
        gitwrap.run(["commit", "-q", "-m", title, "--", *rel], cwd)
        gitwrap.run(["push", "-q", "origin", gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd)], cwd)
        return True

    monkeypatch.setattr(_forge, "registry_pr", _manual)
    monkeypatch.setattr(_forge, "add_ride", _manual_add)
