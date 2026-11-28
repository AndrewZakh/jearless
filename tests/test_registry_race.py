"""The registry-edit race (task tooling/21, re-cut for the burst transport —
task tooling/63): a burst of adds rides one branch, and the push race still
arbitrates when two riders collide on the same branch name.

With the reuse rule a sequential burst has no conflict at all: the second
`add` joins the open registry branch and allocates the next free id. The
truly concurrent case — two riders, same branch name, different commits —
is simulated by hand here, and the server arbitrates exactly as before: the
second push is rejected, the stale duplicate is dropped, the registry keeps
every delivered task and no id is reused.
"""

import pytest

import conftest as conftest_helpers
from jearless import add as add_mod
from jearless import forge as forge_module
from jearless import gitwrap, registry
from jearless.gitwrap import GitError

REGISTRY = "tasks:\n  p:\n    - id: 1\n      summary: seed task\n"


@pytest.fixture
def two_clones(tmp_path):
    bare = tmp_path / "origin.git"
    bare.mkdir()
    gitwrap.run(["init", "--quiet", "--bare", "-b", "main"], bare)
    alpha = tmp_path / "alpha"
    alpha.mkdir()
    gitwrap.run(["init", "-q", "-b", "main"], alpha)
    gitwrap.run(["config", "user.email", "test@example.com"], alpha)
    gitwrap.run(["config", "user.name", "Test"], alpha)
    gitwrap.run(["remote", "add", "origin", str(bare)], alpha)
    (alpha / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], alpha)
    gitwrap.run(["commit", "-q", "-m", "registry"], alpha)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], alpha)
    beta = tmp_path / "beta"
    gitwrap.run(["clone", "--quiet", str(bare), str(beta)], tmp_path)
    gitwrap.run(["config", "user.email", "test@example.com"], beta)
    gitwrap.run(["config", "user.name", "Test"], beta)
    return alpha, beta


def test_registry_race_conflict_and_resolution(two_clones, monkeypatch, capsys):
    # this test IS about the ride — restore the real one (the autouse fixture
    # stands it in everywhere else)
    monkeypatch.setattr(forge_module, "add_ride", conftest_helpers.real_add_ride)

    alpha, beta = two_clones

    # alpha takes the lead: id 2 allocated, the ride lands it on registry/p-2
    assert add_mod.add(alpha, "p", "task from alpha") == 2
    assert "registry/p-2" in gitwrap.out(["ls-remote", "--heads", "origin"], alpha)

    # beta, without pulling, builds its own registry/p-2 from its stale main —
    # a concurrent rider with the same branch name and a different commit
    gitwrap.run(["checkout", "-q", "-b", "registry/p-2", "main"], beta)
    (beta / "tasks.yml").write_text(
        REGISTRY + "    - id: 2\n      summary: task from beta\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], beta)
    gitwrap.run(["commit", "-q", "-m", "task from beta"], beta)
    with pytest.raises(GitError, match=r"rejected|fetch first"):
        gitwrap.run(["push", "origin", "registry/p-2"], beta)  # the race arbitrates HERE

    # the resolution: alpha's PR merges first (the forge); beta drops the
    # stale duplicate, pulls the merged registry, re-adds — no id reuse
    gitwrap.run(["checkout", "-q", "main"], alpha)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge pull request #1: registry/p-2", "registry/p-2"],
        alpha,
    )
    gitwrap.run(["push", "-q", "origin", "main"], alpha)
    gitwrap.run(["push", "-q", "origin", "--delete", "registry/p-2"], alpha)  # the forge auto-delete
    gitwrap.run(["checkout", "-q", "main"], beta)
    gitwrap.run(["pull", "--no-rebase", "-q", "origin", "main"], beta)
    gitwrap.run(["branch", "-q", "-D", "registry/p-2"], beta)

    assert add_mod.add(beta, "p", "task from beta, re-added") == 3  # a fresh burst: id 3

    # beta's PR merges (the forge): main gains the re-added task
    gitwrap.run(["fetch", "-q", "origin"], beta)
    gitwrap.run(["checkout", "-q", "main"], beta)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge pull request #2: registry/p-3 (re-added)",
         "origin/registry/p-3"],
        beta,
    )
    gitwrap.run(["push", "-q", "origin", "main"], beta)

    # alpha pulls the resolution: three tasks, ids unique, nothing lost
    gitwrap.run(["pull", "--no-rebase", "-q", "origin", "main"], alpha)
    reg = registry.load_all(alpha)
    assert reg.count() == 3
    assert sorted(t.id for t in reg.all()) == [1, 2, 3]
    summaries = {t.summary for t in reg.all()}
    assert {"seed task", "task from alpha", "task from beta, re-added"} == summaries


def test_sequential_burst_joins_the_open_branch(two_clones, monkeypatch, capsys):
    """The reuse rule (task tooling/63): a sequential burst rides the open
    registry branch — one pull request carries both adds, no conflict, and
    the ids allocate against the ride branch too."""
    monkeypatch.setattr(forge_module, "add_ride", conftest_helpers.real_add_ride)

    alpha, _beta = two_clones
    assert add_mod.add(alpha, "p", "first of the burst") == 2
    assert add_mod.add(alpha, "p", "second of the burst") == 3

    heads = gitwrap.out(["ls-remote", "--heads", "origin"], alpha)
    assert "registry/p-2" in heads and "registry/p-3" not in heads  # ONE branch for the burst
    branch_file = gitwrap.out(["show", "origin/registry/p-2:tasks.yml"], alpha)
    assert "first of the burst" in branch_file and "second of the burst" in branch_file
    # the ride returned to main and the trunk never saw the burst directly
    assert gitwrap.lines(["log", "origin/main", "--merges", "--format=%s"], alpha) == []
