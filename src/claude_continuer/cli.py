"""CLI entry point."""

from __future__ import annotations

import argparse
import sys

from claude_continuer import __version__
from claude_continuer.inspect_cmd import run_inspect
from claude_continuer.modes import continue_mode
from claude_continuer.schedule import next_run_at, parse_time_string, sleep_until


def _cmd_continue(args: argparse.Namespace) -> int:
    if not args.now:
        if not args.at:
            print("Error: provide --at TIME or --now", file=sys.stderr)
            return 2
        hour, minute = parse_time_string(args.at)
        target = next_run_at(hour, minute, today_only=args.today_only)
        print(f"Waiting until {target.strftime('%Y-%m-%d %I:%M %p')}...")
        sleep_until(target)
        print("Scheduled time reached.")

    return continue_mode.run_continue()


def _cmd_inspect(args: argparse.Namespace) -> int:
    return run_inspect(max_depth=args.depth)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-continuer",
        description="Automate Claude Desktop when session time limits are reached.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    continue_parser = subparsers.add_parser(
        "continue",
        help="Switch to Code, open first recent chat, send 'continue'",
    )
    continue_parser.add_argument(
        "--at",
        metavar="TIME",
        help='Clock time to run, e.g. "4:20pm" or "7:30 am"',
    )
    continue_parser.add_argument(
        "--now",
        action="store_true",
        help="Run immediately without waiting",
    )
    continue_parser.add_argument(
        "--today-only",
        action="store_true",
        help="Fail if --at time already passed today (default: run tomorrow)",
    )
    continue_parser.set_defaults(func=_cmd_continue)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Dump Claude accessibility tree for debugging",
    )
    inspect_parser.add_argument(
        "--depth",
        type=int,
        default=6,
        help="Maximum tree depth (default: 6)",
    )
    inspect_parser.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
