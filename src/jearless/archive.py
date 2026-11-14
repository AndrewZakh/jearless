"""archive: move done-as-of-tag tasks out of tasks.yml (task tooling/8).

The cut is by RELEASE TAG — the same frozen boundary as the changelog and the
timeline snapshot. Tasks merged before the tag leave the registry into
archive_<tag>.yml; available/in_progress always live in tasks.yml; identity
for analytics is the union of the registry and the archives (load_all).
The move is a human-run step: the tool writes both files, the human commits —
nothing automatic writes to main. An archive file is frozen: one tag, one file.
"""

from pathlib import Path

from ruamel.yaml import YAML

from jearless import config, gitwrap, registry, timeline
from jearless.errors import JearlessError

ARCHIVE_PREFIX = "archive_"

_HEADER = (
    "# Frozen history: tasks done as of {tag}, moved out of tasks.yml by `jear archive {tag}`.\n"
    "# Identity for analytics is the union of tasks.yml and the archives (registry.load_all).\n"
)


def run(cwd: Path, tag: str) -> int:
    # an archive file is frozen — refused if it exists in either home
    legacy_path = cwd / f"{ARCHIVE_PREFIX}{tag}.yml"
    home_path = cwd / registry.HOMEDIR / f"{ARCHIVE_PREFIX}{tag}.yml"
    if home_path.exists() or legacy_path.exists():
        raise JearlessError(f"{home_path.name} already exists — an archive file is frozen")
    try:
        gitwrap.run(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], cwd)
    except gitwrap.GitError as exc:
        raise JearlessError(f"no tag {tag}: the cut is by a release tag ({exc})") from exc

    cfg = config.load(cwd)
    registry.load_all(cwd)  # validates the union before any surgery
    done = {(b.project, b.num) for b in timeline.merge_bars(cwd, cfg, registry.load_all(cwd), tag)}

    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100000

    reg_path = registry.load(cwd).path
    if reg_path is None or not reg_path.exists():
        print(f"nothing done as of {tag} — the registry is untouched")
        return 0
    data = yaml.load(reg_path)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
        raise JearlessError(f"{registry.REGISTRY_NAME}: expected the 'tasks:' mapping")

    moved: dict[str, list] = {}
    for project, entries in data["tasks"].items():
        keep, gone = [], []
        for entry in entries:
            key = (str(project), entry["id"]) if isinstance(entry, dict) and "id" in entry else None
            (gone if key in done else keep).append(entry)
        if gone:
            moved[str(project)] = gone
            entries[:] = keep  # in place: ruamel formatting of the rest survives
    if not moved:
        print(f"nothing done as of {tag} — the registry is untouched")
        return 0

    yaml.dump(data, reg_path)
    home_path.parent.mkdir(parents=True, exist_ok=True)
    with home_path.open("w", encoding="utf-8") as fh:
        fh.write(_HEADER.format(tag=tag))
        yaml.dump({"tasks": moved}, fh)

    total = sum(len(entries) for entries in moved.values())
    print(f"archived {total} task(s) done as of {tag} -> {home_path.name}:")
    for project, entries in sorted(moved.items()):
        print(f"  {project}: " + ", ".join(str(entry["id"]) for entry in entries))
    print("commit both files to main — the union (registry + archives) keeps every identity")
    return 0
