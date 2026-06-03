"""Continue mode: Code tab → first recent chat → send 'continue'."""

from __future__ import annotations

import sys

from claude_continuer import claude_app


def run_continue() -> int:
    try:
        print("Launching / activating Claude...")
        app = claude_app.get_app_ref()

        print('Switching to "Code" tab...')
        claude_app.click_sidebar_item(app, claude_app.SIDEBAR_CODE)

        print("Selecting first chat in Recents...")
        claude_app.click_first_recent_chat(app)

        print('Sending "continue"...')
        claude_app.send_continue_message(app)

        print("Done.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Tip: run `claude-continuer inspect` to debug the UI tree.", file=sys.stderr)
        return 1
