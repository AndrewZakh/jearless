"""changelog: derived from merge commits between refs — printed, never stored (README).

Dry-run is the only mode: writing files is the release step's business (task tooling/9).
"""

from pathlib import Path

from jearless import config, gitwrap, registry, state
from jearless.errors import JearlessError

_UNRELEASED = "Unreleased"


def _summary_for(reg: registry.Registry, project: str, num: int, slug: str | None) -> str:
    """The registry (union with archives) first; the branch slug is the fallback (README)."""
    for task in reg.tasks.get(project, []):
        if task.id == num:
            return task.summary
    return (slug or "task").replace("-", " ")


def _entries_from_history(
    cwd: Path, cfg: config.Config, reg: registry.Registry, rev_range: str
) -> tuple[dict[str, list[tuple[tuple[str, int], str]]], int]:
    sections: dict[str, list[tuple[tuple[str, int], str]]] = {}
    skipped = 0
    subjects = gitwrap.lines(["log", rev_range, "--merges", "--format=%s"], cwd)
    for subject in subjects:
        branch = state.branch_from_merge_subject(subject)
        m = cfg.match_branch(branch) if branch else None
        if not m:
            skipped += 1  # off-taxonomy merge: the visible hole, counted aloud
            continue
        project, num = m.group("project"), int(m.group("num"))
        summary = _summary_for(reg, project, num, m.group("slug"))
        line = cfg.line_template.format(
            type=m.group("type"),
            project=project,
            num=num,
            slug=m.group("slug") or "",
            summary=summary,
        )
        sections.setdefault(m.group("type"), []).append(((project, num), line))
    return sections, skipped


def render(
    cwd: Path, from_tag: str | None = None, to_tag: str | None = None, header: str | None = None
) -> str:
    """The changelog as text; `header` overrides the section title (used by release)."""
    cfg = config.load(cwd)
    reg = registry.load_all(cwd)
    to_ref = to_tag or "HEAD"
    rev_range = f"{from_tag}..{to_ref}" if from_tag else to_ref
    try:
        sections, skipped = _entries_from_history(cwd, cfg, reg, rev_range)
        date = gitwrap.out(["log", "-1", "--format=%cd", "--date=short", to_ref], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(f"cannot read history {rev_range}: {exc}") from exc

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
    return "\n".join(lines) + "\n"


def run(cwd: Path, from_tag: str | None = None, to_tag: str | None = None) -> int:
    print(render(cwd, from_tag=from_tag, to_tag=to_tag), end="")
    return 0
