"""Keep Claude focused and avoid bouncing the Python dock icon."""

from __future__ import annotations

import subprocess
import time

from AppKit import NSApplication, NSWorkspace

BUNDLE_ID = "com.anthropic.claudefordesktop"
APP_NAME = "Claude"

# NSApplicationActivationPolicyAccessory — no Dock tile for this CLI process.
_ACTIVATION_POLICY_ACCESSORY = 1
_ACTIVATE_IGNORE_OTHERS = 1 << 1


def suppress_python_dock_icon() -> None:
    """Hide the Terminal-launched Python icon so automation does not bounce the Dock."""
    try:
        NSApplication.sharedApplication().setActivationPolicy_(
            _ACTIVATION_POLICY_ACCESSORY
        )
    except Exception:
        pass


def activate_claude() -> None:
    """Bring Claude Desktop to the front without activating Python."""
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == BUNDLE_ID:
            app.activateWithOptions_(_ACTIVATE_IGNORE_OTHERS)
            time.sleep(0.25)
            return
    subprocess.run(["open", "-gj", "-a", APP_NAME], check=False)
    for _ in range(20):
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.bundleIdentifier() == BUNDLE_ID:
                app.activateWithOptions_(_ACTIVATE_IGNORE_OTHERS)
                time.sleep(0.25)
                return
        time.sleep(0.25)


def keystroke_in_claude(*applescript_body: str) -> None:
    """Run System Events keystrokes while Claude stays frontmost."""
    activate_claude()
    args = ["osascript", "-e", f'tell application "{APP_NAME}" to activate']
    for line in applescript_body:
        args.extend(["-e", line])
    subprocess.run(args, check=False)
    activate_claude()
