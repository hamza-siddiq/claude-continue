"""Enter mode: focus visible filled prompt and press Return (no navigation)."""

from __future__ import annotations

import sys
import time

from claude_continue import claude_app

ENTER_ATTEMPT_COUNT = 3
ENTER_RETRY_GAPS_S = (30, 60)


def run_enter_once() -> int:
    print("Launching / activating Claude...")
    app = claude_app.get_app_ref_minimal()

    print("Pressing Enter in visible prompt...")
    claude_app.send_enter_only(app)

    print("Done.")
    return 0


def run_enter() -> int:
    """Press Enter up to three times with 30s / 1min gaps after the scheduled time."""
    last_code = 1
    for attempt in range(1, ENTER_ATTEMPT_COUNT + 1):
        if attempt > 1:
            gap = ENTER_RETRY_GAPS_S[attempt - 2]
            print(f"Waiting {gap}s before attempt {attempt}/{ENTER_ATTEMPT_COUNT}...")
            time.sleep(gap)

        print(f"Enter attempt {attempt}/{ENTER_ATTEMPT_COUNT}...")
        try:
            last_code = run_enter_once()
            if last_code == 0:
                if attempt > 1:
                    print(f"Succeeded on attempt {attempt}.")
                return 0
        except Exception as exc:
            last_code = 1
            print(f"Error: {exc}", file=sys.stderr)
            if attempt < ENTER_ATTEMPT_COUNT:
                print("Will retry.", file=sys.stderr)
            else:
                print(
                    "Tip: run `claude-continue inspect` to debug the UI tree.",
                    file=sys.stderr,
                )

    return last_code
