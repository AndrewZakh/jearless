"""find: search across the eternal registry (task tooling/35).

The registry grows forever — finding "that task about unbound" must not be
a manual grep. `jear find <query>` — case-insensitive substring search
across summaries and descriptions of the live registry; prints
project/num, summary, story_points. Archives stay out of v1 (the union is
the report's business; find works on the working set). Pure view, nothing
stored.
"""

from pathlib import Path

from jearless import registry


def run(cwd: Path, query: str) -> int:
    reg = registry.load(cwd)
    needle = query.lower()
    matches = []
    for project, units in reg.tasks.items():
        for task in units:
            hay = f"{task.summary}\n{task.description}".lower()
            if needle in hay:
                matches.append((project, task))
    if not matches:
        print(f"no tasks matching '{query}'")
        return 0
    for project, task in sorted(matches, key=lambda m: (m[0], m[1].id)):
        pts = f" ({task.story_points} pt)" if task.story_points is not None else ""
        print(f"{project}/{task.id}{pts}  {task.summary}")
    print(f"{len(matches)} match(es)")
    return 0
