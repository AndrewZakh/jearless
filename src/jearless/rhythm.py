"""rhythm: when does landed work happen (task tooling/57).

Team-level aggregate by default: commits per LOCAL weekday and per LOCAL
hour, recovered from the offsets stored inside the commits themselves
(%aI — the author's own wall clock at authoring). --no-merges --first-parent
on the trunk: landed work only, no merge-timestamp noise.

Per-author mode (an argument) is opt-in and serves ASSIGNMENT HINTS —
best-effort estimates from client clocks, never workload evidence (the
manifest: per-author rhythms may inform assignment; they are never workload
proof — the Peter-Friday-17:59 case: don't drop an urgent task into a dead
window).
"""

from collections import Counter
from datetime import datetime
from pathlib import Path

from jearless import config, gitwrap

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _rows(cwd: Path, ref: str, author: str | None) -> list[tuple[str, datetime]]:
    fmt = "%aN%x1f%aI"
    lines = gitwrap.lines(["log", "--first-parent", "--no-merges", f"--format={fmt}", ref], cwd)
    rows: list[tuple[str, datetime]] = []
    for line in lines:
        name, iso = line.split("\x1f", 1)
        if author and name.lower() != author.lower():
            continue
        rows.append((name, datetime.fromisoformat(iso)))
    return rows


def _histogram_line(title: str, keys: list[str], counts: Counter, width: int = 4) -> list[str]:
    out = [f"{title:<{width}}: " + " ".join(f"{k:>4}" for k in keys)]
    out.append(f"{'':<{width}}: " + " ".join(f"{counts.get(k, 0):>4}" for k in keys))
    return out


def _mermaid(hours: Counter) -> str:
    bars = ", ".join(str(hours.get(f"{h:02d}", 0)) for h in range(24))
    labels = ", ".join(f'"{h:02d}"' for h in range(24))
    peak = max(hours.values()) if hours else 0
    return (
        "xychart-beta\n"
        f'    title "commit rhythm by local hour"\n'
        f'    x-axis [{labels}]\n'
        f'    y-axis "commits" 0 --> {max(peak, 1)}\n'
        f"    bar [{bars}]"
    )


def run(cwd: Path, author: str | None = None) -> int:
    cfg = config.load(cwd)
    ref = f"origin/{cfg.trunk_ref}"
    rows = _rows(cwd, ref, author)
    if not rows:
        who = f" by '{author}'" if author else ""
        print(f"rhythm: no landed commits{who} on {ref}")
        return 0

    hours: Counter = Counter(f"{dt.hour:02d}" for _, dt in rows)
    weekdays: Counter = Counter(_WEEKDAYS[dt.weekday()] for _, dt in rows)

    print(f"rhythm: {len(rows)} landed commit(s)" + (f" by '{author}'" if author else ""))
    for i in (0, 12):
        for out in _histogram_line("hours", [f"{h:02d}" for h in range(i, i + 12)], hours):
            print(out)
    for out in _histogram_line("weekday", _WEEKDAYS, weekdays, width=7):
        print(out)

    print()
    print(_mermaid(hours))
    if author:
        print(
            "assignment hints — best-effort estimates from client clocks;"
            " never workload evidence"
        )
    return 0
