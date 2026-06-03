"""Parse clock times and sleep until the next occurrence."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta


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


def sleep_until(target: datetime) -> None:
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 60))
