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


def test_zero_plans_falls_back_to_trunk(origin_and_clone):
    """Task tooling/33: {n} with NO plans resolves to the trunk — the same
    rule the board and the burndown follow. A live demo caught release-s0."""
    _bare, clone = origin_and_clone
    (clone / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "release-s{n}"\n', encoding="utf-8"
    )
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "cfg + registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    branch = take_mod.take(clone, "p", 1)
    assert branch.startswith("feature/p/1-")  # trunk fallback, not release-s0


# --- the GitFlow edges (task tooling/61) -------------------------------------
# Every case below was first run by hand in a throwaway repository; the tests
# pin what was observed. No code change was needed: the mode already behaves
# correctly at these boundaries.

TWO_TASKS = """\
tasks:
  p:
    - id: 1
      summary: feature one
    - id: 2
      summary: feature two
"""


def _states(clone):
    cfg = config_mod.load(clone)
    view = state_mod.compute(clone, cfg, registry_mod.load(clone))
    return {tv.task.id: tv.state for tv in view.tasks}


_work_count = 0


def _mk(clone, branch, filename):
    """A task branch with one commit, cut from the staging tip, pushed.

    Each call appends a new line, so a branch re-created under the same name
    still carries a commit of its own.
    """
    global _work_count
    _work_count += 1
    gitwrap.run(["fetch", "-q", "origin"], clone)
    gitwrap.run(["checkout", "-q", "-b", branch, "origin/staging"], clone)
    with (clone / filename).open("a", encoding="utf-8") as fh:
        fh.write(f"work {_work_count} on {branch}\n")
    gitwrap.run(["add", filename], clone)
    gitwrap.run(["commit", "-q", "-m", f"work {branch}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)


def _integrate(clone, branch):
    """Merge into staging with --no-ff; the forge then deletes the task branch."""
    gitwrap.run(["fetch", "-q", "origin"], clone)
    gitwrap.run(["checkout", "-q", "-B", "staging", "origin/staging"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", f"origin/{branch}"], clone)
    gitwrap.run(["push", "-q", "origin", "staging"], clone)
    gitwrap.run(["push", "-q", "origin", "--delete", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)


@pytest.fixture
def two_integrated(gitflow):
    """Staging carries tasks 1 and 2; main carries nothing."""
    (gitflow / "tasks.yml").write_text(TWO_TASKS, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], gitflow)
    gitwrap.run(["commit", "-q", "-m", "two tasks"], gitflow)
    gitwrap.run(["push", "-q", "origin", "main:staging"], gitflow)  # keep staging aligned
    _mk(gitflow, "feature/p/1-feature-one", "one.txt")
    _integrate(gitflow, "feature/p/1-feature-one")
    _mk(gitflow, "feature/p/2-feature-two", "two.txt")
    _integrate(gitflow, "feature/p/2-feature-two")
    gitwrap.run(["fetch", "-q", "origin"], gitflow)
    return gitflow


def test_partial_promotion_keeps_both_done(two_integrated):
    """Only task 1 is promoted to main: task 2 is still DONE — in GitFlow mode
    done means 'integrated', whether or not it has reached main yet."""
    clone = two_integrated
    first = gitwrap.out(
        ["log", "origin/staging", "--merges", "--format=%H", "--reverse"], clone
    ).split()[0]
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Promote task 1 only", first], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert _states(clone) == {1: "done", 2: "done"}


def test_partial_promotion_changelog_shows_what_the_promotion_delivers(two_integrated, capsys):
    clone = two_integrated
    first = gitwrap.out(
        ["log", "origin/staging", "--merges", "--format=%H", "--reverse"], clone
    ).split()[0]
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Promote task 1 only", first], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert changelog_mod.run(clone, from_tag="origin/main", to_tag="origin/staging") == 0
    out = capsys.readouterr().out
    assert "p-2: feature two" in out and "p-1" not in out  # task 1 already landed


def test_re_integration_stays_done(two_integrated):
    """The same branch name is re-created and merged into staging a second time:
    a re-merge is an artifact — the task stays done, first arrival wins."""
    clone = two_integrated
    gitwrap.run(["branch", "-q", "-D", "feature/p/2-feature-two"], clone)
    _mk(clone, "feature/p/2-feature-two", "two.txt")
    _integrate(clone, "feature/p/2-feature-two")
    subjects = gitwrap.lines(["log", "origin/staging", "--merges", "--format=%s"], clone)
    assert subjects.count("Merge branch 'feature/p/2-feature-two'") == 2  # integrated twice
    assert _states(clone) == {1: "done", 2: "done"}


def test_retake_is_seen_with_other_tasks_integrated_afterwards(two_integrated):
    """A fix forked from the staging tip — past task 1's merge and past task
    2's — is rework on task 1: it reopens that task and leaves task 2 done."""
    clone = two_integrated
    _mk(clone, "fix/p/1-feature-one", "one.txt")  # a change to the task's own file
    assert _states(clone) == {1: "in_progress", 2: "done"}


def test_branch_forked_before_the_merge_is_not_a_retake(two_integrated):
    """A branch forked from a state that predates task 1's merge carries no
    rework — it cannot reopen the task. It stays a done task."""
    clone = two_integrated
    init = gitwrap.out(["log", "origin/main", "--format=%H", "--reverse"], clone).split()[0]
    merge_of_1 = gitwrap.out(
        ["log", "origin/staging", "--merges", "--format=%H", "--reverse"], clone
    ).split()[0]
    gitwrap.run(["checkout", "-q", "-b", "fix/p/1-pre-merge", init], clone)
    (clone / "one_stale.txt").write_text("stale\n", encoding="utf-8")
    gitwrap.run(["add", "one_stale.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "forked before the merge"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "fix/p/1-pre-merge"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert not gitwrap.is_ancestor(merge_of_1, "fix/p/1-pre-merge", clone)  # the premise holds
    assert _states(clone) == {1: "done", 2: "done"}


def test_divergence_between_staging_and_main_is_stable(two_integrated):
    """Staging ahead of main, main ahead of staging, task branches gone: the
    states do not depend on the two branches agreeing."""
    clone = two_integrated
    first = gitwrap.out(
        ["log", "origin/staging", "--merges", "--format=%H", "--reverse"], clone
    ).split()[0]
    gitwrap.run(["merge", "--no-ff", "-q", "-m", "Promote task 1 only", first], clone)
    (clone / "hotfix.txt").write_text("direct on main\n", encoding="utf-8")
    gitwrap.run(["add", "hotfix.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "a hotfix on main"], clone)  # main ahead of staging
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert int(gitwrap.out(["rev-list", "--count", "origin/main..origin/staging"], clone)) > 0
    assert int(gitwrap.out(["rev-list", "--count", "origin/staging..origin/main"], clone)) > 0
    assert _states(clone) == {1: "done", 2: "done"}


def test_retake_is_seen_before_any_promotion(gitflow):
    """The defect task tooling/61 found: main has never moved, the task's merge
    lives on staging alone. A fix forked from the staging tip is rework — it
    must reopen the task. Measured against the trunk only, the fork point fell
    before the merge and the live retake stayed done."""
    clone = gitflow
    _take_feature(clone)
    _integrate_to_staging_and_delete_branch(clone, "feature/p/1-the-feature")
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert gitwrap.lines(["log", "origin/main", "--merges", "--format=%H"], clone) == []  # main never moved
    assert _states(clone) == {1: "done"}

    gitwrap.run(["checkout", "-q", "-b", "fix/p/1-the-feature", "origin/staging"], clone)
    (clone / "fix.txt").write_text("rework\n", encoding="utf-8")
    gitwrap.run(["add", "fix.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "rework on the task"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "fix/p/1-the-feature"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert _states(clone) == {1: "in_progress"}


# --- the integration branch is any name (task tooling/61) --------------------
# Nothing in the tool is tied to a branch called "staging": the name comes
# from [git] integration_ref and may contain slashes.

@pytest.mark.parametrize(
    "integration", ["dev", "release-1", "sprint-27", "release/2.x", "sprint-{n}"]
)
def test_integration_branch_is_any_name(origin_and_clone, integration, capsys):
    """A task merged into the integration branch is done, the next task forks
    from that branch's tip and the changelog reads it — whatever it is called.
    With {n} the name follows the latest plan number."""
    _bare, clone = origin_and_clone
    name = integration
    (clone / ".jearless").mkdir()
    if "{n}" in name:
        plans = clone / ".jearless" / "plans"
        plans.mkdir()
        (plans / "sprint_27.yml").write_text(
            "plan:\n  goal: g\n  tasks:\n    - task: p/1\n", encoding="utf-8"
        )
        name = name.replace("{n}", "27")
    (clone / ".jearless.toml").write_text(
        f'[git]\nintegration_ref = "{integration}"\n', encoding="utf-8"
    )
    (clone / ".jearless" / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: feature one\n    - id: 2\n      summary: next task\n",
        encoding="utf-8",
    )
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "config + registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", f"main:{name}"], clone)

    gitwrap.run(["fetch", "-q", "origin"], clone)
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-feature-one", f"origin/{name}"], clone)
    (clone / "one.txt").write_text("one\n", encoding="utf-8")
    gitwrap.run(["add", "one.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "work task 1"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/p/1-feature-one"], clone)
    gitwrap.run(["checkout", "-q", "-b", "integ", f"origin/{name}"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-feature-one'",
         "origin/feature/p/1-feature-one"],
        clone,
    )
    gitwrap.run(["push", "-q", "origin", f"HEAD:{name}"], clone)
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/p/1-feature-one"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)

    assert gitwrap.lines(["log", "origin/main", "--merges", "--format=%H"], clone) == []
    assert _states(clone) == {1: "done", 2: "available"}

    branch = take_mod.take(clone, "p", 2)
    fork = gitwrap.out(["merge-base", f"origin/{name}", branch], clone)
    assert fork == gitwrap.out(["rev-parse", f"origin/{name}"], clone)  # stacks on its tip
    gitwrap.run(["checkout", "-q", "main"], clone)

    assert changelog_mod.run(clone, from_tag="origin/main", to_tag=f"origin/{name}") == 0
    assert "p-1: feature one" in capsys.readouterr().out  # the unreleased view reads that branch


# --- {n} follows the branch that exists (task tooling/66) --------------------
# A sprint's plan is often committed before its branch is created. Reading the
# plan number blindly pointed at a branch that did not exist: jear take
# refused, and the work integrated on the previous branch dropped out of view.

TWO_SHOP_TASKS = """\
tasks:
  shop:
    - id: 1
      summary: add the cart page
      story_points: 3
    - id: 2
      summary: add the checkout button
      story_points: 1
"""


@pytest.fixture
def sprint_repo(origin_and_clone):
    """GitFlow with sprint-{n}; sprint 27 open, task 1 integrated on its branch
    and not promoted."""
    _bare, clone = origin_and_clone
    (clone / ".jearless" / "plans").mkdir(parents=True)
    (clone / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "sprint-{n}"\n', encoding="utf-8"
    )
    (clone / ".jearless" / "tasks.yml").write_text(TWO_SHOP_TASKS, encoding="utf-8")
    (clone / ".jearless" / "plans" / "sprint_27.yml").write_text(
        "plan:\n  goal: the cart\n  tasks:\n    - task: shop/1\n    - task: shop/2\n",
        encoding="utf-8",
    )
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "registry, sprint_27 plan, config"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", "main:sprint-27"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)

    gitwrap.run(["checkout", "-q", "-b", "feature/shop/1-add-the-cart-page", "origin/sprint-27"], clone)
    (clone / "cart.txt").write_text("work\n", encoding="utf-8")
    gitwrap.run(["add", "cart.txt"], clone)
    gitwrap.run(["commit", "-q", "-m", "the cart page"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/shop/1-add-the-cart-page"], clone)
    gitwrap.run(["checkout", "-q", "-B", "sprint-27", "origin/sprint-27"], clone)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/shop/1-add-the-cart-page'",
         "origin/feature/shop/1-add-the-cart-page"],
        clone,
    )
    gitwrap.run(["push", "-q", "origin", "sprint-27"], clone)
    gitwrap.run(["push", "-q", "origin", "--delete", "feature/shop/1-add-the-cart-page"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["fetch", "-q", "--prune", "origin"], clone)
    return clone


def _open_sprint_28_without_its_branch(clone):
    (clone / ".jearless" / "plans" / "sprint_28.yml").write_text(
        "plan:\n  goal: checkout\n  tasks:\n    - task: shop/2\n", encoding="utf-8"
    )
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "sprint_28 plan"], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "--prune", "origin"], clone)
    assert "sprint-28" not in gitwrap.remote_heads(clone)  # the premise holds


def test_sprint_n_stays_on_the_branch_that_exists(sprint_repo):
    """The defect: sprint_28.yml is committed before sprint-28 is created.
    The integrated task stays done instead of dropping back to available."""
    clone = sprint_repo
    assert _states(clone) == {1: "done", 2: "available"}
    _open_sprint_28_without_its_branch(clone)
    assert _states(clone) == {1: "done", 2: "available"}


def test_sprint_n_take_works_before_the_new_branch_exists(sprint_repo):
    """jear take no longer refuses; the task forks from sprint-27's tip, so it
    carries the work already integrated there."""
    clone = sprint_repo
    _open_sprint_28_without_its_branch(clone)
    branch = take_mod.take(clone, "shop", 2)
    fork = gitwrap.out(["merge-base", "origin/sprint-27", branch], clone)
    assert fork == gitwrap.out(["rev-parse", "origin/sprint-27"], clone)
    assert gitwrap.out(["rev-parse", f"{branch}^{{tree}}"], clone) == gitwrap.out(
        ["rev-parse", "origin/sprint-27^{tree}"], clone
    )
    gitwrap.run(["checkout", "-q", "main"], clone)


def test_sprint_n_moves_on_once_the_new_branch_exists(sprint_repo):
    """When sprint-28 is created the tool follows it. This is the limit task
    tooling/67 keeps: sprint-27 is not promoted, and it now drops out of view."""
    clone = sprint_repo
    _open_sprint_28_without_its_branch(clone)
    gitwrap.run(["push", "-q", "origin", "main:sprint-28"], clone)
    gitwrap.run(["fetch", "-q", "--prune", "origin"], clone)
    cfg = config_mod.load(clone)
    assert cfg.live_ref(clone, "origin") == "origin/sprint-28"
    assert _states(clone) == {1: "available", 2: "available"}


def test_sprint_n_without_any_branch_falls_back_to_the_trunk(origin_and_clone):
    """Plans exist, no sprint branch was ever created: the trunk is the
    integration target, as when no plan exists at all."""
    _bare, clone = origin_and_clone
    (clone / ".jearless" / "plans").mkdir(parents=True)
    (clone / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "sprint-{n}"\n', encoding="utf-8"
    )
    (clone / ".jearless" / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: seed\n", encoding="utf-8"
    )
    (clone / ".jearless" / "plans" / "sprint_1.yml").write_text(
        "plan:\n  goal: g\n  tasks:\n    - task: p/1\n", encoding="utf-8"
    )
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "config + registry + plan"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    cfg = config_mod.load(clone)
    assert cfg.live_ref(clone, "origin") == "origin/main"


def test_sprint_n_needs_no_network(tmp_path, monkeypatch):
    """live_ref reads the local refs only: with git unable to reach anything,
    it still answers — and says the trunk when no sprint branch is known."""
    gitwrap.run(["init", "-q", "-b", "main", str(tmp_path)], tmp_path)
    (tmp_path / ".jearless" / "plans").mkdir(parents=True)
    (tmp_path / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "sprint-{n}"\n', encoding="utf-8"
    )
    (tmp_path / ".jearless" / "plans" / "sprint_3.yml").write_text(
        "plan:\n  goal: g\n  tasks: []\n", encoding="utf-8"
    )
    # any attempt to talk to a remote would go through this and fail loudly
    def no_network(*args, **kwargs):
        raise AssertionError("live_ref must not reach the remote")

    monkeypatch.setattr(gitwrap, "remote_heads", no_network)
    cfg = config_mod.load(tmp_path)
    assert cfg.live_ref(tmp_path, "origin") == "origin/main"
