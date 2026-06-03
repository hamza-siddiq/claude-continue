"""Claude Desktop app lifecycle and UI element discovery."""

from __future__ import annotations

import subprocess
import time
from typing import Any

import atomacos

from claude_continuer.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
    retry,
)

BUNDLE_ID = "com.anthropic.claudefordesktop"
APP_NAME = "Claude"

SIDEBAR_CODE = "Code"
SIDEBAR_RECENTS = "Recents"
MESSAGE_TEXT = "continue"


def launch_if_needed() -> None:
    if find_running_app(BUNDLE_ID):
        return
    subprocess.run(["open", "-a", APP_NAME], check=True)
    for _ in range(30):
        if find_running_app(BUNDLE_ID):
            return
        time.sleep(0.5)
    raise RuntimeError("Claude did not start within 15 seconds")


def activate() -> None:
    subprocess.run(
        ["osascript", "-e", f'tell application "{APP_NAME}" to activate'],
        check=True,
    )
    time.sleep(0.8)


def get_app_ref() -> Any:
    launch_if_needed()
    activate()
    running = find_running_app(BUNDLE_ID)
    if running is None:
        raise RuntimeError("Claude is not running")
    enable_manual_accessibility(running.processIdentifier())
    time.sleep(0.3)
    app = atomacos.getAppRefByBundleId(BUNDLE_ID)
    if app is None:
        raise RuntimeError("Could not get accessibility reference for Claude")
    return app


def _matches_label(element: Any, label: str) -> bool:
    label_lower = label.lower()
    for attr in ("AXTitle", "AXDescription", "AXValue", "AXIdentifier"):
        value = get_attr(element, attr)
        if value and value.strip().lower() == label_lower:
            return True
    return False


def find_by_label(app: Any, label: str) -> Any | None:
    return app.findFirstR(
        AXTitle=label,
        AXDescription=label,
    ) or app.findFirstR(AXTitle=label) or app.findFirstR(AXDescription=label)


def click_sidebar_item(app: Any, label: str) -> None:
    def _click():
        element = find_by_label(app, label)
        if element is None:
            candidates = app.findAllR(AXRole="AXButton") + app.findAllR(
                AXRole="AXStaticText"
            )
            for candidate in candidates:
                if _matches_label(candidate, label):
                    element = candidate
                    break
        if element is None:
            raise RuntimeError(f'Sidebar item "{label}" not found')
        press_element(element)

    retry(_click, description=f'click sidebar "{label}"')


def _collect_rows(container: Any) -> list[Any]:
    rows: list[Any] = []
    for role in ("AXRow", "AXButton", "AXCell", "AXGroup"):
        try:
            rows.extend(container.findAllR(AXRole=role))
        except Exception:
            continue
    return rows


def click_first_recent_chat(app: Any) -> None:
    def _click():
        recents = find_by_label(app, SIDEBAR_RECENTS)
        if recents is None:
            raise RuntimeError(f'"{SIDEBAR_RECENTS}" section not found')

        parent = getattr(recents, "AXParent", None) or recents
        rows = _collect_rows(parent)
        if not rows:
            window = app.windows()[0] if app.windows() else app
            rows = _collect_rows(window)

        clickable = []
        for row in rows:
            title = get_attr(row, "AXTitle") or get_attr(row, "AXDescription")
            if not title or title.strip().lower() in (
                "recents",
                "code",
                "chat",
                "cowork",
            ):
                continue
            clickable.append(row)

        if not clickable:
            raise RuntimeError("No recent chats found under Recents")
        press_element(clickable[0])

    retry(_click, description="select first recent chat")


def send_continue_message(app: Any) -> None:
    def _send():
        composer = (
            app.findFirstR(AXRole="AXTextArea")
            or app.findFirstR(AXRole="AXTextField")
            or app.findFirstR(AXRole="AXComboBox")
        )
        if composer is None:
            raise RuntimeError("Message composer not found")

        try:
            composer.AXFocus = True
        except Exception:
            press_element(composer)

        time.sleep(0.2)

        try:
            composer.AXValue = MESSAGE_TEXT
        except Exception:
            composer.sendKeys(MESSAGE_TEXT)

        time.sleep(0.15)
        composer.sendKeys("\r")

    retry(_send, description="send continue message")
