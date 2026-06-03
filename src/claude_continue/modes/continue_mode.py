"""Continue mode: sidebar tab → first Recents chat → send 'continue'."""

from __future__ import annotations

import sys
import time

from claude_continue import claude_app
from claude_continue.claude_app import ContinueTarget

# After the scheduled time: 3 attempts, waiting 30s then 60s before retries 2 and 3
# (third attempt lands ~90s after the first).
CONTINUE_ATTEMPT_COUNT = 3
CONTINUE_RETRY_GAPS_S = (30, 60)


def run_continue_once(*, target: ContinueTarget = "code") -> int:
    tab = claude_app.target_to_sidebar_tab(target)

    print("Launching / activating Claude...")
    app = claude_app.get_app_ref()

    print(f'Switching to "{tab}" tab (from other tabs if needed)...')
    claude_app.ensure_tab(app, tab)

    print(f"Selecting first {tab} chat in Recents (skipping Pinned)...")
    app = claude_app.click_first_recent_chat(app, tab=tab)

    print('Sending "continue"...')
    claude_app.send_continue_message(app, tab=tab)

    print("Done.")
    return 0


def run_continue(*, target: ContinueTarget = "code") -> int:
    """Run continue up to three times with 30s / 1min gaps after the scheduled time."""
    last_code = 1
    for attempt in range(1, CONTINUE_ATTEMPT_COUNT + 1):
        if attempt > 1:
            gap = CONTINUE_RETRY_GAPS_S[attempt - 2]
            print(f"Waiting {gap}s before attempt {attempt}/{CONTINUE_ATTEMPT_COUNT}...")
            time.sleep(gap)

        print(f"Continue attempt {attempt}/{CONTINUE_ATTEMPT_COUNT}...")
        try:
            last_code = run_continue_once(target=target)
            if last_code == 0:
                if attempt > 1:
                    print(f"Succeeded on attempt {attempt}.")
                return 0
        except Exception as exc:
            last_code = 1
            print(f"Error: {exc}", file=sys.stderr)
            if attempt < CONTINUE_ATTEMPT_COUNT:
                print("Will retry.", file=sys.stderr)
            else:
                print(
                    "Tip: run `claude-continue inspect` to debug the UI tree.",
                    file=sys.stderr,
                )

    return last_code
