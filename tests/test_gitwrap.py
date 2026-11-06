from pathlib import Path

import pytest

from jearless import gitwrap
from jearless.gitwrap import GitError


def test_is_repo(empty_repo: Path, tmp_path: Path):
    assert gitwrap.is_repo(empty_repo)
    assert not gitwrap.is_repo(tmp_path)


def test_has_commits_fresh_repo_is_false(empty_repo: Path):
    assert not gitwrap.has_commits(empty_repo)


def test_has_commits_true_after_commit(repo_with_commit: Path):
    assert gitwrap.has_commits(repo_with_commit)


def test_out(repo_with_commit: Path):
    assert gitwrap.out(["symbolic-ref", "--short", "HEAD"], repo_with_commit) == "main"


def test_remote_heads_without_remote_raises(empty_repo: Path):
    with pytest.raises(GitError):
        gitwrap.remote_heads(empty_repo)
