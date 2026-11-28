"""Task: trailer attribution (task tooling/64) — the squash bridge.

The parser reads git's trailer block (the message's LAST paragraph): a
``Task: <project>/<id>`` line there declares the task. The changelog and
doctor read it; the subject regexes stay the legacy fallback for real
merges, and a plain commit's subject is never trusted.
"""

import pytest

from jearless import changelog as changelog_mod
from jearless import config as config_mod
from jearless import doctor as doctor_mod
from jearless import gitwrap
from jearless import registry as registry_mod
from jearless import reject as reject_mod
from jearless import state as state_mod
from jearless import take as take_mod

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
"""


# --- the parser: git's trailer rule (the last paragraph declares) ---


def test_generator_format_attributes():
    """The shape `jear message` prints: summary, description, trailer last."""
    assert state_mod.task_trailer("the summary\n\nthe description\n\nTask: p/1") == ("p", 1)


def test_mid_body_mention_is_not_a_trailer():
    """A PR template's bold Task line and prose notes declare nothing."""
    body = "**Task:** p/1 — the template line\n\nsome prose\nTask: p/1 mid-note\n\nthe end"
    assert state_mod.task_trailer(body) is None


def test_trailer_not_in_last_paragraph_declares_nothing():
    assert state_mod.task_trailer("Task: p/1\n\nthe real last paragraph") is None


def test_trailer_block_alongside_other_trailers():
    assert state_mod.task_trailer("s\n\nCo-authored-by: X <x@y>\nTask: p/2") == ("p", 2)


def test_empty_body_and_bare_subject():
    assert state_mod.task_trailer("") is None
    assert state_mod.task_trailer("just a subject") is None


def test_whitespace_tolerated():
    assert state_mod.task_trailer("s\n\nTask:   p/1  ") == ("p", 1)


def test_malformed_values_declare_nothing():
    assert state_mod.task_trailer("s\n\nTask: p/x") is None
    assert state_mod.task_trailer("s\n\nTask: p/") is None


# --- the changelog: squash entries and trailer-first merges ---


