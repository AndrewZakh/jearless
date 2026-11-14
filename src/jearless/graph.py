"""graph: the dependency view — a mermaid flowchart of the registry's depends_on links.

The links are frozen authorial facts (task tooling/12): the registry holds
them, the author owns them. Git knows no inter-task structure — that is why
this is a PLAN-side view, the gantt contract's sibling, not a timeline feature.
Mermaid's gantt cannot draw arrows, so this is a flowchart; nodes carry the
same project_num key as the gantt bars, so both views join on one id space.
"""

import re
from pathlib import Path

from jearless import registry


def _sanitize(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'["\[\]{}|]', " ", label)).strip()


def render(cwd: Path) -> str:
    reg = registry.load_all(cwd)
    registry.check_links(reg)  # the loud hole: unknown targets and cycles refuse the view
    lines = ["flowchart LR"]
    tasks = sorted(reg.all(), key=lambda t: (t.project, t.id))
    for task in tasks:
        label = _sanitize(f"{task.project}/{task.id}: {task.summary}")
        lines.append(f'    {task.project}_{task.id}["{label}"]')
    for task in tasks:
        for dep in task.depends_on:
            lines.append(f"    {task.project}_{task.id} --> {dep[0]}_{dep[1]}")
    return "\n".join(lines) + "\n"


def run(cwd: Path) -> int:
    print(render(cwd), end="")
    return 0
