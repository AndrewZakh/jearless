"""The registry-edit race (task tooling/21, re-cut for the PR transport —
task tooling/52+53): two concurrent `add`s compute the same id; the ride's
push is rejected (same branch name, different commit); the conflict moves to
the PR merge, and the documented flow closes it.

The push race still arbitrates the CLAIM (same branch name, different sha).
The task-level conflict surfaces at merge time: alpha's PR merges, beta
drops the stale duplicate branch, pulls the merged registry and re-runs
`add` — it allocates the next free id against the merged registry.
"""

import pytest

from jearless import add as add_mod
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
    import conftest as conftest_helpers
    from jearless import forge as forge_module

    # this test IS about the ride — restore the real one (the autouse fixture
    # stands it in everywhere else)
    monkeypatch.setattr(forge_module, "registry_pr", conftest_helpers.real_registry_pr)

    alpha, beta = two_clones

    # alpha takes the lead: id 2 allocated, the ride lands it on registry/p-2
    assert add_mod.add(alpha, "p", "task from alpha") == 2
    assert "registry/p-2" in gitwrap.out(["ls-remote", "--heads", "origin"], alpha)

    # beta, without pulling, allocates the SAME id 2 — the ride's push is
    # rejected: same branch name, different commit; the race arbitrates HERE
    assert add_mod.add(beta, "p", "task from beta") == 2
    with pytest.raises(GitError, match=r"rejected|fetch first"):
        gitwrap.run(["push", "origin", "registry/p-2"], beta)

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

    assert add_mod.add(beta, "p", "task from beta, re-added") == 3

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
