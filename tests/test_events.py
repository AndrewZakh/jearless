"""jear events (task tooling/73): the lifecycle as a versioned JSON stream.

A PULL-based export: stable ids (type:key:sha), replay by re-running the
command, no delivery. The tests build one full lifecycle and read the stream.
"""

import contextlib
import io
import json

import pytest

from jearless import events as events_mod
from jearless import gitwrap
from jearless import reject as reject_mod
from jearless import take as take_mod
from jearless.errors import JearlessError

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
    - id: 3
      summary: third task
"""


def _work(clone, filename: str, message: str):
    (clone / filename).write_text("work\n", encoding="utf-8")
    gitwrap.run(["add", filename], clone)
    gitwrap.run(["commit", "-q", "-m", message], clone)


def _merge(clone, branch: str):
    gitwrap.run(["checkout", "-q", "main"], clone)
    gitwrap.run(["merge", "--no-ff", "-q", "-m", f"Merge branch '{branch}'", branch], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)


@pytest.fixture
def lifecycle(origin_and_clone):
    """One full lifecycle: three tasks — one merged, one merged twice (a
    return), one rejected; a sprint plan; an annotated release tag."""
    _bare, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)

    branch = take_mod.take(clone, "p", 1)  # take switches to the branch
    _work(clone, "one.txt", "work one")
    gitwrap.run(["push", "-q", "-u", "origin", branch], clone)
    _merge(clone, branch)

    branch2 = take_mod.take(clone, "p", 2)
    _work(clone, "two.txt", "work two")
    gitwrap.run(["push", "-q", "-u", "origin", branch2], clone)
    _merge(clone, branch2)
    gitwrap.run(["checkout", "-q", branch2], clone)
    _work(clone, "two_more.txt", "second round")
    gitwrap.run(["push", "-q", "origin", branch2], clone)
    _merge(clone, branch2)  # the same branch again: a return

    reject_mod.run(clone, "p", 3, "superseded by task 2")

    plans = clone / ".jearless" / "plans"
    plans.mkdir(parents=True)
    (plans / "sprint_1.yml").write_text("plan:\n  goal: g\n  tasks: []\n", encoding="utf-8")
    gitwrap.run(["add", ".jearless/plans/sprint_1.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "sprint_1 plan"], clone)
    gitwrap.run(["push", "-q", "origin", "main"], clone)
    gitwrap.run(["tag", "-a", "v0.1.0", "-m", "the first release"], clone)
    return clone


def _stream(clone, since: str | None = None) -> list[dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert events_mod.run(clone, since=since) == 0
    return [json.loads(line) for line in buf.getvalue().splitlines()]


def test_the_full_lifecycle_stream(lifecycle):
    events = _stream(lifecycle)
    types = [e["type"] for e in events]
    assert types.count("task.created") == 3
    assert types.count("task.started") == 2  # p/3 was never taken
    assert types.count("task.merged") == 2  # first arrivals
    assert types.count("task.returned") == 1  # the second merge of task 2
    assert types.count("task.rejected") == 1
    assert types.count("sprint.opened") == 1
    assert types.count("release.tagged") == 1


def test_envelope_and_stable_ids(lifecycle):
    events = _stream(lifecycle)
    for event in events:
        assert event["v"] == 1
        assert event["id"] == f'{event["type"]}:{event["key"]}:{event["sha"]}'
    assert len({e["id"] for e in events}) == len(events)


def test_keys_name_their_carrier(lifecycle):
    events = _stream(lifecycle)
    created = [e for e in events if e["type"] == "task.created"]
    assert {e["key"] for e in created} == {"p/1", "p/2", "p/3"}
    assert next(e for e in events if e["type"] == "sprint.opened")["key"] == "sprint_1"
    assert next(e for e in events if e["type"] == "release.tagged")["key"] == "v0.1.0"
    assert next(e for e in events if e["type"] == "task.rejected")["key"] == "p/3"


def test_replay_is_identical(lifecycle):
    first, second = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(first):
        events_mod.run(lifecycle)
    with contextlib.redirect_stdout(second):
        events_mod.run(lifecycle)
    assert first.getvalue() == second.getvalue()


def test_stream_is_ordered_by_time(lifecycle):
    times = [e["time"] for e in _stream(lifecycle)]
    assert times == sorted(times)


def test_since_filters_the_pull_point(lifecycle):
    events = _stream(lifecycle)
    registry_commit = next(e["sha"] for e in events if e["type"] == "task.created")
    rest = _stream(lifecycle, since=registry_commit)
    assert all(e["type"] != "task.created" for e in rest)
    assert len(rest) == len(events) - 3  # the three births sat on the pull point


def test_reject_cause_is_the_declaring_commit(lifecycle):
    rejected = next(e for e in _stream(lifecycle) if e["type"] == "task.rejected")
    subject = gitwrap.out(
        ["log", "-1", "--format=%B", rejected["sha"]], lifecycle
    )
    assert "rejected" in subject.lower()


def test_format_guard(lifecycle):
    with pytest.raises(JearlessError):
        events_mod.run(lifecycle, fmt="csv")
