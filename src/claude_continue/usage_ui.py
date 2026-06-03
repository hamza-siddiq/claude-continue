"""Navigate Claude Desktop Settings → Usage and read limit state."""

from __future__ import annotations

import time
from typing import Any

from claude_continue.ax import get_attr, press_element, retry
from claude_continue.claude_app import (
    UI_READY_POLL_S,
    _element_label,
    _element_x,
    _element_y,
    _matches_label,
    _refresh_app_ref,
)
from claude_continue.usage_parse import UsageSnapshot


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


def _click_labeled(app: Any, label: str, *, prefer_roles: tuple[str, ...] | None = None) -> None:
    roles = prefer_roles or ("AXMenuItem", "AXButton", "AXLink", "AXStaticText")
    for role in roles:
        for element in app.findAllR(AXRole=role):
            if _matches_label(element, label):
                press_element(element)
                time.sleep(0.6)
                return
    raise RuntimeError(f'Could not find control labeled "{label}"')


def _open_bottom_account_menu(app: Any) -> None:
    """Open the menu from the profile / arrow at the bottom of the sidebar."""
    try:
        windows = app.windows()
        window_height = float(windows[0].AXSize.height) if windows else 900.0
    except Exception:
        window_height = 900.0

    candidates: list[tuple[float, float, Any]] = []
    for role in ("AXButton", "AXImage"):
        for element in app.findAllR(AXRole=role):
            y = _element_y(element)
            x = _element_x(element)
            if y < window_height - 160:
                continue
            if x > 280:
                continue
            label = _element_label(element).lower()
            if any(skip in label for skip in ("voice", "record", "extension", "file")):
                continue
            candidates.append((y, x, element))

    if not candidates:
        raise RuntimeError("Could not find bottom sidebar menu (profile / arrow)")

    candidates.sort(key=lambda item: (-item[0], item[1]))
    press_element(candidates[0][2])
    time.sleep(0.6)


def open_usage_page(app: Any) -> Any:
    """Open Settings → Usage via the bottom tab-bar menu."""

    def _open() -> Any:
        current = _refresh_app_ref()
        if _is_usage_page_visible(current):
            return current

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

    return retry(_open, description="open Settings → Usage", attempts=3, delay=0.8)


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
    deadline = time.monotonic() + 20
    current = app
    while time.monotonic() < deadline:
        current = _refresh_app_ref()
        rows = _collect_text_rows(current)
        if any("all models" in t.lower() for _y, t in rows):
            return current
        time.sleep(UI_READY_POLL_S)
    raise RuntimeError("Usage page did not show usage data in time")
