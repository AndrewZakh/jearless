"""The registry-edit race (task tooling/21): two concurrent `add`s compute the
same id; the second push is rejected; the documented flow closes it.

Branch occupancy is server-arbitrated, registry EDITS are not: both clones
append at the same spot of tasks.yml, the second push is rejected as
non-fast-forward, and `git pull` surfaces a real merge conflict. The
documented resolution (README, Key decisions): keep the winner's entry,
drop your duplicate, commit the merge (no rebase — the charter), then
re-run `add` — it allocates the next free id against the merged registry.
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


def _commit_registry(clone, message: str):
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", message], clone)


def test_registry_race_conflict_and_resolution(two_clones, capsys):
    alpha, beta = two_clones

    # alpha takes the lead: id 2 allocated, committed, pushed
    assert add_mod.add(alpha, "p", "task from alpha") == 2
    _commit_registry(alpha, "add: task from alpha")
    gitwrap.run(["push", "-q", "origin", "main"], alpha)

    # beta, without pulling, allocates the SAME id 2 — the race
    assert add_mod.add(beta, "p", "task from beta") == 2
    _commit_registry(beta, "add: task from beta")

    # the server arbitrates: beta's push is rejected (non-fast-forward —
    # worded "(fetch first)" on a local transport, "[rejected]" on any)
    with pytest.raises(GitError, match=r"\[rejected\]"):
        gitwrap.run(["push", "origin", "main"], beta)

    # a bare `pull` dies first: modern git demands an explicit strategy on
    # divergent branches (rc 128, "specify how to reconcile") — which happens
    # to enforce the charter's "no rebase" for free
    with pytest.raises(GitError, match="divergent"):
        gitwrap.run(["pull", "origin", "main"], beta)

    # the merge pull surfaces the real conflict — both edits touched the same spot
    with pytest.raises(GitError):
        gitwrap.run(["pull", "--no-rebase", "origin", "main"], beta)
    assert "UU tasks.yml" in gitwrap.out(["status", "--porcelain"], beta)

    # the documented resolution: keep the winner's entry, drop your duplicate,
    # commit the merge (a merge commit — no rebase, the charter)
    gitwrap.run(["checkout", "--theirs", "tasks.yml"], beta)  # alpha's version wins
    gitwrap.run(["add", "tasks.yml"], beta)
    gitwrap.run(["commit", "-q", "-m", "merge: alpha's registry wins"], beta)
    gitwrap.run(["push", "-q", "origin", "main"], beta)

    # re-run add: the id allocates against the MERGED registry — no reuse
    assert add_mod.add(beta, "p", "task from beta, re-added") == 3
    _commit_registry(beta, "add: task from beta, re-added")
    gitwrap.run(["push", "-q", "origin", "main"], beta)

    # alpha pulls the resolution: three tasks, ids unique, nothing lost
    gitwrap.run(["pull", "--no-rebase", "-q", "origin", "main"], alpha)
    reg = registry.load_all(alpha)
    assert reg.count() == 3
    assert sorted(t.id for t in reg.all()) == [1, 2, 3]
    summaries = {t.summary for t in reg.all()}
    assert {"seed task", "task from alpha", "task from beta, re-added"} == summaries
