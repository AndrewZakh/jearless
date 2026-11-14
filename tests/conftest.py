import time
from pathlib import Path

import pytest

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