@pytest.fixture
def history(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def _squash(clone, filename: str, subject: str, body: str | None = None):
    """A squash-style plain commit straight on main: the bridge's delivery."""
    (clone / filename).write_text("work", encoding="utf-8")
    gitwrap.run(["add", filename], clone)
    args = ["commit", "-q", "-m", subject]
    if body:
        args += ["-m", body]
    gitwrap.run(args, clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def _merge_branch(clone, branch: str, subject: str, body: str | None = None):
    gitwrap.run(["checkout", "-q", "-b", branch], clone)
    (clone / f"{branch.replace('/', '_')}.txt").write_text("done", encoding="utf-8")
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", f"work on {branch}"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    args = ["merge", "--no-ff", "-q", "-m", subject]
    if body:
        args += ["-m", body]  # the second -m is the body
    gitwrap.run([*args, branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


def test_squash_with_trailer_is_an_entry(history, capsys):
    _squash(history, "f1.py", "first task done", "the description\n\nTask: p/1")
    assert changelog_mod.run(history) == 0
    out = capsys.readouterr().out
    assert "- p-1: first task" in out
    assert "off-taxonomy" not in out


def test_squash_without_trailer_is_invisible(history, capsys):
    """No declaration, no entry — the changelog stays quiet, doctor screams."""
    _squash(history, "f1.py", "unattributed work", "some body")
    assert changelog_mod.run(history) == 0
    assert "- p-1" not in capsys.readouterr().out


def test_trailer_first_on_a_forged_subject(history, capsys):
    """The hostile review's P0: the merge subject is forgeable — the trailer
    attributes, the lying subject never does."""
    _merge_branch(history, "feature/p/1-real", "Merge branch 'fix/p/2-fake'", body="Task: p/1")
    assert changelog_mod.run(history) == 0
    out = capsys.readouterr().out
    assert "- p-1: first task" in out
    assert "p-2" not in out
    assert "off-taxonomy" not in out


def test_trailer_with_agreeing_subject_keeps_the_kind(history, capsys):
    """The subject branch agrees with the declaration: its kind is honest."""
    _merge_branch(history, "fix/p/2-thing", "Merge branch 'fix/p/2-thing'", body="Task: p/2")
    assert changelog_mod.run(history) == 0
    out = capsys.readouterr().out
    assert "### Fixed" in out and "- p-2: second task" in out.split("### Fixed")[1]


def test_legacy_subject_path_still_attributes(history, capsys):
    """No trailer at all: the subject regexes are the legacy fallback."""
    _merge_branch(history, "fix/p/2-thing", "Merge branch 'fix/p/2-thing'")
    assert changelog_mod.run(history) == 0
    out = capsys.readouterr().out
    assert "### Fixed" in out and "- p-2: second task" in out.split("### Fixed")[1]


def test_ghost_trailer_falls_back_to_the_subject(history, capsys):
    """A trailer naming an unknown task declares nothing — the legacy path
    still attributes."""
    _merge_branch(history, "feature/p/2-real", "Merge branch 'feature/p/2-real'", body="Task: p/99")
    assert changelog_mod.run(history) == 0
    assert "- p-2: second task" in capsys.readouterr().out


def test_squash_before_the_tag_is_not_reshipped(history, capsys):
    _squash(history, "f1.py", "first", "Task: p/1")
    gitwrap.run(["tag", "v0.1.0"], history)
    _squash(history, "f2.py", "again", "Task: p/1")
    capsys.readouterr()
    changelog_mod.run(history, from_tag="v0.1.0")
    out = capsys.readouterr().out
    assert "- p-1" not in out  # shipped in v0.1.0; the re-squash is not a new entry
    assert "1 re-merge(s) collapsed" in out


# --- doctor: the bridge commit is attributed, not a hole ---


@pytest.fixture
def drepo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def test_doctor_trailer_commit_is_attributed(drepo, capsys):
    _squash(drepo, "code.py", "squashed delivery", "Task: p/1")
    assert doctor_mod.run(drepo) == 0
    assert "0 finding" in capsys.readouterr().out


def test_doctor_ghost_trailer_is_still_a_hole(drepo, capsys):
    """A trailer naming a task the registry does not know declares nothing."""
    _squash(drepo, "code.py", "claims a ghost", "Task: p/42")
    assert doctor_mod.run(drepo) == 1
    out = capsys.readouterr().out
    assert "unattributed commit" in out and "no Task: trailer" in out


def test_doctor_bold_template_line_is_not_a_declaration(drepo, capsys):
    _squash(drepo, "code.py", "so-called task line", "**Task:** p/1 from a template")
    assert doctor_mod.run(drepo) == 1
    assert "unattributed commit" in capsys.readouterr().out


# --- the state join reads trailers too (task tooling/74, the review's P0) ---


def _states(clone):
    cfg = config_mod.load(clone)
    view = state_mod.compute(clone, cfg, registry_mod.load(clone))
    return {tv.task.id: tv.state for tv in view.tasks}


def test_squash_delivery_is_done_on_the_board(history):
    """The critic's consequence 3: a squash-only org gets its board — the
    branch is gone, the declaration is all that survives."""
    _squash(history, "f1.py", "the delivery", "Task: p/1")
    assert _states(history) == {1: "done", 2: "available"}


def test_ghost_trailer_never_closes_the_task(history):
    _squash(history, "f1.py", "claims a ghost", "Task: p/42")
    assert _states(history) == {1: "available", 2: "available"}


def test_edited_merge_subject_with_trailer_still_closes(history):
    """The critic's consequence 2: the reviewer rewrote the subject at merge
    time; the body declares. The board agrees with the changelog."""
    _merge_branch(history, "feature/p/1-real", "the reviewer rewrote this", body="Task: p/1")
    assert _states(history) == {1: "done", 2: "available"}


def test_retake_after_a_squash_delivery_reopens(history):
    _squash(history, "f1.py", "the delivery", "Task: p/1")
    take_mod.take(history, "p", 1, kind="fix")
    assert _states(history) == {1: "in_progress", 2: "available"}


def test_rejected_wins_over_the_trailer_delivery(history):
    _squash(history, "f1.py", "the delivery", "Task: p/1")
    reject_mod.run(history, "p", 1, "withdrawn by the owner")
    assert _states(history) == {1: "rejected", 2: "available"}


def test_trailer_on_the_family_branch_is_done(origin_and_clone):
    """GitFlow: the declaration on the unpromoted family branch integrates the
    task — done reads the same surface the changelog reads."""
    _bare, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    (clone / ".jearless.toml").write_text(
        '[git]\nintegration_ref = "sprint-27"\n', encoding="utf-8"
    )
    gitwrap.run(["add", "."], clone)
    gitwrap.run(["commit", "-q", "-m", "registry + config"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    gitwrap.run(["push", "-q", "origin", "main:sprint-27"], clone)
    gitwrap.run(["checkout", "-q", "sprint-27"], clone)
    (clone / "f1.py").write_text("work\n", encoding="utf-8")
    gitwrap.run(["add", "f1.py"], clone)
    gitwrap.run(["commit", "-q", "-m", "the delivery", "-m", "Task: p/1"], clone)
    gitwrap.run(["push", "-q", "origin", "sprint-27"], clone)
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["fetch", "-q", "origin"], clone)
    assert _states(clone) == {1: "done", 2: "available"}
