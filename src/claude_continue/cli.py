"""CLI entry point."""

from __future__ import annotations

import argparse
import sys

from claude_continue import __version__
from claude_continue.claude_app import ContinueTarget
from claude_continue.inspect_cmd import run_inspect
from claude_continue.mac_focus import suppress_python_dock_icon
from claude_continue.modes import continue_mode, enter_mode
from claude_continue.usage_schedule import wait_until_run


def _add_schedule_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--at",
        metavar="TIME",
        help='Override: run at clock time, e.g. "4:20pm" (default: read Usage page)',
    )
    parser.add_argument(
        "--allow-sleep",
        action="store_true",
        help=(
            "Allow macOS idle sleep while waiting. If macOS refuses the wake "
            "schedule, the run may wait until you wake the Mac."
        ),
    )


def _cmd_run(args: argparse.Namespace) -> int:
    outcome = wait_until_run(manual_at=args.at, allow_sleep=args.allow_sleep)
    if outcome == "cancelled":
        return 1
    return continue_mode.run_continue(target=args.target)


def _cmd_run_enter(args: argparse.Namespace) -> int:
    outcome = wait_until_run(manual_at=args.at, allow_sleep=args.allow_sleep)
    if outcome == "cancelled":
        return 1
    return enter_mode.run_enter()


def _cmd_inspect(args: argparse.Namespace) -> int:
    return run_inspect(
        max_depth=args.depth,
        sidebar=args.sidebar,
        usage=args.usage,
        settings_nav=args.settings_nav,
    )


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
    suppress_python_dock_icon()
    parser = argparse.ArgumentParser(
        prog="claude-continue",
        description=(
            "Continue Claude Desktop Code or Chat sessions when limits are reached. "
            "Without --at, reads Settings → Usage to decide when to run."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _make_run_parser(
        subparsers,
        "code",
        "code",
        "Code tab: schedule from Usage (or --at), then send 'continue'",
    )
    _make_run_parser(
        subparsers,
        "chat",
        "chat",
        "Chat tab: schedule from Usage (or --at), then send 'continue'",
    )

    enter_parser = subparsers.add_parser(
        "enter",
        help=(
            "Schedule from Usage (or --at), then press Enter in the visible "
            "prompt (no navigation, no typing)"
        ),
    )
    _add_schedule_args(enter_parser)
    enter_parser.set_defaults(func=_cmd_run_enter)

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
    inspect_parser.add_argument(
        "--usage",
        action="store_true",
        help="Open Settings → Usage and print detected limits (debug)",
    )
    inspect_parser.add_argument(
        "--settings-nav",
        action="store_true",
        help="List Settings sidebar nav targets (open Settings first)",
    )
    inspect_parser.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
