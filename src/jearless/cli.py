"""CLI-рама: подкоманды по PLAN.md, фазы 1–4.

В Ф0 подкоманды — заглушки, но пустые состояния обрабатываются живыми
модулями, без падений (DoD Ф0).
"""

import argparse
import sys
from pathlib import Path

from jearless import __version__, registry
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
        description="Fearless. Jira-less. Задачи и чейнджлог на голом гите.",
    )
    parser.add_argument("--version", action="version", version=f"jearless {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="КОМАНДА")

    p = sub.add_parser("add", help="добавить задачу в реестр (Ф1)")
    p.add_argument("project")
    p.add_argument("summary")
    p.add_argument("--points", type=int, default=None)

    p = sub.add_parser("take", help="взять задачу: ветка + push (Ф1)")
    p.add_argument("project")
    p.add_argument("id", type=int)

    sub.add_parser("sprint", help="спринт: джойн реестр × ветки × merge-лог (Ф1)")

    p = sub.add_parser("changelog", help="чейнджлог из merge-коммитов (Ф2)")
    p.add_argument("--from", dest="from_tag", default=None, metavar="ТЕГ")
    p.add_argument("--to", dest="to_tag", default=None, metavar="ТЕГ")
    p.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor", help="диагностика: безатрибутные коммиты и пр. (Ф2)")

    p = sub.add_parser("timeline", help="таймлайн факта, mermaid (Ф3)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true")
    group.add_argument("--snapshot", metavar="ТЕГ")

    p = sub.add_parser("retro", help="план против факта (Ф3)")
    p.add_argument("plan")

    sub.add_parser("archive", help="вынос done-задач (Ф4, по триггеру)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command == "sprint":
            # Ф0: живой проба пустых состояний — реестра может не быть вовсе.
            reg = registry.load(cwd)
            print(f"не реализовано (Фаза {PHASES['sprint']}); реестр: {reg.count()} задач")
            return 0
        print(f"не реализовано (Фаза {PHASES[args.command]}) — см. PLAN.md")
        return 0
    except JearlessError as exc:
        print(f"jear: {exc}", file=sys.stderr)
        return 1
