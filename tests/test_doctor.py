import pytest

from jearless import doctor as doctor_mod
from jearless import gitwrap

REGISTRY = "tasks:\n  p:\n    - id: 1\n      summary: a\n"


@pytest.fixture
def repo(origin_and_clone):
    _, clone = origin_and_clone
    (clone / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    gitwrap.run(["add", "tasks.yml"], clone)
    gitwrap.run(["commit", "-q", "-m", "registry"], clone)
    gitwrap.run(["push", "-q", "-u", "origin", "main"], clone)
    return clone


def test_clean_repo_passes(repo, capsys):
    assert doctor_mod.run(repo) == 0
    assert "0 finding" in capsys.readouterr().out


def test_squash_commit_is_the_visible_hole(repo, capsys):
    """Phase 2 DoD: a squash commit is highlighted loudly, not lost silently."""
    (repo / "code.py").write_text("print('squashed work')", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "task 16 squashed"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out
    assert "unattributed commit" in out
    assert "task 16 squashed" in out
    assert "squash or fast-forward suspected" in out


def test_merge_arrivals_are_attributed(repo, capsys):
    """WIP that arrived inside a --no-ff merge must not be flagged — only the chain is audited."""
    gitwrap.run(["checkout", "-q", "-b", "feature/p/1-thing"], repo)
    (repo / "code.py").write_text("work", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "wip inside the branch"], repo)
    gitwrap.run(["push", "-q", "-u", "origin", "feature/p/1-thing"], repo)
    gitwrap.run(["checkout", "-q", "main"], repo)
    gitwrap.run(
        ["merge", "--no-ff", "-q", "-m", "Merge branch 'feature/p/1-thing'", "feature/p/1-thing"],
        repo,
    )
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0


def test_registry_edits_are_attributed(repo, capsys):
    (repo / "tasks.yml").write_text(
        REGISTRY + "    - id: 2\n      summary: b\n", encoding="utf-8"
    )
    gitwrap.run(["add", "tasks.yml"], repo)
    gitwrap.run(["commit", "-q", "-m", "one more task"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0


def test_branch_naming_violation(repo, capsys):
    gitwrap.run(["push", "-q", "origin", "main:refs/heads/feature/typo"], repo)
    assert doctor_mod.run(repo) == 1
    assert "'feature/typo'" in capsys.readouterr().out


def test_invalid_registry_reported(repo, capsys):
    # the working tree is sick (a stored status) — doctor reads it before any commit
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      status: available\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    assert "status" in capsys.readouterr().out


def test_broken_link_is_a_finding(repo, capsys):
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      depends_on: 99\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    assert "links:" in capsys.readouterr().out


def test_link_cycle_is_a_finding(repo, capsys):
    (repo / "tasks.yml").write_text(
        "tasks:\n  p:\n"
        "    - id: 1\n      summary: a\n      depends_on: 2\n"
        "    - id: 2\n      summary: b\n      depends_on: 1\n",
        encoding="utf-8",
    )
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out  # one drain: a second readouterr() returns empty
    assert "links:" in out and "cycle" in out


def test_two_live_registries_is_a_finding(repo, capsys):
    (repo / ".jearless").mkdir()
    (repo / ".jearless" / "tasks.yml").write_text(REGISTRY, encoding="utf-8")
    assert doctor_mod.run(repo) == 1
    assert "two live registries" in capsys.readouterr().out


# --- *.md = documentation bookkeeping (task tooling/13) ---


def test_md_only_commit_is_sanctioned(repo, capsys):
    (repo / "NOTES.md").write_text("notes\n", encoding="utf-8")
    gitwrap.run(["add", "NOTES.md"], repo)
    gitwrap.run(["commit", "-q", "-m", "docs: notes"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 0  # documentation bookkeeping


def test_md_plus_code_commit_is_flagged(repo, capsys):
    (repo / "NOTES.md").write_text("notes\n", encoding="utf-8")
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    gitwrap.run(["add", "."], repo)
    gitwrap.run(["commit", "-q", "-m", "docs and code mixed"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    assert doctor_mod.run(repo) == 1  # code inside: still a hole


# --- the scar ledger (task tooling/31) ---


def _direct_commit(repo, filename: str, message: str) -> str:
    (repo / filename).write_text("x", encoding="utf-8")
    gitwrap.run(["add", filename], repo)
    gitwrap.run(["commit", "-q", "-m", message], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    return gitwrap.out(["rev-parse", "HEAD"], repo)


def test_ledger_silences_an_acknowledged_scar(repo, capsys):
    sha = _direct_commit(repo, "legacy.py", "a real accident, accepted")
    ledger = repo / ".jearless" / "doctor_ignore"
    ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(f"# accepted: content superseded later\n{sha[:7]}  # the cause\n",
                      encoding="utf-8")
    assert doctor_mod.run(repo) == 0  # exit 0: gate-able at last
    out = capsys.readouterr().out
    assert "1 accepted scar(s) on the ledger (.jearless/doctor_ignore)" in out
    assert "unattributed" not in out


def test_ledger_sha_precision(repo, capsys):
    """The ledger by exact sha: it can never hide a NEW violation."""
    sha = _direct_commit(repo, "old.py", "accepted accident")
    ledger = repo / ".jearless" / "doctor_ignore"
    ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(f"{sha[:7]}  # acknowledged\n", encoding="utf-8")
    _direct_commit(repo, "new.py", "a fresh sin")
    assert doctor_mod.run(repo) == 1
    out = capsys.readouterr().out
    assert "1 accepted scar(s) on the ledger" in out  # the old one suppressed
    assert "a fresh sin" in out  # the new one screams


def test_ledger_ignores_comments_and_blanks(repo, capsys):
    sha = _direct_commit(repo, "old.py", "accepted accident")
    ledger = repo / ".jearless" / "doctor_ignore"
    ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(f"# header\n\n{sha[:7]}  # cause\n\n# tail\n", encoding="utf-8")
    assert doctor_mod.run(repo) == 0


def test_acknowledge_appends_and_stages(repo, capsys):
    """task tooling/36: the ledger UX — validate, require the cause, append, stage."""
    (repo / "code.py").write_text("x", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "the slip itself"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    sha = gitwrap.out(["rev-parse", "origin/main"], repo)[:7]
    assert doctor_mod.acknowledge(repo, sha, "the honest mistake, acknowledged") == 0
    out = capsys.readouterr().out
    assert f"acknowledged: {sha} — the honest mistake, acknowledged" in out
    assert "staged" in out
    ledger = (repo / ".jearless" / "doctor_ignore").read_text(encoding="utf-8")
    assert f"{sha}  # the honest mistake, acknowledged" in ledger
    staged = gitwrap.out(["status", "--porcelain"], repo)
    assert "jearless/doctor_ignore" in staged  # staged (A or M), never committed — the charter


def test_acknowledge_then_doctor_is_clean(repo, capsys):
    (repo / "code.py").write_text("x", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "slip"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    sha = gitwrap.out(["rev-parse", "origin/main"], repo)[:7]
    doctor_mod.acknowledge(repo, sha, "the scar stays visible")
    capsys.readouterr()
    assert doctor_mod.run(repo) == 0
    assert "1 accepted scar(s) on the ledger" in capsys.readouterr().out


def test_acknowledge_unknown_sha_refused(repo):
    with pytest.raises(Exception, match="no such commit on the origin/main"):
        doctor_mod.acknowledge(repo, "deadbee", "cause")


def test_acknowledge_duplicate_refused(repo, capsys):
    (repo / "code.py").write_text("x", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "slip"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    sha = gitwrap.out(["rev-parse", "origin/main"], repo)[:7]
    doctor_mod.acknowledge(repo, sha, "first verdict")
    with pytest.raises(Exception, match="already acknowledged"):
        doctor_mod.acknowledge(repo, sha, "second verdict")


def test_acknowledge_empty_cause_refused(repo, capsys):
    (repo / "code.py").write_text("x", encoding="utf-8")
    gitwrap.run(["add", "code.py"], repo)
    gitwrap.run(["commit", "-q", "-m", "slip"], repo)
    gitwrap.run(["push", "-q", "origin", "main"], repo)
    sha = gitwrap.out(["rev-parse", "origin/main"], repo)[:7]
    with pytest.raises(Exception, match="cause is required"):
        doctor_mod.acknowledge(repo, sha, "   ")
    assert not (repo / ".jearless" / "doctor_ignore").exists()  # nothing written on a bare pass
