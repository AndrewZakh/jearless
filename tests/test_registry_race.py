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

    # alpha takes the lead: id 2 allocated, the ride lands it on registry/p/2
    assert add_mod.add(alpha, "p", "task from alpha") == 2
    assert "registry/p/2" in gitwrap.out(["ls-remote", "--heads", "origin"], alpha)

    # beta, without pulling, builds its own registry/p/2 from its stale main —
    # a concurrent rider with the same branch name and a different commit
    gitwrap.run(["checkout", "-q", "-b", "registry/p/2", "main"], beta)
    (beta / "tasks.yml").write_text(
        REGISTRY + "    - id: 2\n      summary: task from beta\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], beta)
    gitwrap.run(["commit", "-q", "-m", "task from beta"], beta)
    with pytest.raises(GitError, match=r"rejected|fetch first"):
        gitwrap.run(["push", "origin", "registry/p/2"], beta)  # the race arbitrates HERE

    # the resolution: alpha's PR merges first (the forge); beta drops the
    # stale duplicate, pulls the merged registry, re-adds — no id reuse
    gitwrap.run(["checkout", "-q", "main"], alpha)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge pull request #1: registry/p/2", "registry/p/2"],
        alpha,
    )
    gitwrap.run(["push", "-q", "origin", "main"], alpha)
    gitwrap.run(["push", "-q", "origin", "--delete", "registry/p/2"], alpha)  # the forge auto-delete
    gitwrap.run(["checkout", "-q", "main"], beta)
    gitwrap.run(["pull", "--no-rebase", "-q", "origin", "main"], beta)
    gitwrap.run(["branch", "-q", "-D", "registry/p/2"], beta)

    assert add_mod.add(beta, "p", "task from beta, re-added") == 3  # a fresh burst: id 3

    # beta's PR merges (the forge): main gains the re-added task
    gitwrap.run(["fetch", "-q", "origin"], beta)
    gitwrap.run(["checkout", "-q", "main"], beta)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge pull request #2: registry/p/3 (re-added)",
         "origin/registry/p/3"],
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
    assert "registry/p/2" in heads and "registry/p/3" not in heads  # ONE branch for the burst
    branch_file = gitwrap.out(["show", "origin/registry/p/2:tasks.yml"], alpha)
    assert "first of the burst" in branch_file and "second of the burst" in branch_file
    # the ride returned to main and the trunk never saw the burst directly
    assert gitwrap.lines(["log", "origin/main", "--merges", "--format=%s"], alpha) == []


def test_three_add_burst_allocates_from_the_content(two_clones, monkeypatch, capsys):
    """Task tooling/78: the ride branch's NAME freezes at the burst's first
    add, its content grows with every add. The parseable name (tooling/69)
    made the branch match the work-branch pattern, and the name-based read
    buried the content-read — the third add allocated the taken id again.
    A registry-type branch is read by content, never by name."""
    monkeypatch.setattr(forge_module, "add_ride", conftest_helpers.real_add_ride)

    alpha, _beta = two_clones
    assert add_mod.add(alpha, "p", "first of the burst") == 2
    assert add_mod.add(alpha, "p", "second of the burst") == 3
    assert add_mod.add(alpha, "p", "third of the burst") == 4  # the name says 2; the content says 3

    branch_file = gitwrap.out(["show", "origin/registry/p/2:tasks.yml"], alpha)
    assert "third of the burst" in branch_file
    ids = [line.strip() for line in branch_file.splitlines() if line.strip().startswith("- id:")]
    assert len(ids) == len(set(ids))  # no duplicates


# --- bookkeeping rides claim nothing (task tooling/77) -------------------------


def _states(clone):
    from jearless import config as config_mod
    from jearless import state as state_mod

    cfg = config_mod.load(clone)
    view = state_mod.compute(clone, cfg, registry.load(clone))
    return {tv.task.id: tv.state for tv in view.tasks}


def _register_never_taken(alpha, monkeypatch):
    """A task added through the ride and merged as a registration — the work
    never happened: no take, no work branch, no delivery."""
    monkeypatch.setattr(forge_module, "add_ride", conftest_helpers.real_add_ride)
    add_mod.add(alpha, "p", "registered, never taken")
    gitwrap.run(["fetch", "-q", "origin"], alpha)
    gitwrap.run(["checkout", "-q", "-B", "registry/p/2", "origin/registry/p/2"], alpha)
    gitwrap.run(["checkout", "-q", "main"], alpha)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'registry/p/2'", "origin/registry/p/2"],
        alpha,
    )
    gitwrap.run(["push", "-q", "origin", "main"], alpha)
    gitwrap.run(["fetch", "-q", "origin"], alpha)


def test_merged_registration_credits_nothing(two_clones, monkeypatch):
    """The registration merge names the task — and credits nothing anywhere:
    no done, no bar, no report merge, no event merged."""
    import contextlib
    import io

    from jearless import changelog as changelog_mod
    from jearless import config as config_mod
    from jearless import events as events_mod
    from jearless import report as report_mod
    from jearless import timeline as timeline_mod

    alpha, _beta = two_clones
    _register_never_taken(alpha, monkeypatch)

    assert _states(alpha) == {1: "available", 2: "available"}

    cfg = config_mod.load(alpha)
    refs = cfg.integration_refs(alpha, "origin")
    bars = timeline_mod.merge_bars(alpha, cfg, registry.load(alpha), refs)
    assert bars == []

    first_sha, _fb, _returns, total, _fix = report_mod._task_merges(alpha, cfg, None, refs)
    assert first_sha == {} and total == 0

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        changelog_mod.run(alpha)
    out = buf.getvalue()
    assert "p-2" not in out
    assert "off-taxonomy" not in out  # sanctioned bookkeeping: not a hole either

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        events_mod.run(alpha)
    stream = buf.getvalue()
    assert "task.created:p/2" in stream
    assert "task.merged:p/2" not in stream


def test_a_work_merge_after_a_registration_still_credits(two_clones, monkeypatch):
    """The exclusion is scoped to bookkeeping kinds: the real delivery — a
    work branch merged after the registration — credits exactly as before."""
    alpha, _beta = two_clones
    _register_never_taken(alpha, monkeypatch)
    branch = alpha_git_take(alpha)
    _work_and_merge(alpha, branch)
    assert _states(alpha) == {1: "available", 2: "done"}


def alpha_git_take(alpha):
    from jearless import take as take_mod

    return take_mod.take(alpha, "p", 2)


def _work_and_merge(alpha, branch):
    (alpha / "work.txt").write_text("done\n", encoding="utf-8")
    gitwrap.run(["add", "work.txt"], alpha)
    gitwrap.run(["commit", "-q", "-m", "the real work"], alpha)
    gitwrap.run(["push", "-q", "-u", "origin", branch], alpha)
    gitwrap.run(["checkout", "-q", "main"], alpha)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], alpha)
    gitwrap.run(["push", "-q", "origin", "main"], alpha)
    gitwrap.run(["fetch", "-q", "origin"], alpha)
