"""The CLI frame: subcommands per PLAN.md, phases 1-4.

In Phase 0 the subcommands are stubs, but empty states are handled by the
live modules, without crashing (Phase 0 DoD).
"""

import argparse
import sys
from pathlib import Path

from jearless import __version__
from jearless import add as add_mod
from jearless import archive as archive_mod
from jearless import board as board_mod
from jearless import burndown as burndown_mod
from jearless import changelog as changelog_mod
from jearless import doctor as doctor_mod
from jearless import find as find_mod
from jearless import graph as graph_mod
from jearless import log as log_mod
from jearless import plan as plan_mod
from jearless import reject as reject_mod
from jearless import release as release_mod
from jearless import report as report_mod
from jearless import retro as retro_mod
from jearless import sprint as sprint_mod
from jearless import take as take_mod
from jearless import timeline as timeline_mod
from jearless.errors import JearlessError

PHASES = {
    "add": 1,
    "take": 1,
    "sprint": 1,
    "changelog": 2,
    "doctor": 2,
    "timeline": 3,
    "retro": 3,
    "archive": 4,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jear",
        description="Fearless. Jira-less. Task tracking and changelog on bare git.",
    )
    parser.add_argument("--version", action="version", version=f"jearless {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("add", help="add a task to the registry (Phase 1)")
    p.add_argument("project")
    p.add_argument("summary")
    p.add_argument("--points", type=int, default=None)
    p.add_argument("--yes", action="store_true", help="skip the duplicate guard")
    p.add_argument(
        "--depends",
        action="append",
        default=None,
        metavar="TASK",
        help="link to an existing task: number or project/number (repeatable)",
    )

    p = sub.add_parser("take", help="take a task: branch + push (Phase 1)")
    p.add_argument("project")
    p.add_argument("id", type=int)
    p.add_argument(
        "--type",
        dest="kind",
        choices=["feature", "fix", "chore"],
        default="feature",
        help="the declared kind of work — the branch prefix (default feature)",
    )

    p = sub.add_parser(
        "log", help="the per-task journal: branches, commits, merges (task tooling/34)"
    )
    p.add_argument("project", help="project key, e.g. tooling")
    p.add_argument("id", type=int, help="task id")
    p.add_argument("--remote", default="origin")

    p = sub.add_parser("find", help="search across the eternal registry (task tooling/35)")
    p.add_argument("query", help="case-insensitive substring: summaries and descriptions")

    p = sub.add_parser(
        "reject", help="withdraw a task with a mandatory cause (task tooling/38)"
    )
    p.add_argument("project", help="project key, e.g. tooling")
    p.add_argument("id", type=int, help="task id")
    p.add_argument("cause", help="the withdrawal cause — required, non-empty")

    p = sub.add_parser("board", help="the kanban view over the canonical states (task tooling/25)")
    p.add_argument("--plan", default=None, metavar="FILE", help="board a specific sprint plan")
    p.add_argument("--all", action="store_true", help="ignore plans; board everything with column limits")
    p.add_argument("--limit", type=int, default=10, metavar="N", help="per-column cap for --all (default 10)")

    p = sub.add_parser(
        "burndown", help="sprint burn-down and the velocity trend via xychart (task tooling/27)"
    )
    p.add_argument("plan", nargs="?", default=None, metavar="FILE")
    p.add_argument("--trend", action="store_true", help="points done per sprint, across plans")

    p = sub.add_parser("sprint", help="sprint: registry × branches × merge log join (Phase 1)")
    p.add_argument(
        "--write",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="refresh the markdown dashboard (default ./sprint.md); bare sprint only prints",
    )
    p.add_argument(
        "--rag",
        default=None,
        metavar="PLAN_FILE",
        help="add the red-yellow-green view over the given sprint plan (task tooling/18)",
    )

    p = sub.add_parser(
        "changelog", help="changelog from merge commits (Phase 2); dry-run is the only mode"
    )
    p.add_argument("--from", dest="from_tag", default=None, metavar="TAG")
    p.add_argument("--to", dest="to_tag", default=None, metavar="TAG")
    p.add_argument("--dry-run", action="store_true", help="accepted for symmetry; always dry")

    p = sub.add_parser("doctor", help="diagnostics: unattributed commits etc. (Phase 2)")
    p.add_argument(
        "--acknowledge",
        nargs=2,
        metavar=("SHA", "CAUSE"),
        help="append a scar to the ledger — the sha must be on the trunk chain (task tooling/36)",
    )

    sub.add_parser("graph", help="mermaid flowchart of the registry's task links")

    p = sub.add_parser("timeline", help="actual timeline, mermaid (Phase 3)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true")
    group.add_argument("--snapshot", metavar="TAG")

    p = sub.add_parser("retro", help="plan versus actual (Phase 3)")
    p.add_argument("plan")

    p = sub.add_parser(
        "release", help="tag + changelog + timeline snapshot in one move (task tooling/9)"
    )
    p.add_argument("--tag", default=None, metavar="TAG")
    p.add_argument(
        "--finalize",
        metavar="TAG",
        help="phase 2: after the release PR merges, tag the merge commit (task tooling/51)",
    )

    p = sub.add_parser(
        "plan", help="validate a sprint plan contract and show it (task tooling/16)"
    )
    p.add_argument("file", metavar="FILE")
    p.add_argument("--gantt", action="store_true", help="render the derived gantt-of-the-plan")

    p = sub.add_parser("report", help="the release-time PM snapshot (task tooling/17)")
    p.add_argument("tag", metavar="TAG")

    p = sub.add_parser("archive", help="move done-as-of-tag tasks into archive_<tag>.yml")
    p.add_argument("tag", metavar="TAG")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command == "add":
            add_mod.add(cwd, args.project, args.summary, args.points, yes=args.yes, depends=args.depends)
            return 0
        if args.command == "graph":
            print(graph_mod.render(cwd), end="")
            return 0
        if args.command == "take":
            print(take_mod.take(cwd, args.project, args.id, kind=args.kind))
            return 0
        if args.command == "sprint":
            return sprint_mod.run(cwd, write=args.write, rag=args.rag)
        if args.command == "changelog":
            return changelog_mod.run(cwd, from_tag=args.from_tag, to_tag=args.to_tag)
        if args.command == "doctor":
            if args.acknowledge:
                return doctor_mod.acknowledge(cwd, args.acknowledge[0], args.acknowledge[1])
            return doctor_mod.run(cwd)
        if args.command == "timeline":
            return timeline_mod.run(cwd, snapshot=args.snapshot)
        if args.command == "retro":
            return retro_mod.run(cwd, Path(args.plan))
        if args.command == "release":
            if args.finalize:
                return release_mod.finalize(cwd, args.finalize)
            return release_mod.run(cwd, tag=args.tag)
        if args.command == "archive":
            return archive_mod.run(cwd, args.tag)
        if args.command == "log":
            return log_mod.run(cwd, args.project, args.id, remote=args.remote)
        if args.command == "find":
            return find_mod.run(cwd, args.query)
        if args.command == "reject":
            return reject_mod.run(cwd, args.project, args.id, args.cause)
        if args.command == "board":
            return board_mod.run(cwd, plan_path=args.plan, show_all=args.all, limit=args.limit)
        if args.command == "burndown":
            return burndown_mod.run(cwd, plan_path=args.plan, trend=args.trend)
        if args.command == "plan":
            return plan_mod.run(cwd, Path(args.file), gantt=args.gantt)
        if args.command == "report":
            return report_mod.run(cwd, args.tag)
        print(f"not implemented (Phase {PHASES[args.command]}) — see PLAN.md")
        return 0
    except JearlessError as exc:
        print(f"jear: {exc}", file=sys.stderr)
        return 1
