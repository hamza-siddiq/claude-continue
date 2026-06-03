"""CLI entry point."""

from __future__ import annotations

import argparse
import sys

from claude_continue import __version__
from claude_continue.claude_app import ContinueTarget
from claude_continue.inspect_cmd import run_inspect
from claude_continue.modes import continue_mode
from claude_continue.schedule import next_run_at, parse_time_string, sleep_until


def _add_schedule_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--at",
        metavar="TIME",
        help='Clock time to run, e.g. "4:20pm" or "7:30 am"',
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run immediately without waiting",
    )
    parser.add_argument(
        "--today-only",
        action="store_true",
        help="Fail if --at time already passed today (default: run tomorrow)",
    )


def _cmd_run(args: argparse.Namespace) -> int:
    if not args.now:
        if not args.at:
            print("Error: provide --at TIME or --now", file=sys.stderr)
            return 2
        hour, minute = parse_time_string(args.at)
        target_time = next_run_at(hour, minute, today_only=args.today_only)
        print(f"Waiting until {target_time.strftime('%Y-%m-%d %I:%M %p')}...")
        sleep_until(target_time)
        print("Scheduled time reached.")

    return continue_mode.run_continue(target=args.target)


def _cmd_inspect(args: argparse.Namespace) -> int:
    return run_inspect(max_depth=args.depth, sidebar=args.sidebar)


def _make_run_parser(
    subparsers: argparse._SubParsersAction,
    name: str,
    target: ContinueTarget,
    help_text: str,
) -> None:
    parser = subparsers.add_parser(name, help=help_text)
    _add_schedule_args(parser)
    parser.set_defaults(func=_cmd_run, target=target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-continue",
        description="Automate Claude Desktop when session time limits are reached.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _make_run_parser(
        subparsers,
        "code",
        "code",
        "Code tab: first Recents chat, send 'continue' in Prompt",
    )
    _make_run_parser(
        subparsers,
        "chat",
        "chat",
        "Chat tab: first Recents chat, send 'continue' in the composer",
    )

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
    inspect_parser.add_argument(
        "--sidebar",
        action="store_true",
        help="List sidebar chat row candidates (for debugging Recents selection)",
    )
    inspect_parser.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
