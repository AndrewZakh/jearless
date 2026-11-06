"""The CLI frame: subcommands per PLAN.md, phases 1-4.

In Phase 0 the subcommands are stubs, but empty states are handled by the
live modules, without crashing (Phase 0 DoD).
"""

import argparse
import sys
from pathlib import Path

from jearless import __version__, registry
from jearless import add as add_mod
from jearless import take as take_mod
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

    p = sub.add_parser("take", help="take a task: branch + push (Phase 1)")
    p.add_argument("project")
    p.add_argument("id", type=int)

    sub.add_parser("sprint", help="sprint: registry × branches × merge log join (Phase 1)")

    p = sub.add_parser("changelog", help="changelog from merge commits (Phase 2)")
    p.add_argument("--from", dest="from_tag", default=None, metavar="TAG")
    p.add_argument("--to", dest="to_tag", default=None, metavar="TAG")
    p.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor", help="diagnostics: unattributed commits etc. (Phase 2)")

    p = sub.add_parser("timeline", help="actual timeline, mermaid (Phase 3)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true")
    group.add_argument("--snapshot", metavar="TAG")

    p = sub.add_parser("retro", help="plan versus actual (Phase 3)")
    p.add_argument("plan")

    sub.add_parser("archive", help="move done tasks out (Phase 4, on trigger)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command == "add":
            add_mod.add(cwd, args.project, args.summary, args.points)
            return 0
        if args.command == "take":
            print(take_mod.take(cwd, args.project, args.id))
            return 0
        if args.command == "sprint":
            # Phase 0: a live probe of the empty states — there may be no registry at all.
            reg = registry.load(cwd)
            print(f"not implemented (Phase {PHASES['sprint']}); registry: {reg.count()} tasks")
            return 0
        print(f"not implemented (Phase {PHASES[args.command]}) — see PLAN.md")
        return 0
    except JearlessError as exc:
        print(f"jear: {exc}", file=sys.stderr)
        return 1
