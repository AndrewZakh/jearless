"""release: the one human-run move — tag, changelog section, timeline snapshot.

The release moment freezes the facts (README): the changelog and the snapshot
are committed as artifacts, then the annotated tag lands on that commit, then
both go to the remote. The tag defaults to the flow version from env.yml.
"""

from pathlib import Path

from ruamel.yaml import YAML

from jearless import changelog, gitwrap, timeline
from jearless.errors import JearlessError

CHANGELOG_NAME = "CHANGELOG.md"
SNAPSHOTS_DIR = "snapshots"


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


def _preconditions(cwd: Path, remote: str) -> None:
    if gitwrap.out(["status", "--porcelain"], cwd):
        raise JearlessError("working tree is dirty — commit or stash first")
    if gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd) != "main":
        raise JearlessError("release runs on main")
    gitwrap.run(["fetch", "--quiet", remote], cwd)
    if gitwrap.out(["rev-parse", "main"], cwd) != gitwrap.out(["rev-parse", f"{remote}/main"], cwd):
        raise JearlessError(f"main is not in sync with {remote}/main")


def _merge_changelog(path: Path, body: str) -> None:
    """New section on top; the old ones keep their place below."""
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old.startswith("# Changelog"):
            old_body = old[len("# Changelog") :].lstrip("\n")
            body = body.rstrip("\n") + "\n\n" + old_body
    path.write_text(body, encoding="utf-8")


def run(cwd: Path, tag: str | None = None, remote: str = "origin") -> int:
    _preconditions(cwd, remote)
    tag = tag or _flow_version(cwd)
    try:
        gitwrap.run(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], cwd)
    except gitwrap.GitError:
        pass  # no such tag — the good path
    else:
        raise JearlessError(f"tag {tag} already exists")

    from_tag = _last_tag(cwd)
    _merge_changelog(
        cwd / CHANGELOG_NAME, changelog.render(cwd, from_tag=from_tag, to_tag="HEAD", header=tag)
    )
    snapshots = cwd / SNAPSHOTS_DIR
    snapshots.mkdir(exist_ok=True)
    (snapshots / f"timeline-{tag}.mmd").write_text(
        timeline.render(cwd, snapshot="HEAD", title=f"jearless — snapshot {tag}"),
        encoding="utf-8",
    )
    gitwrap.run(["add", CHANGELOG_NAME, SNAPSHOTS_DIR], cwd)
    gitwrap.run(["commit", "-q", "-m", f"release {tag}: changelog and timeline snapshot"], cwd)
    gitwrap.run(["tag", "-a", tag, "-m", f"Release {tag}"], cwd)
    gitwrap.run(["push", "-q", remote, "main"], cwd)
    gitwrap.run(["push", "-q", remote, tag], cwd)
    print(f"released {tag}: CHANGELOG.md section + {SNAPSHOTS_DIR}/timeline-{tag}.mmd, tag pushed")
    return 0
