"""changelog: derived from merge commits between refs — printed, never stored (README).

Dry-run is the only mode: writing files is the release step's business (task tooling/9).
Re-merges collapse to the first arrival (task tooling/11): a task ships in the
version of its first merge, so a branch merged twice yields one entry, and a
task first merged before the range is not re-shipped by its re-merge.
"""

from pathlib import Path

from jearless import config, gitwrap, registry, state
from jearless.errors import JearlessError

_UNRELEASED = "Unreleased"

# Trailer-attributed entries carry no branch kind (the squash bridge: the
# forge's squash kills the branch name). "trailer" is not in DEFAULT_SECTIONS,
# so render routes the entries to "Other" — unless an adopter defines a
# "trailer" section deliberately.
_TRAILER_SECTION = "trailer"


def _records(cwd: Path, args: list[str]) -> list[list[str]]:
    """(sha, parents, subject, body) per commit, read in one walk.

    %B carries newlines, so the records terminate on NUL (probed live: git
    emits one record per commit, the body never contains the separators).
    """
    out = gitwrap.out([*args, "--format=tformat:%H%x1f%P%x1f%s%x1f%B%x00"], cwd)
    records = []
    for record in out.split("\x00"):
        record = record.strip("\n")
        if record.strip():
            records.append(record.split("\x1f", 3))
    return records


def _summary_for(reg: registry.Registry, project: str, num: int, slug: str | None) -> str:
    """The registry (union with archives) first; the branch slug is the fallback (README)."""
    for task in reg.tasks.get(project, []):
        if task.id == num:
            return task.summary
    return (slug or "task").replace("-", " ")


def _entries_from_history(
    cwd: Path, cfg: config.Config, reg: registry.Registry, range_args: list[str], from_tag: str | None
) -> tuple[dict[str, list[tuple[tuple[str, int], str]]], int, int]:
    """Merge commits → entries; dedupe keys on the BRANCH (task tooling/26).

    The same branch merged twice is a re-merge artifact (collapse, counted
    aloud). A DIFFERENT branch naming the same task — a declared re-take —
    is new work: it lands in its own kind's section (a fix in "Fixed") even
    when the task shipped before the range.

    Task tooling/64: attribution reads the full body. A ``Task: <project>/<id>``
    trailer (git's last paragraph) wins over the subject; the subject regexes
    stay the legacy fallback for real merges. A plain commit on the trunk's
    first-parent chain attributes ONLY by trailer — the squash bridge — its
    subject is never trusted.
    """
    known = {(t.project, t.id) for t in reg.all()}
    sections: dict[str, list[tuple[tuple[str, int], str]]] = {}
    skipped = 0
    remerged = 0
    seen: set[tuple[str, int, str]] = set()
    shipped_before: set[tuple[str, int, str]] = set()

    def _attr(subject: str, body: str, is_merge: bool):
        """(project, num, type, slug, dedupe-unit) — or None: unattributed."""
        tkey = state.task_trailer(body)
        if tkey and tkey in known:
            branch = state.branch_from_merge_subject(subject) if is_merge else None
            m = cfg.match_branch(branch) if branch else None
            if m and (m.group("project"), int(m.group("num"))) == tkey:
                # the subject agrees with the declaration: its kind is honest
                return (*tkey, m.group("type"), m.group("slug"), branch)
            return (*tkey, None, None, f"trailer:{tkey[0]}/{tkey[1]}")
        if is_merge:
            branch = state.branch_from_merge_subject(subject)
            m = cfg.match_branch(branch) if branch else None
            if m:
                key = (m.group("project"), int(m.group("num")))
                return (*key, m.group("type"), m.group("slug"), branch)
        return None

    def _enter(a) -> None:
        nonlocal remerged
        project, num, type_, slug, unit = a
        key = (project, num, unit)
        if key in shipped_before or key in seen:
            remerged += 1
            return
        seen.add(key)
        line = cfg.line_template.format(
            type=type_ or "",
            project=project,
            num=num,
            slug=slug or "",
            summary=_summary_for(reg, project, num, slug),
        )
        sections.setdefault(type_ or _TRAILER_SECTION, []).append(((project, num), line))

    if from_tag:
        for sha, parents, subject, body in _records(cwd, ["log", from_tag, "--merges"]):
            a = _attr(subject, body, is_merge=True)
            if a:
                shipped_before.add((a[0], a[1], a[4]))
        for sha, parents, subject, body in _records(
            cwd, ["log", "--first-parent", "--no-merges", from_tag]
        ):
            a = _attr(subject, body, is_merge=False)
            if a:
                shipped_before.add((a[0], a[1], a[4]))

    for sha, parents, subject, body in _records(cwd, ["log", *range_args, "--merges"]):
        a = _attr(subject, body, is_merge=True)
        if a is None:
            skipped += 1  # off-taxonomy merge: the visible hole, counted aloud
            continue
        _enter(a)
    for sha, parents, subject, body in _records(
        cwd, ["log", "--first-parent", "--no-merges", *range_args]
    ):
        a = _attr(subject, body, is_merge=False)
        if a is None:
            continue  # a plain commit without a trailer: doctor's business, not the changelog's
        _enter(a)
    return sections, skipped, remerged


def render(
    cwd: Path, from_tag: str | None = None, to_tag: str | None = None, header: str | None = None
) -> str:
    """The changelog as text; `header` overrides the section title (used by release)."""
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    # explicit tags = released ranges on main; no to_tag = the unreleased
    # view: the trunk together with every unpromoted family branch (task
    # tooling/67) — the newest sprint alone cannot see an older unpromoted
    # sibling's work. The header date reads the trunk tip (the release anchor).
    if to_tag:
        walk = [to_tag]
        date_ref = to_tag
    else:
        walk = cfg.integration_refs(cwd, "origin")
        date_ref = f"origin/{cfg.trunk_ref}"
    range_args = ([f"^{from_tag}"] if from_tag else []) + walk
    try:
        sections, skipped, remerged = _entries_from_history(cwd, cfg, reg, range_args, from_tag)
        date = gitwrap.out(["log", "-1", "--format=%cd", "--date=short", date_ref], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(f"cannot read history {range_args}: {exc}") from exc

    lines = ["# Changelog"]
    title = header or to_tag or _UNRELEASED
    lines.append(f"## {title} ({date})" if date else f"## {title}")
    for prefix, section_title in cfg.sections.items():
        entries = sorted(sections.pop(prefix, []))
        if not entries:
            continue
        lines.append(f"### {section_title}")
        lines.extend(f"- {line}" for _, line in entries)
    others = sorted((key, line) for entries in sections.values() for key, line in entries)
    if others:
        lines.append("### Other")
        lines.extend(f"- {line}" for _, line in others)
    if skipped:
        lines.append(f"# {skipped} off-taxonomy merge(s) skipped — the visible hole (README)")
    if remerged:
        lines.append(
            f"# {remerged} re-merge(s) collapsed — a task ships in the version of its first merge"
        )
    return "\n".join(lines) + "\n"


def run(cwd: Path, from_tag: str | None = None, to_tag: str | None = None) -> int:
    print(render(cwd, from_tag=from_tag, to_tag=to_tag), end="")
    return 0
