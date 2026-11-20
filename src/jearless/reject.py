"""reject: withdraw a recorded task with a mandatory cause (task tooling/38).

The mirror of `doctor --acknowledge` (36): validate, require the
explanation, write. The registry stays eternal — the entry keeps its
points and history; the state join derives REJECTED from the field.
Revival is reversible: remove the field -> available again; git remembers
the whole story. The tool edits the file (the ledger precedent —
sanctioned for direct edits); the human commits (the charter: nothing
automatic writes to main).
"""

from pathlib import Path

from ruamel.yaml import YAML

from jearless import gitwrap, registry
from jearless.add import GUIDANCE_HINT
from jearless.errors import JearlessError


def run(cwd: Path, project: str, num: int, cause: str, remote: str = "origin") -> int:
    reg = registry.load(cwd)
    task = next((t for t in reg.all() if (t.project, t.id) == (project, num)), None)
    if task is None:
        raise JearlessError(f"{project}/{num}: no such task in the registry")
    if task.rejected:
        raise JearlessError(f"{project}/{num}: already rejected — {task.rejected}")
    cause = cause.strip()
    if not cause:
        raise JearlessError("the cause is required — a bare rejection is invisible debt")
    reg_path = reg.path
    if reg_path is None:
        raise JearlessError("the registry file is not resolved — nothing to edit")

    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(reg_path)
    entries = data["tasks"][project]
    entry = next(e for e in entries if e["id"] == num)
    entry["rejected"] = cause
    with reg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh)

    gitwrap.run(["add", str(reg_path)], cwd)
    print(
        f"{project}/{num} rejected — cause: {cause}\n"
        f"the registry edit is staged; " + GUIDANCE_HINT + "\n"
        "(revival: remove the field -> available again; git remembers)"
    )
    return 0
