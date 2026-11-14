"""sprint: the board computed on demand — fetch --prune, then the canonical join.

Bare `jear sprint` is a PURE view: peeking never writes. `--write [PATH]`
materializes the board as a markdown dashboard (task tooling/13), ./sprint.md
by default, with three cases: a missing file is created whole with jear:sprint
markers inside; markers present — only the chunk between them is replaced and
human text around stays untouchable; markers absent — refuse with a paste-ready
snippet, a human file can never be overwritten. The chunk carries a
generated-at · git@sha stamp: staleness is visible (a sha mismatch says the
report is stale). Writes happen only on content change — a no-op refresh
leaves the tree clean. Committing the refresh is the human's move: nothing
automatic writes to main.
"""

from datetime import datetime
from pathlib import Path

from jearless import config, gitwrap, registry, state
from jearless.errors import JearlessError

_SECTION_ORDER = (state.IN_PROGRESS, state.AVAILABLE, state.DONE)

DEFAULT_DASHBOARD = "sprint.md"
CHUNK_BEGIN = "<!-- jear:sprint:begin -->"
CHUNK_END = "<!-- jear:sprint:end -->"

_SNIPPET = f"{CHUNK_BEGIN}\n{CHUNK_END}"


def _print_terminal(view: state.SprintView) -> None:
    for section in _SECTION_ORDER:
        group = [tv for tv in view.tasks if tv.state == section]
        print(f"{section} ({len(group)}):")
        for tv in sorted(group, key=lambda tv: (tv.task.project, tv.task.id)):
            line = f"  {tv.task.project}/{tv.task.id}  {tv.task.summary}"
            if tv.task.story_points is not None:
                line += f" ({tv.task.story_points} pt)"
            if tv.task.depends_on:
                line += "  after " + ", ".join(f"{p}/{n}" for p, n in tv.task.depends_on)
            if tv.branch:
                line += f"  [{tv.branch}]"
            print(line)
    if view.unknown_branches:
        print(f"branches without a registry task ({len(view.unknown_branches)}):")
        for name in view.unknown_branches:
            print(f"  {name}")


def _markdown_block(view: state.SprintView, cwd: Path) -> str:
    try:
        sha = gitwrap.out(["rev-parse", "HEAD"], cwd)[:7]
    except gitwrap.GitError:
        sha = "no-commits"
    lines = [
        (
            f"_generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · git@{sha}"
            " — refresh: `jear sprint --write`_"
        ),
        "",
    ]
    for section in _SECTION_ORDER:
        group = [tv for tv in view.tasks if tv.state == section]
        lines.append(f"### {section} ({len(group)})")
        for tv in sorted(group, key=lambda tv: (tv.task.project, tv.task.id)):
            item = f"- **{tv.task.project}/{tv.task.id}** — {tv.task.summary}"
            if tv.task.story_points is not None:
                item += f" ({tv.task.story_points} pt)"
            if tv.task.depends_on:
                item += " · after " + ", ".join(f"{p}/{n}" for p, n in tv.task.depends_on)
            if tv.branch:
                item += f" · `{tv.branch}`"
            lines.append(item)
    if view.unknown_branches:
        lines.append(f"### branches without a registry task ({len(view.unknown_branches)})")
        lines.extend(f"- `{name}`" for name in view.unknown_branches)
    return "\n".join(lines)


def _refuse(path: Path) -> JearlessError:
    return JearlessError(
        f"{path.name}: no jear:sprint markers — a human file is never overwritten;"
        f" paste this snippet where the dashboard should live:\n{_SNIPPET}"
    )


def _write_dashboard(path: Path, block: str) -> str:
    """The three cases; returns a human-readable outcome."""
    if not path.exists():
        path.write_text(f"# Sprint\n\n{CHUNK_BEGIN}\n{block}\n{CHUNK_END}\n", encoding="utf-8")
        return (
            f"{path.name}: dashboard created — commit it to publish;"
            " the markers can be pasted into any md (e.g. README) to embed it"
        )
    text = path.read_text(encoding="utf-8")
    if text.count(CHUNK_BEGIN) != 1 or text.count(CHUNK_END) != 1:
        raise _refuse(path)
    begin = text.index(CHUNK_BEGIN)
    end = text.index(CHUNK_END)
    if end < begin:
        raise _refuse(path)
    old_block = text[begin + len(CHUNK_BEGIN) : end].strip("\n")
    # the stamp carries the minute — compare the board BODY, not the metadata:
    # a no-op refresh leaves the tree clean even across a minute boundary,
    # and the stamp then means "generated when the board last changed"
    old_body = "\n".join(old_block.splitlines()[2:])
    new_body = "\n".join(block.splitlines()[2:])
    if old_body == new_body:
        return f"{path.name}: up to date — the tree stays clean"
    new = text[: begin + len(CHUNK_BEGIN)] + "\n" + block + "\n" + text[end:]
    path.write_text(new, encoding="utf-8")
    return f"{path.name}: dashboard chunk refreshed — commit it to publish"


def run(cwd: Path, write: str | None = None, remote: str = "origin") -> int:
    try:
        gitwrap.run(["fetch", "--quiet", "--prune", remote], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(
            f"cannot fetch '{remote}': the sprint truth lives on the remote"
        ) from exc
    view = state.compute(cwd, config.load(cwd), registry.load(cwd), remote)
    if write is None:
        _print_terminal(view)
        return 0
    # resolve against the cwd PARAM, not the process cwd: an absolute PATH
    # replaces the prefix (pathlib semantics), a relative one anchors at the repo
    path = cwd / (write or DEFAULT_DASHBOARD)
    print(_write_dashboard(path, _markdown_block(view, cwd)))
    return 0
