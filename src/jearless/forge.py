"""forge: the PR/MR transport (task tooling/53) — jear speaks the forge natively.

GitHub rides gh; GitLab rides glab or the MR API (python stdlib, GL_TOKEN in
the environment — CI variables or the operator's shell, never the repo).
Every opening degrades to a manual hint: no forge, no auth, no network —
the flow survives (the constitution keeps the manual door).

The transport deliberately does NOT go through gitwrap: gh/glab/curl are not
git, and gitwrap prepends `git` to everything it runs — that is why release's
auto-PR was silent on GitHub until now (task tooling/53's founding lesson).
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from jearless import gitwrap

_LABELS_FLAG = "--label"


def _run(args: list[str], cwd: Path) -> str | None:
    """Run a non-git CLI; stripped stdout on success, None on any failure."""
    try:
        proc = subprocess.run(
            args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False
        )
    except FileNotFoundError:
        return None  # the CLI is not installed — manual territory
    return proc.stdout.strip() if proc.returncode == 0 else None


def open_pr(
    cwd: Path, base: str, branch: str, title: str, body: str, labels: tuple[str, ...] = ()
) -> str | None:
    """Open the PR (GitHub via gh) or the MR (GitLab via the API). Returns the
    URL, or None — manual territory (the caller prints the hint). A missing
    label must not bury the PR: the labeled attempt falls back to unlabeled."""
    args = ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body]
    for label in labels:
        args += [_LABELS_FLAG, label]
    url = _run(args, cwd)
    if url is None and labels:
        url = _run(args[: -2 * len(labels)], cwd)
    if url:
        return url
    return _gitlab_mr(cwd, base, branch, title, body, labels)


def _gitlab_mr(
    cwd: Path, base: str, branch: str, title: str, body: str, labels: tuple[str, ...]
) -> str | None:
    """The GitLab MR API with python stdlib only: GL_TOKEN plus the CI
    variables (CI_API_V4_URL, CI_PROJECT_ID) — the CI context or the
    operator's shell provides them; nothing is read from the repo."""
    api = os.environ.get("CI_API_V4_URL")
    project = os.environ.get("CI_PROJECT_ID")
    token = os.environ.get("GL_TOKEN") or os.environ.get("GITLAB_TOKEN")
    if not (api and project and token):
        return None
    payload = json.dumps(
        {
            "source_branch": branch,
            "target_branch": base,
            "title": title,
            "description": body,
            "labels": ",".join(labels),
        }
    ).encode()
    request = urllib.request.Request(
        f"{api}/projects/{project}/merge_requests",
        data=payload,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None
    return data.get("web_url")


def registry_pr(
    cwd: Path,
    files: list[str],
    branch: str,
    title: str,
    body: str,
    label: str,
    base: str,
    trunk: str,
) -> bool:
    """Carry a staged registry edit to its own branch, commit, push, open the
    labeled PR (task tooling/53). Returns True when the PR opened; False =
    manual territory — the edit stays staged where the human can reach it.

    Nothing touches main: the branch carries the commit, the human merges.
    """
    if gitwrap.is_repo(cwd):
        rel = [os.path.relpath(os.path.join(str(cwd), str(item)), str(cwd)) for item in files]
        gitwrap.run(["add", *rel], cwd)
    origin_branch = gitwrap.out(["symbolic-ref", "--short", "HEAD"], cwd) if gitwrap.is_repo(cwd) else trunk
    try:
        gitwrap.run(["checkout", "-q", "-b", branch], cwd)
        rel = [os.path.relpath(os.path.join(str(cwd), str(item)), str(cwd)) for item in files]
        gitwrap.run(["commit", "-q", "-m", title, "--", *rel], cwd)
        gitwrap.run(["push", "-q", "-u", "origin", branch], cwd)
    except gitwrap.GitError as exc:
        print(f"jear: the branch ride failed ({exc}) — the edit stays staged; open the PR by hand")
        return False
    url = open_pr(cwd, base, branch, title, body, labels=(label,))
    if url:
        print(f"PR: {url}")
    else:
        print(f"open the PR by hand: {branch} -> {base}")
    if origin_branch and origin_branch != branch:
        gitwrap.run(["checkout", "-q", origin_branch], cwd)
    return url is not None
