"""Parse clock times and sleep until the next occurrence."""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timedelta

from claude_continue.power import (
    CAFFEINATE_LEAD_SECONDS,
    MIN_WAKE_SCHEDULE_SECONDS,
    WAKE_LEAD_SECONDS,
    format_wait_duration,
    notify_resume_after_sleep,
    prevent_idle_sleep,
    try_schedule_relative_wake,
)

_TIME_RE = re.compile(
    r"^\s*"
    r"(?P<hour>\d{1,2})"
    r"(?::(?P<minute>\d{1,2}))?"
    r"\s*"
    r"(?P<ampm>am|pm)?"
    r"\s*$",
    re.IGNORECASE,
)


def parse_time_string(text: str) -> tuple[int, int]:
    """Parse strings like '4:20pm', '7:30 am', '16:20'."""
    match = _TIME_RE.match(text.strip())
    if not match:
        raise ValueError(
            f'Invalid time "{text}". Use formats like 4:20pm, 7:30 am, or 16:20.'
        )

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = (match.group("ampm") or "").lower()

    if minute < 0 or minute > 59:
        raise ValueError("Minute must be between 0 and 59")

    if ampm:
        if hour < 1 or hour > 12:
            raise ValueError("Hour must be between 1 and 12 when using am/pm")
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        raise ValueError("Hour must be between 0 and 23 for 24-hour format")

    return hour, minute


def next_run_at(
    hour: int,
    minute: int,
    *,
    today_only: bool = False,
    now: datetime | None = None,
) -> datetime:
    """Return the next datetime at the given local clock time."""
    now = now or datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        if today_only:
            raise ValueError(
                f"Time {hour:02d}:{minute:02d} has already passed today."
            )
        candidate += timedelta(days=1)
    return candidate


def _wake_seconds_before_target(remaining: float) -> float:
    """Seconds from now until we want the system to wake (before final caffeinate)."""
    return max(WAKE_LEAD_SECONDS, remaining - CAFFEINATE_LEAD_SECONDS)


def sleep_until(target: datetime) -> None:
    """Block until `target`, allowing the Mac to sleep most of the wait.

    Does not keep the Mac awake for the whole wait. When far from the target,
    requests a one-time system wake via pmset (best-effort). In the last few
    minutes, uses caffeinate so an awake Mac does not idle-sleep. After system
    sleep, resumes when the process runs again; if the target passed during
    sleep, returns immediately.
    """
    wake_requested = False
    last_tick = datetime.now()

    while True:
        now = datetime.now()
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            return

        tick_gap = (now - last_tick).total_seconds()
        if tick_gap > 90:
            notify_resume_after_sleep()
            wake_requested = False

        if (
            not wake_requested
            and remaining >= MIN_WAKE_SCHEDULE_SECONDS
        ):
            wake_in = _wake_seconds_before_target(remaining)
            if try_schedule_relative_wake(wake_in):
                print(
                    f"Scheduled system wake in {format_wait_duration(wake_in)} "
                    f"(Mac may sleep until then).",
                    file=sys.stderr,
                )
                wake_requested = True

        if remaining <= CAFFEINATE_LEAD_SECONDS:
            prevent_idle_sleep(remaining)
            while (target - datetime.now()).total_seconds() > 0:
                time.sleep(0.25)
            return

        last_tick = now
        chunk = min(remaining - CAFFEINATE_LEAD_SECONDS, 60)
        time.sleep(max(chunk, 0.25))
