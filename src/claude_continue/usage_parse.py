"""Parse Claude Desktop usage / reset strings from the Settings → Usage page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

_RESET_COUNTDOWN_RE = re.compile(
    r"resets\s+in\s+"
    r"(?:(?P<hours>\d+)\s*hr)?\s*"
    r"(?:(?P<minutes>\d+)\s*min)?",
    re.IGNORECASE,
)

_RESET_WEEKDAY_TIME_RE = re.compile(
    r"resets\s+"
    r"(?:(?P<weekday>mon|tues|tue|wed|thurs|thu|fri|sat|sun)\w*\s+)?"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<ampm>am|pm)?",
    re.IGNORECASE,
)

_RESET_TIME_ONLY_RE = re.compile(
    r"resets\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UsageSnapshot:
    all_models_full: bool
    session_full: bool
    all_models_reset_text: str | None
    session_reset_text: str | None


def parse_countdown(text: str) -> timedelta:
    match = _RESET_COUNTDOWN_RE.search(text)
    if not match:
        raise ValueError(f'Could not parse countdown from "{text}"')
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    if hours == 0 and minutes == 0:
        raise ValueError(f'Could not parse countdown from "{text}"')
    return timedelta(hours=hours, minutes=minutes)


def _to_24h(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    ampm = ampm.lower()
    if ampm == "pm" and hour != 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour


def parse_reset_clock(text: str, *, now: datetime | None = None) -> datetime:
    """Parse strings like 'Resets Wed 12:00 PM' or 'Resets 9:30 PM'."""
    now = now or datetime.now()
    match = _RESET_WEEKDAY_TIME_RE.search(text) or _RESET_TIME_ONLY_RE.search(text)
    if not match:
        raise ValueError(f'Could not parse reset time from "{text}"')

    hour = _to_24h(int(match.group("hour")), match.group("ampm"))
    minute = int(match.group("minute"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    weekday = match.group("weekday") if match.lastindex and "weekday" in match.groupdict() else None
    if weekday:
        target = _WEEKDAYS[weekday[:3].lower()]
        days_ahead = (target - candidate.weekday()) % 7
        if days_ahead == 0 and candidate <= now:
            days_ahead = 7
        candidate = candidate + timedelta(days=days_ahead)
    elif candidate <= now:
        candidate += timedelta(days=1)

    return candidate


def run_at_from_snapshot(
    snapshot: UsageSnapshot,
    *,
    now: datetime | None = None,
) -> datetime:
    """Compute when to run continue from usage bars."""
    now = now or datetime.now()

    if snapshot.all_models_full:
        if not snapshot.all_models_reset_text:
            raise RuntimeError("All models is at 100% but no reset time was found on Usage page")
        return parse_reset_clock(snapshot.all_models_reset_text, now=now)

    if snapshot.session_full:
        if not snapshot.session_reset_text:
            raise RuntimeError("Session is at 100% but no reset countdown was found on Usage page")
        delta = parse_countdown(snapshot.session_reset_text)
        return now + delta + timedelta(minutes=1)

    raise UsageNotLimitedError("Neither all-models nor session usage is at 100%")


class UsageNotLimitedError(Exception):
    """Usage limits are not exhausted; caller should ask the user."""
