from jearless import duplicate as dup
from jearless.registry import Registry, Task


def _reg(summaries: list[str]) -> Registry:
    return Registry(tasks={"p": [Task("p", i + 1, s) for i, s in enumerate(summaries)]})


def test_identical_summary_scores_full():
    matches = dup.find_similar(_reg(["paint it black", "open the door"]), "paint it black", 0.5)
    assert matches and matches[0].task.id == 1
    assert matches[0].score == 1.0


def test_disjoint_summary_scores_zero():
    assert dup.find_similar(_reg(["paint it black"]), "deploy the cluster", 0.1) == []


def test_domain_noise_is_cheap():
    """task/registry sit in every summary — overlap only on them is not a match."""
    reg = _reg(
        [
            "add a task to the registry",
            "remove a task from the registry",
            "audit the registry tasks",
        ]
    )
    assert dup.find_similar(reg, "archive the registry task list", 0.5) == []


def test_containment_catches_short_inside_long():
    reg = _reg(["paint the door red before the winter"])
    matches = dup.find_similar(reg, "paint the door", 0.6)
    assert matches and matches[0].task.id == 1


def test_reordering_is_not_the_enemy():
    reg = _reg(["claim a task with a single push"])
    matches = dup.find_similar(reg, "push a single task claim with", 0.6)
    assert matches and matches[0].task.id == 1


def test_limit_keeps_top_three():
    reg = _reg([f"paint the door number {i}" for i in range(5)])
    matches = dup.find_similar(reg, "paint the door", 0.1)
    assert len(matches) == 3
    assert matches == sorted(matches, key=lambda m: m.score, reverse=True)
