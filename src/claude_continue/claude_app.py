"""Claude Desktop app lifecycle and UI element discovery."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Literal

import atomacos

from claude_continue.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
    retry,
)
from claude_continue.mac_focus import activate_claude

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

# Top nav pill row (Chat / Cowork / Code) — used when df-pill is not exposed yet on cold start.
SIDEBAR_PILL_Y_MIN = 150
SIDEBAR_PILL_Y_MAX = 230
SIDEBAR_PILL_X_MIN = 400

UI_READY_TIMEOUT_S = 45
UI_READY_POLL_S = 0.5

# Section headers and nav; pinned chats above Recents are excluded via y > recents_y.
SKIP_SIDEBAR_LABELS = frozenset(
    {
        "pinned",
        "recents",
        "new session",
        "new chat",
        "routines",
        "customize",
        "chat",
        "cowork",
        "code",
    }
)

CHAT_ROW_ROLES = ("AXButton", "AXLink", "AXRow", "AXCell")


def launch_if_needed() -> None:
    if find_running_app(BUNDLE_ID):
        return
    subprocess.run(["open", "-gj", "-a", APP_NAME], check=True)
    for _ in range(30):
        if find_running_app(BUNDLE_ID):
            return
        time.sleep(0.5)
    raise RuntimeError("Claude did not start within 15 seconds")


def activate() -> None:
    activate_claude()
    time.sleep(0.5)


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


def _refresh_app_ref() -> Any:
    app = atomacos.getAppRefByBundleId(BUNDLE_ID)
    if app is None:
        raise RuntimeError("Could not get accessibility reference for Claude")
    return app


def _is_top_nav_pill_candidate(element: Any) -> bool:
    y = _element_y(element)
    x = _element_x(element)
    return SIDEBAR_PILL_Y_MIN <= y <= SIDEBAR_PILL_Y_MAX and x >= SIDEBAR_PILL_X_MIN


def find_sidebar_tab(app: Any, label: str) -> Any | None:
    """Top nav pill (Chat / Cowork / Code), not other 'Code' buttons in the UI."""
    for element in app.findAllR(AXRole="AXButton"):
        if not _is_sidebar_pill(element):
            continue
        if _matches_label(element, label):
            return element
    # Cold start: web view may expose labels before df-pill classes are present.
    for element in app.findAllR(AXRole="AXButton"):
        if not _matches_label(element, label):
            continue
        if _is_top_nav_pill_candidate(element):
            return element
    return None


def wait_for_sidebar_ready(app: Any) -> Any:
    """Wait until Chat/Code nav pills exist (Electron UI after cold launch)."""
    deadline = time.monotonic() + UI_READY_TIMEOUT_S
    current = app
    while time.monotonic() < deadline:
        for name in (SIDEBAR_CHAT, SIDEBAR_COWORK, SIDEBAR_CODE):
            if find_sidebar_tab(current, name) is not None:
                time.sleep(0.4)
                return _refresh_app_ref()
        time.sleep(UI_READY_POLL_S)
        current = _refresh_app_ref()
    raise RuntimeError(
        "Claude sidebar did not load in time. "
        "Leave the main window open and try again."
    )


def get_app_ref() -> Any:
    launch_if_needed()
    activate()
    running = find_running_app(BUNDLE_ID)
    if running is None:
        raise RuntimeError("Claude is not running")
    enable_manual_accessibility(running.processIdentifier())
    time.sleep(0.5)
    app = _refresh_app_ref()
    return wait_for_sidebar_ready(app)


def is_sidebar_tab_active(tab: Any) -> bool:
    return get_attr(tab, "AXARIACurrent") == "page"


def _element_label(element: Any) -> str:
    for attr in ("AXTitle", "AXDescription", "AXValue"):
        value = get_attr(element, attr)
        if value and value.strip():
            return value.strip()
    try:
        for child in element.AXChildren or []:
            label = _element_label(child)
            if label:
                return label
    except Exception:
        pass
    return ""


def _sidebar_max_x(app: Any) -> float:
    try:
        windows = app.windows()
        if windows:
            return float(windows[0].AXSize.width) * 0.5
    except Exception:
        pass
    return 600.0


def _find_recents_element(app: Any) -> Any | None:
    for role in ("AXButton", "AXStaticText", "AXGroup"):
        for element in app.findAllR(AXRole=role):
            if _matches_label(element, SIDEBAR_RECENTS):
                return element
    return None


def _is_skipped_sidebar_label(label: str) -> bool:
    return label.strip().lower() in SKIP_SIDEBAR_LABELS


def _subtree_clickable_candidates(
    root: Any, *, max_x: float, min_y: float
) -> list[tuple[float, Any, str]]:
    found: list[tuple[float, Any, str]] = []

    def walk(node: Any) -> None:
        role = get_attr(node, "AXRole")
        label = _element_label(node)
        if role in CHAT_ROW_ROLES and label and not _is_skipped_sidebar_label(label):
            y, x = _element_y(node), _element_x(node)
            if y > min_y and x <= max_x:
                found.append((y, node, label))
        try:
            for child in node.AXChildren or []:
                walk(child)
        except Exception:
            pass

    walk(root)
    return found


def _collect_chats_after_recents(app: Any, recents: Any) -> list[tuple[float, Any, str]]:
    """Prefer siblings after the Recents node in the sidebar list."""
    max_x = _sidebar_max_x(app)
    min_y = _element_y(recents)
    parent = getattr(recents, "AXParent", None)
    if parent is not None:
        try:
            children = list(parent.AXChildren or [])
            idx = children.index(recents)
        except (ValueError, TypeError):
            idx = -1
        if idx >= 0:
            chats: list[tuple[float, Any, str]] = []
            for sibling in children[idx + 1 :]:
                chats.extend(
                    _subtree_clickable_candidates(
                        sibling, max_x=max_x, min_y=min_y - 1
                    )
                )
            if chats:
                chats.sort(key=lambda item: item[0])
                return chats

    return []


def _collect_chats_below_recents_y(
    app: Any, recents_y: float
) -> list[tuple[float, Any, str]]:
    max_x = _sidebar_max_x(app)
    chats: list[tuple[float, Any, str]] = []
    for role in CHAT_ROW_ROLES:
        for element in app.findAllR(AXRole=role):
            label = _element_label(element)
            if not label or _is_skipped_sidebar_label(label):
                continue
            y = _element_y(element)
            if y <= recents_y:
                continue
            if _element_x(element) > max_x:
                continue
            chats.append((y, element, label))
    chats.sort(key=lambda item: item[0])
    return chats


def _wait_for_recent_chats(app: Any) -> tuple[Any, list[tuple[float, Any, str]]]:
    """Poll until at least one chat appears below Recents."""
    deadline = time.monotonic() + UI_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        current = _refresh_app_ref()
        recents = _find_recents_element(current)
        if recents is None:
            time.sleep(UI_READY_POLL_S)
            continue
        chats = _collect_chats_after_recents(current, recents)
        if not chats:
            chats = _collect_chats_below_recents_y(current, _element_y(recents))
        if chats:
            return current, chats
        time.sleep(UI_READY_POLL_S)
    raise RuntimeError(
        "No recent chats found under Recents. "
        "Ensure the Chat or Code tab has conversation history visible."
    )


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

        running = find_running_app(BUNDLE_ID)
        if running is not None:
            enable_manual_accessibility(running.processIdentifier())
        time.sleep(0.5)

    retry(_ensure, description=f"switch to {tab} tab")


def click_first_recent_chat(app: Any, *, tab: SidebarTab) -> Any:
    """Open the first chat below Recents; skip Pinned section above Recents."""

    refreshed = app

    def _click() -> None:
        nonlocal refreshed
        ensure_tab(app, tab)
        refreshed, chats = _wait_for_recent_chats(app)
        press_element(chats[0][1])
        time.sleep(0.5)

    retry(_click, description="select first recent chat")
    return refreshed


def _press_return(composer: Any) -> None:
    """Submit via Return on the composer (avoid pyautogui — it steals Dock focus)."""
    activate_claude()
    try:
        composer.sendKeys("\r")
    except Exception:
        pass
    time.sleep(0.1)
    activate_claude()


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
        _press_return(composer)

    retry(_send, description="send continue message")


def target_to_sidebar_tab(target: ContinueTarget) -> SidebarTab:
    return "Code" if target == "code" else "Chat"
