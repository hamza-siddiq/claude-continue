"""Resolve run time from Usage page or prompt the user."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Literal

from claude_continue.claude_app import get_app_ref
from claude_continue.schedule import sleep_until
from claude_continue.usage_parse import (
    UsageNotLimitedError,
    run_at_from_snapshot,
)
from claude_continue.usage_ui import open_usage_page, read_usage_snapshot, wait_for_usage_rows

ScheduleOutcome = Literal["run_now", "cancelled"]


def prompt_run_now() -> ScheduleOutcome:
    try:
        answer = input("Usage is not at 100%. Run continue now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return "cancelled"
    if answer in ("y", "yes"):
        return "run_now"
    return "cancelled"


def resolve_run_time_from_usage(*, manual_at: str | None = None) -> datetime | ScheduleOutcome:
    """
    If manual_at is set, parse that clock time.
    Otherwise open Usage, read bars, and return when to run (or prompt).
    """
    if manual_at:
        from claude_continue.schedule import next_run_at, parse_time_string

        hour, minute = parse_time_string(manual_at)
        return next_run_at(hour, minute)

    app = get_app_ref()
    app = open_usage_page(app)
    app = wait_for_usage_rows(app)
    snapshot = read_usage_snapshot(app)

    print(
        f"Usage: all_models={'100%' if snapshot.all_models_full else 'ok'}, "
        f"session={'100%' if snapshot.session_full else 'ok'}"
    )
    if snapshot.all_models_reset_text:
        print(f"  All models reset: {snapshot.all_models_reset_text}")
    if snapshot.session_reset_text:
        print(f"  Session reset: {snapshot.session_reset_text}")

    try:
        run_at = run_at_from_snapshot(snapshot)
        print(f"Scheduled for {run_at.strftime('%Y-%m-%d %I:%M %p')}")
        return run_at
    except UsageNotLimitedError:
        return prompt_run_now()


def wait_until_run(*, manual_at: str | None = None) -> ScheduleOutcome:
    """Block until the resolved run time; return whether to proceed."""
    outcome = resolve_run_time_from_usage(manual_at=manual_at)
    if outcome == "cancelled":
        print("Cancelled.", file=sys.stderr)
        return "cancelled"
    if outcome == "run_now":
        return "run_now"
    sleep_until(outcome)
    print("Scheduled time reached.")
    return "run_now"
