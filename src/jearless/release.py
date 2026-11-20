"""release: two phases, neither writes main (task tooling/51).

PREPARE (`jear release [--tag TAG]`): cut release/<tag>, commit the artifacts
(changelog section, timeline snapshot, PM report) on that branch, push it and
open the PR (gh when available — a manual hint otherwise). FINALIZE (`jear
release --finalize <tag>`): after the PR merges, the annotated tag lands on
the origin tip — the merge commit — and is pushed. Nothing automatic writes
main, now without a single exception. The tag defaults to the flow version
from env.yml.
"""

from pathlib import Path

from ruamel.yaml import YAML

from jearless import changelog, config, gitwrap, timeline
from jearless import report as report_mod
from jearless.errors import JearlessError
from jearless.registry import HOMEDIR

CHANGELOG_NAME = "CHANGELOG.md"
SNAPSHOTS_DIR = f"{HOMEDIR}/snapshots"
REPORTS_DIR = f"{HOMEDIR}/reports"
CHECKLIST_NAME = "release.md"

_FALLBACK_HINT = "now: uv build && uv publish — the release is local until published"


def _flow_version(cwd: Path) -> str:
    path = cwd / "env.yml"
    if not path.exists():
        raise JearlessError("no env.yml: the release tag comes from the flow version")
    data = YAML(typ="rt").load(path)
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version:
        raise JearlessError("env.yml: no 'version' key")
    return version


def _last_tag(cwd: Path) -> str | None:
    try:
        return gitwrap.out(["describe", "--tags", "--abbrev=0"], cwd)
    except gitwrap.GitError:
        return None  # no tags yet — the whole history is the range


def _preconditions(cwd: Path, cfg: config.Config, remote: str) -> None:
    if gitwrap.out(["status", "--porcelain"], cwd):
        raise JearlessError("working tree is dirty — commit or stash first")
    if gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd) != cfg.trunk_ref:
        raise JearlessError(f"release runs on the trunk ({cfg.trunk_ref})")
    gitwrap.run(["fetch", "--quiet", remote], cwd)
    local_trunk = gitwrap.out(["rev-parse", cfg.trunk_ref], cwd)
    if local_trunk != gitwrap.out(["rev-parse", f"{remote}/{cfg.trunk_ref}"], cwd):
        raise JearlessError(f"{cfg.trunk_ref} is not in sync with {remote}/{cfg.trunk_ref}")


def _tag_free(cwd: Path, tag: str, remote: str) -> None:
    try:
        gitwrap.run(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], cwd)
    except gitwrap.GitError:
        pass  # no local tag — the good path
    else:
        raise JearlessError(f"tag {tag} already exists")
    if any(f"refs/tags/{tag}" in line for line in gitwrap.lines(["ls-remote", "--tags", remote], cwd)):
        raise JearlessError(f"tag {tag} already exists on {remote}")


def _merge_changelog(path: Path, body: str) -> None:
    """New section on top; the old ones keep their place below."""
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old.startswith("# Changelog"):
            old_body = old[len("# Changelog") :].lstrip("\n")
            body = body.rstrip("\n") + "\n\n" + old_body
    path.write_text(body, encoding="utf-8")


def _artifacts(cwd: Path, tag: str, from_tag: str | None) -> None:
    _merge_changelog(
        cwd / CHANGELOG_NAME, changelog.render(cwd, from_tag=from_tag, to_tag="HEAD", header=tag)
    )
    snapshots = cwd / SNAPSHOTS_DIR
    snapshots.mkdir(parents=True, exist_ok=True)
    (snapshots / f"timeline-{tag}.mmd").write_text(
        timeline.render(cwd, snapshot="HEAD", title=f"jearless — snapshot {tag}"),
        encoding="utf-8",
    )
    report_text = report_mod.render(cwd, tag, from_tag, to_ref="HEAD")
    reports = cwd / REPORTS_DIR
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"report-{tag}.md").write_text(report_text, encoding="utf-8")


def _checklist(cwd: Path) -> None:
    """The authored checklist (task tooling/23 + tooling/30): the team edits
    .jearless/release.md, the release prints it; the one-liner is the fallback."""
    checklist = cwd / HOMEDIR / CHECKLIST_NAME
    if checklist.exists():
        print(checklist.read_text(encoding="utf-8"), end="")
    else:
        print(_FALLBACK_HINT)


def _open_pr(cwd: Path, tag: str, branch: str, trunk: str) -> str | None:
    """gh when available; a manual hint otherwise. The labels-and-tokens polish
    is tooling/53's land — this is the plain transport."""
    try:
        url = gitwrap.out(
            [
                "gh", "pr", "create",
                "--base", trunk, "--head", branch,
                "--title", f"Release {tag}",
                "--body", f"Release {tag}: the artifacts ride the PR — nothing automatic writes main (task tooling/51).",
            ],
            cwd,
        )
        return url.strip() or None
    except (gitwrap.GitError, FileNotFoundError):
        return None


def run(cwd: Path, tag: str | None = None, remote: str = "origin") -> int:
    """PREPARE: the artifacts ride a release branch; main is untouched."""
    cfg = config.load(cwd)
    _preconditions(cwd, cfg, remote)
    tag = tag or _flow_version(cwd)
    _tag_free(cwd, tag, remote)
    branch = f"release/{tag}"
    from_tag = _last_tag(cwd)

    gitwrap.run(["checkout", "-q", "-b", branch, f"{remote}/{cfg.trunk_ref}"], cwd)
    try:
        _artifacts(cwd, tag, from_tag)
        gitwrap.run(["add", CHANGELOG_NAME, SNAPSHOTS_DIR, REPORTS_DIR], cwd)
        gitwrap.run(
            ["commit", "-q", "-m", f"release {tag}: changelog, timeline snapshot, PM report"], cwd
        )
        gitwrap.run(["push", "-q", "-u", remote, branch], cwd)
    except Exception:
        gitwrap.run(["checkout", "-q", cfg.trunk_ref], cwd)
        gitwrap.run(["branch", "-q", "-D", branch], cwd)
        raise
    gitwrap.run(["checkout", "-q", cfg.trunk_ref], cwd)

    pr = _open_pr(cwd, tag, branch, cfg.trunk_ref)
    print(f"release {tag}: artifacts on {branch} — merge the PR, then: jear release --finalize {tag}")
    print(f"PR: {pr}" if pr else f"open the PR by hand: {branch} -> {cfg.trunk_ref}")
    return 0


def finalize(cwd: Path, tag: str, remote: str = "origin") -> int:
    """FINALIZE: the tag lands on the origin tip — the merge commit."""
    cfg = config.load(cwd)
    _preconditions(cwd, cfg, remote)
    _tag_free(cwd, tag, remote)
    try:
        gitwrap.out(["show", f"{remote}/{cfg.trunk_ref}:{REPORTS_DIR}/report-{tag}.md"], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"no report-{tag}.md on {remote}/{cfg.trunk_ref} — merge the release PR first ({exc})"
        ) from exc
    tip = gitwrap.out(["rev-parse", f"{remote}/{cfg.trunk_ref}"], cwd)
    gitwrap.run(["tag", "-a", tag, "-m", f"Release {tag}", tip], cwd)
    gitwrap.run(["push", "-q", remote, tag], cwd)
    print(f"finalized {tag}: tag on {tip[:7]} ({remote}/{cfg.trunk_ref})")
    _checklist(cwd)
    return 0
