"""Continue mode: sidebar tab → first Recents chat → send 'continue'."""

from __future__ import annotations

import sys

from claude_continue import claude_app
from claude_continue.claude_app import ContinueTarget


def run_continue(*, target: ContinueTarget = "code") -> int:
    tab = claude_app.target_to_sidebar_tab(target)

    try:
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
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Tip: run `claude-continue inspect` to debug the UI tree.", file=sys.stderr)
        return 1
