"""Claude Desktop app lifecycle and UI element discovery."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Literal

import atomacos
from atomacos import keyboard as ax_keyboard

from claude_continue.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
    retry,
)

BUNDLE_ID = "com.anthropic.claudefordesktop"
APP_NAME = "Claude"

SIDEBAR_CODE = "Code"
SIDEBAR_CHAT = "Chat"
SIDEBAR_COWORK = "Cowork"
SIDEBAR_RECENTS = "Recents"
SIDEBAR_PINNED = "Pinned"
MESSAGE_TEXT = "continue"

SidebarTab = Literal["Chat", "Code"]
ContinueTarget = Literal["code", "chat"]

SIDEBAR_PILL_CLASS = "df-pill"
CODE_COMPOSER_DESCRIPTION = "Prompt"
CHAT_COMPOSER_HINT = "write your prompt"

SIDEBAR_MAX_X = 450

# Section headers and nav; pinned chats above Recents are excluded via y > recents_y.
SKIP_SIDEBAR_LABELS = frozenset(
    {
        "pinned",
        "recents",
        "new session",
        "routines",
        "customize",
        "chat",
        "cowork",
        "code",
    }
)


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


def _is_sidebar_pill(element: Any) -> bool:
    classes = getattr(element, "AXDOMClassList", None) or []
    if isinstance(classes, str):
        return SIDEBAR_PILL_CLASS in classes
    return SIDEBAR_PILL_CLASS in list(classes)


def _element_y(element: Any) -> float:
    try:
        return float(element.AXPosition.y)
    except Exception:
        return 0.0


def _element_x(element: Any) -> float:
    try:
        return float(element.AXPosition.x)
    except Exception:
        return 0.0


def find_sidebar_tab(app: Any, label: str) -> Any | None:
    """Top nav pill (Chat / Cowork / Code), not other 'Code' buttons in the UI."""
    for element in app.findAllR(AXRole="AXButton"):
        if not _is_sidebar_pill(element):
            continue
        if _matches_label(element, label):
            return element
    return None


def is_sidebar_tab_active(tab: Any) -> bool:
    return get_attr(tab, "AXARIACurrent") == "page"


def _find_recents_y(app: Any) -> float:
    for element in app.findAllR(AXRole="AXButton"):
        if _matches_label(element, SIDEBAR_RECENTS):
            return _element_y(element)
    raise RuntimeError(f'"{SIDEBAR_RECENTS}" section not found in sidebar')


def ensure_tab(app: Any, tab: SidebarTab) -> None:
    """Switch to Chat or Code via top nav pills if another tab is active."""

    def _ensure() -> None:
        target = find_sidebar_tab(app, tab)
        if target is None:
            raise RuntimeError(f'Sidebar tab "{tab}" not found')

        if is_sidebar_tab_active(target):
            return

        press_element(target)
        time.sleep(0.8)

        target = find_sidebar_tab(app, tab) or target
        if is_sidebar_tab_active(target):
            return

        press_element(target)
        time.sleep(0.8)

        if not is_sidebar_tab_active(target):
            active = []
            for name in (SIDEBAR_CHAT, SIDEBAR_COWORK, SIDEBAR_CODE):
                pill = find_sidebar_tab(app, name)
                if pill and is_sidebar_tab_active(pill):
                    active.append(name)
            raise RuntimeError(
                f'Could not switch to {tab} tab (still on: {", ".join(active) or "unknown"})'
            )

    retry(_ensure, description=f"switch to {tab} tab")


def click_first_recent_chat(app: Any, *, tab: SidebarTab) -> None:
    """Open the first chat below Recents; skip Pinned section above Recents."""

    def _click() -> None:
        ensure_tab(app, tab)
        time.sleep(0.4)

        # Pinned chats sit above the Recents header (y <= recents_y); only take y > recents_y.
        recents_y = _find_recents_y(app)

        chats: list[tuple[float, Any, str]] = []
        for element in app.findAllR(AXRole="AXButton"):
            title = get_attr(element, "AXTitle") or get_attr(element, "AXDescription")
            if not title:
                continue
            normalized = title.strip().lower()
            if normalized in SKIP_SIDEBAR_LABELS:
                continue
            y = _element_y(element)
            if y <= recents_y:
                continue
            if _element_x(element) > SIDEBAR_MAX_X:
                continue
            chats.append((y, element, title))

        chats.sort(key=lambda item: item[0])
        if not chats:
            raise RuntimeError(f"No recent {tab} chats found under Recents")
        press_element(chats[0][1])
        time.sleep(0.5)

    retry(_click, description="select first recent chat")


def _press_return() -> None:
    """Submit via Return; AXValue + element sendKeys often skip Enter."""
    ax_keyboard.press("return")
    time.sleep(0.1)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to key code 36',  # Return
        ],
        check=False,
    )


def find_code_composer(app: Any) -> Any | None:
    """Code tab composer ('Prompt'), not the Chat tab ('Write your prompt…')."""
    composer = app.findFirstR(
        AXRole="AXTextArea", AXDescription=CODE_COMPOSER_DESCRIPTION
    )
    if composer is not None:
        return composer

    candidates: list[Any] = []
    for role in ("AXTextArea", "AXTextField"):
        for element in app.findAllR(AXRole=role):
            desc = get_attr(element, "AXDescription").lower()
            if CHAT_COMPOSER_HINT in desc:
                continue
            if "prompt" in desc or CODE_COMPOSER_DESCRIPTION.lower() in desc:
                candidates.append(element)

    if not candidates:
        return None
    return max(candidates, key=_element_y)


def find_chat_composer(app: Any) -> Any | None:
    """Chat tab composer ('Write your prompt…')."""
    for role in ("AXTextArea", "AXTextField"):
        for element in app.findAllR(AXRole=role):
            desc = get_attr(element, "AXDescription").lower()
            if CHAT_COMPOSER_HINT in desc:
                return element
    return app.findFirstR(AXRole="AXTextArea")


def _find_composer(app: Any, tab: SidebarTab) -> Any | None:
    if tab == "Code":
        return find_code_composer(app)
    return find_chat_composer(app)


def send_continue_message(app: Any, *, tab: SidebarTab) -> None:
    def _send() -> None:
        time.sleep(0.3)

        composer = _find_composer(app, tab)
        if composer is None:
            if tab == "Code":
                hint = "Prompt field"
            else:
                hint = f'composer containing "{CHAT_COMPOSER_HINT}"'
            raise RuntimeError(
                f"{tab} tab composer not found (looked for {hint}). "
                f"Are you on the {tab} tab with a session open?"
            )

        press_element(composer)
        time.sleep(0.25)

        composer.sendKeys(MESSAGE_TEXT)
        time.sleep(0.2)
        _press_return()

    retry(_send, description="send continue message")


def target_to_sidebar_tab(target: ContinueTarget) -> SidebarTab:
    return "Code" if target == "code" else "Chat"
