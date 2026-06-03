"""macOS sleep/wake helpers for long scheduled waits."""

from __future__ import annotations

import subprocess
import sys

# Try to wake the system this many seconds before the target (when far away).
WAKE_LEAD_SECONDS = 120
# Do not call pmset when less than this remains (wake + continue is imminent).
MIN_WAKE_SCHEDULE_SECONDS = 300
# Prevent idle sleep in the final window so a running Mac does not doze off.
CAFFEINATE_LEAD_SECONDS = 180


def try_schedule_relative_wake(seconds: float) -> bool:
    """Ask macOS to wake in `seconds` from now (best-effort, no admin)."""
    secs = int(seconds)
    if secs < 60 or secs > 7 * 24 * 3600:
        return False
    proc = subprocess.run(
        ["pmset", "relative", "wake", str(secs)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def prevent_idle_sleep(seconds: float) -> None:
    """Keep the system awake for `seconds` using caffeinate (no admin)."""
    secs = max(1, int(seconds) + 15)
    subprocess.run(["caffeinate", "-i", "-t", str(secs)], check=False)


def format_wait_duration(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    if minutes < 90:
        return f"{minutes} min"
    hours, rem = divmod(minutes, 60)
    if rem:
        return f"{hours} hr {rem} min"
    return f"{hours} hr"


def notify_resume_after_sleep() -> None:
    print(
        "Resumed after sleep; continuing toward scheduled time...",
        file=sys.stderr,
    )
