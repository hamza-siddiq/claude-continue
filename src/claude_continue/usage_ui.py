"""Navigate Claude Desktop Settings → Usage and read limit state."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from claude_continue.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
    retry,
    show_menu,
)
from claude_continue.claude_app import (
    BUNDLE_ID,
    UI_READY_POLL_S,
    _element_label,
    _element_x,
    _element_y,
    _matches_label,
    _refresh_app_ref,
)
from claude_continue.mac_focus import activate_claude, keystroke_in_claude
from claude_continue.usage_parse import UsageSnapshot

# Bottom-left sidebar: profile / chevron (screen coords, not window-relative).
SIDEBAR_BOTTOM_Y_MIN = 600
SIDEBAR_LEFT_X_MAX = 400


def _collect_text_rows(app: Any) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for role in ("AXStaticText", "AXButton", "AXLink"):
        for element in app.findAllR(AXRole=role):
            label = _element_label(element)
            if label:
                rows.append((_element_y(element), label.strip()))
    rows.sort(key=lambda item: item[0])
    return rows


def _is_usage_page_visible(app: Any) -> bool:
    for _y, label in _collect_text_rows(app):
        low = label.lower()
        if low == "plan usage limits" or low == "all models":
            return True
    return False


def _is_settings_visible(app: Any) -> bool:
    for _y, label in _collect_text_rows(app):
        if label.strip().lower() == "settings":
            return True
    return False


def _click_labeled(app: Any, label: str, *, prefer_roles: tuple[str, ...] | None = None) -> None:
    roles = prefer_roles or ("AXMenuItem", "AXButton", "AXLink", "AXStaticText")
    for role in roles:
        for element in app.findAllR(AXRole=role):
            if _matches_label(element, label):
                press_element(element)
                time.sleep(0.6)
                return
    raise RuntimeError(f'Could not find control labeled "{label}"')


def _click_labeled_in_sidebar(app: Any, label: str) -> bool:
    """Click label in the left sidebar region; return True if found."""
    for role in ("AXMenuItem", "AXButton", "AXLink", "AXStaticText"):
        for element in app.findAllR(AXRole=role):
            if not _matches_label(element, label):
                continue
            if _element_x(element) > SIDEBAR_LEFT_X_MAX:
                continue
            press_element(element)
            time.sleep(0.6)
            return True
    return False


def _open_settings_via_menu_bar() -> None:
    keystroke_in_claude(
        'tell application "System Events" to tell process "Claude" to click '
        'menu item "Settings…" of menu 1 of menu bar item "Claude" of menu bar 1',
    )
    time.sleep(0.5)


def _open_settings_via_keyboard() -> None:
    keystroke_in_claude(
        'tell application "System Events" to keystroke "," using command down',
    )
    time.sleep(0.5)


def _find_profile_menu_control(app: Any) -> Any | None:
    """Profile avatar or chevron at the bottom of the left sidebar."""
    candidates: list[tuple[float, float, int, Any]] = []

    for role in ("AXButton", "AXImage", "AXGroup"):
        for element in app.findAllR(AXRole=role):
            y = _element_y(element)
            x = _element_x(element)
            if y < SIDEBAR_BOTTOM_Y_MIN or x > SIDEBAR_LEFT_X_MAX:
                continue
            label = _element_label(element).lower()
            if any(skip in label for skip in ("voice", "record", "extension", "file", "prompt")):
                continue
            try:
                has_menu = "ShowMenu" in element.getActions()
            except Exception:
                has_menu = False
            score = 0
            if has_menu:
                score += 10
            if role == "AXImage":
                score += 5
            if role == "AXButton" and not label:
                score += 3
            if label and len(label) < 30 and label not in ("settings", "usage", "recents"):
                score += 2
            if score > 0 or (role == "AXImage" and y > SIDEBAR_BOTTOM_Y_MIN):
                candidates.append((y, x, score, element))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[2], -item[0], item[1]))
    return candidates[0][3]


def _open_bottom_account_menu(app: Any) -> None:
    """Open the menu from the profile / arrow at the bottom of the sidebar."""
    control = _find_profile_menu_control(app)
    if control is None:
        raise RuntimeError("Could not find bottom sidebar menu (profile / arrow)")
    try:
        if "ShowMenu" in control.getActions():
            show_menu(control)
        else:
            press_element(control)
    except Exception:
        press_element(control)
    time.sleep(0.8)


def _prepare_ax_tree(app: Any) -> Any:
    running = find_running_app(BUNDLE_ID)
    if running is not None:
        enable_manual_accessibility(running.processIdentifier())
    time.sleep(0.5)
    return _refresh_app_ref()


def _navigate_to_usage(current: Any) -> Any:
    current = _prepare_ax_tree(current)

    if _is_usage_page_visible(current):
        return current

    if _click_labeled_in_sidebar(current, "Usage"):
        time.sleep(0.8)
        current = _refresh_app_ref()
        if _is_usage_page_visible(current):
            return current

    if _is_settings_visible(current) or _click_labeled_in_sidebar(current, "Settings"):
        time.sleep(0.8)
        current = _refresh_app_ref()
        _click_labeled(current, "Usage", prefer_roles=("AXButton", "AXLink"))
        time.sleep(0.8)
        current = _refresh_app_ref()
        if _is_usage_page_visible(current):
            return current

    _open_settings_via_keyboard()
    current = _refresh_app_ref()
    if _is_settings_visible(current) or _is_usage_page_visible(current):
        if not _is_usage_page_visible(current):
            _click_labeled(current, "Usage", prefer_roles=("AXButton", "AXLink"))
            time.sleep(0.8)
            current = _refresh_app_ref()
        if _is_usage_page_visible(current):
            return current

    _open_settings_via_menu_bar()
    current = _refresh_app_ref()
    if not _is_usage_page_visible(current):
        _click_labeled(current, "Usage", prefer_roles=("AXButton", "AXLink"))
        time.sleep(0.8)
        current = _refresh_app_ref()

    if not _is_usage_page_visible(current):
        _open_bottom_account_menu(current)
        current = _refresh_app_ref()
        _click_labeled(current, "Settings", prefer_roles=("AXMenuItem", "AXButton"))
        current = _refresh_app_ref()
        _click_labeled(current, "Usage", prefer_roles=("AXButton", "AXLink"))
        time.sleep(0.8)
        current = _refresh_app_ref()

    if not _is_usage_page_visible(current):
        raise RuntimeError("Usage page did not open (Plan usage limits not found)")
    return current


def open_usage_page(app: Any) -> Any:
    """Open Settings → Usage via sidebar menu, shortcuts, or menu bar."""

    def _open() -> Any:
        return _navigate_to_usage(app)

    return retry(_open, description="open Settings → Usage", attempts=3, delay=1.0)


def read_usage_snapshot(app: Any) -> UsageSnapshot:
    rows = _collect_text_rows(app)

    session_y: float | None = None
    all_models_y: float | None = None
    for y, text in rows:
        low = text.lower()
        if low == "current session":
            session_y = y
        elif low == "all models":
            all_models_y = y

    session_full = False
    all_models_full = False
    session_reset_text: str | None = None
    all_models_reset_text: str | None = None

    for y, text in rows:
        low = text.lower()
        if "100% used" not in low:
            continue
        if session_y is not None and all_models_y is not None:
            if session_y < y < all_models_y:
                session_full = True
            elif y > all_models_y:
                all_models_full = True
        elif session_y is not None and y > session_y:
            session_full = True
        elif all_models_y is not None and y > all_models_y:
            all_models_full = True

    for y, text in rows:
        low = text.lower()
        if not low.startswith("resets"):
            continue
        if "resets in" in low:
            if session_y is not None and y > session_y and (
                all_models_y is None or y < all_models_y
            ):
                session_reset_text = text
        elif all_models_y is not None and y >= all_models_y:
            all_models_reset_text = text

    if session_full and not session_reset_text:
        for _y, text in rows:
            if "resets in" in text.lower():
                session_reset_text = text
                break
    if all_models_full and not all_models_reset_text:
        for _y, text in rows:
            low = text.lower()
            if low.startswith("resets") and "resets in" not in low:
                all_models_reset_text = text
                break

    return UsageSnapshot(
        all_models_full=all_models_full,
        session_full=session_full,
        all_models_reset_text=all_models_reset_text,
        session_reset_text=session_reset_text,
    )


def wait_for_usage_rows(app: Any) -> Any:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        current = _prepare_ax_tree(app)
        rows = _collect_text_rows(current)
        if any("all models" in t.lower() for _y, t in rows):
            return current
        time.sleep(UI_READY_POLL_S)
    raise RuntimeError("Usage page did not show usage data in time")
