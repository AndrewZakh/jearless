from jearless.slug import slugify


def test_english_norm():
    assert slugify("Claim a task with a single push!") == "claim-a-task-with-a-single-push"


def test_punctuation_collapses():
    assert slugify("add — append: a task (to the registry)") == "add-append-a-task-to-the-registry"


def test_cyrillic_fallback_translit():
    # The fallback for those who skipped their lessons (README)
    assert slugify("Взять задачу одним пушем") == "vzyat-zadachu-odnim-pushem"


def test_length_cap_and_empty_fallback():
    assert len(slugify("x " * 100)) <= 64
    assert slugify("!!!") == "task"
