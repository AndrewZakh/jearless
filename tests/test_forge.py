import pytest

from jearless import forge as forge_mod
from jearless import gitwrap

REGISTRY = """\
tasks:
  p:
    - id: 1
      summary: first task
"""


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def test_open_pr_passes_labels_and_falls_back_unlabeled(tmp_path, monkeypatch):
    seen = []

    def fake_run(args, cwd):
        seen.append(args)
        if "--label" in args:
            return None  # the label does not exist in the repo
        return "https://example/pr/1"

    monkeypatch.setattr(forge_mod, "_run", fake_run)
    url = forge_mod.open_pr(tmp_path, "main", "registry/p-9", "t", "b", labels=("registry",))
    assert url == "https://example/pr/1"
    assert seen[0][-2:] == ["--label", "registry"]  # the labeled attempt first
    assert "--label" not in seen[1]  # the unlabeled retry saves the PR


def test_open_pr_gitlab_api(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_mod, "_run", lambda *a, **k: None)  # gh absent
    monkeypatch.setenv("CI_API_V4_URL", "https://gitlab.example/api/v4")
    monkeypatch.setenv("CI_PROJECT_ID", "42")
    monkeypatch.setenv("GL_TOKEN", "gl-secret")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"web_url": "https://gitlab.example/group/repo/-/merge_requests/3"}'

    def fake_urlopen(request, timeout):
        assert request.headers.get("Private-token") == "gl-secret"
        assert b'"source_branch": "registry/p-9"' in request.data
        return FakeResponse()

    monkeypatch.setattr(forge_mod.urllib.request, "urlopen", fake_urlopen)
    url = forge_mod.open_pr(tmp_path, "main", "registry/p-9", "t", "b", labels=("registry",))
    assert url.endswith("/-/merge_requests/3")


def test_open_pr_no_forge_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_mod, "_run", lambda *a, **k: None)
    monkeypatch.delenv("CI_API_V4_URL", raising=False)
    monkeypatch.delenv("GL_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert forge_mod.open_pr(tmp_path, "main", "b", "t", "body") is None


def test_registry_pr_ride_branch_commit_push_pr(repo, monkeypatch, capsys):
    import conftest

    (repo / "tasks.yml").write_text(REGISTRY + "    - id: 2\n      summary: second\n", encoding="utf-8")
    monkeypatch.setattr(forge_mod, "registry_pr", conftest.real_registry_pr)
    monkeypatch.setattr(forge_mod, "open_pr", lambda *a, **k: "https://example/pr/9")
    assert forge_mod.registry_pr(
        repo,
        files=["tasks.yml"],
        branch="registry/p-2",
        title="tasks.yml: p/2 — second",
        body="the ride",
        label="registry",
        base="main",
        trunk="main",
    )
    assert "PR: https://example/pr/9" in capsys.readouterr().out
    branch_tip = gitwrap.out(["rev-parse", "registry/p-2"], repo)
    assert "second" in gitwrap.out(["show", f"{branch_tip}:tasks.yml"], repo)  # committed on the branch
    assert gitwrap.out(["symbolic-ref", "--short", "HEAD"], repo) == "main"  # back where we started
    assert gitwrap.out(["rev-parse", "origin/registry/p-2"], repo) == branch_tip  # pushed


def test_registry_pr_manual_fallback_keeps_the_edit_staged(repo, monkeypatch, capsys):
    import conftest

    (repo / "tasks.yml").write_text(REGISTRY + "    - id: 2\n      summary: second\n", encoding="utf-8")
    monkeypatch.setattr(forge_mod, "registry_pr", conftest.real_registry_pr)
    monkeypatch.setattr(forge_mod, "open_pr", lambda *a, **k: None)  # no forge — manual territory
    assert not forge_mod.registry_pr(
        repo,
        files=["tasks.yml"],
        branch="registry/p-2",
        title="tasks.yml: p/2 — second",
        body="the ride",
        label="registry",
        base="main",
        trunk="main",
    )
    assert "open the PR by hand" in capsys.readouterr().out
    # the edit is committed on the branch (safe), never lost
    branch_tip = gitwrap.out(["rev-parse", "registry/p-2"], repo)
    assert "second" in gitwrap.out(["show", f"{branch_tip}:tasks.yml"], repo)
