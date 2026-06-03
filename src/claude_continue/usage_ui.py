"""Navigate Claude Desktop Settings → Usage and read limit state."""

from __future__ import annotations

import time
from typing import Any

from claude_continue.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
    retry,
)
from claude_continue.claude_app import (
    BUNDLE_ID,
    _element_label,
    _element_x,
    _element_y,
    _matches_label,
    _refresh_app_ref,
)
from claude_continue.mac_focus import (
    activate_claude,
    keystroke_in_claude,
    open_settings_shortcut,
    run_applescript,
)
from claude_continue.usage_parse import UsageSnapshot

SETTINGS_OPEN_TIMEOUT_S = 8
UI_POLL_S = 0.1
AX_PREPARE_S = 0.12
AFTER_ACTION_S = 0.2

# Left nav inside the Settings panel (not the Chat/Code/Cowork pills).
SETTINGS_NAV_LABELS = frozenset(
    {
        "usage",
        "general",
        "profile",
        "account",
        "privacy",
        "billing",
        "capabilities",
        "connectors",
        "hotkeys",
        "desktop app",
        "labs",
        "appearance",
    }
)

# Roles that often wrap a nav label in Electron settings.
_SETTINGS_NAV_ROLES = ("AXButton", "AXLink", "AXGroup", "AXRow", "AXListItem", "AXCell")
_PRESSABLE_ROLES = _SETTINGS_NAV_ROLES + ("AXMenuItem",)


def _element_bounds(element: Any) -> tuple[float, float, float, float]:
    try:
        pos = element.AXPosition
        size = element.AXSize
        return float(pos.x), float(pos.y), float(size.width), float(size.height)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _click_screen_xy(x: int, y: int) -> None:
    run_applescript(f'tell application "System Events" to click at {{{x}, {y}}}')


def _poll_until(
    predicate,
    *,
    timeout: float = 3.0,
    interval: float = UI_POLL_S,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


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


def _direct_labels(element: Any) -> set[str]:
    """Labels on this element only (not descendant text)."""
    found: set[str] = set()
    for attr in ("AXTitle", "AXDescription", "AXValue", "AXIdentifier"):
        value = get_attr(element, attr).strip()
        if value:
            found.add(value.casefold())
    return found


def _settings_nav_x_bounds(app: Any) -> tuple[float, float]:
    """Horizontal band of the Settings left nav (not the main Chat/Code sidebar)."""
    xs: list[float] = []
    for role in ("AXButton", "AXLink", "AXStaticText", "AXGroup") + _SETTINGS_NAV_ROLES:
        for element in app.findAllR(AXRole=role):
            label = _element_label(element).casefold()
            if label not in SETTINGS_NAV_LABELS:
                continue
            xs.append(_element_x(element))

    if xs:
        left = min(xs) - 40
        right = max(xs) + 120
        return left, right

    # Settings sheet is usually right of the main sidebar; allow a wide band.
    try:
        windows = app.windows()
        if windows:
            width = float(windows[0].AXSize.width)
            return width * 0.15, width * 0.55
    except Exception:
        pass
    return 200.0, 900.0


def _in_settings_nav_column(app: Any, element: Any) -> bool:
    x = _element_x(element)
    left, right = _settings_nav_x_bounds(app)
    return left <= x <= right


def _pressable_ancestor(element: Any, *, max_depth: int = 10) -> Any | None:
    current: Any | None = element
    for _ in range(max_depth):
        if current is None:
            return None
        try:
            if "Press" in current.getActions():
                return current
        except Exception:
            pass
        role = get_attr(current, "AXRole")
        if role in _PRESSABLE_ROLES:
            return current
        current = getattr(current, "AXParent", None)
    return None


def _nav_label_matches(element: Any, name: str) -> bool:
    want = name.casefold()
    if _element_label(element).casefold() == want:
        return True
    return want in _direct_labels(element)


def _is_settings_panel_open(app: Any) -> bool:
    """True when the in-app Settings sheet is open (any section)."""
    if _is_usage_page_visible(app):
        return True
    for role in _SETTINGS_NAV_ROLES:
        for element in app.findAllR(AXRole=role):
            if _element_label(element).casefold() in SETTINGS_NAV_LABELS:
                return True
    for _y, label in _collect_text_rows(app):
        low = label.strip().lower()
        if low in ("plan usage limits", "general", "appearance", "desktop app"):
            return True
    try:
        for window in app.windows():
            title = get_attr(window, "AXTitle").casefold()
            if "setting" in title:
                return True
    except Exception:
        pass
    return False


def _settings_nav_y_for_label(app: Any, label: str) -> float | None:
    want = label.casefold()
    ys: list[float] = []
    for role in ("AXStaticText",) + _SETTINGS_NAV_ROLES:
        for element in app.findAllR(AXRole=role):
            if _element_label(element).casefold() != want:
                continue
            if not _in_settings_nav_column(app, element):
                continue
            ys.append(_element_y(element))
    return max(ys) if ys else None


def _settings_nav_candidates(app: Any, name: str) -> list[tuple[float, Any]]:
    """Click targets for a settings nav item (e.g. Usage)."""
    want = name.casefold()
    found: list[tuple[float, Any]] = []

    for role in ("AXStaticText",) + _SETTINGS_NAV_ROLES:
        for element in app.findAllR(AXRole=role):
            if not _nav_label_matches(element, name):
                continue
            if not _in_settings_nav_column(app, element):
                continue
            target = _pressable_ancestor(element) or element
            found.append((_element_y(element), target))

    unique: dict[int, tuple[float, Any]] = {}
    for y, element in found:
        unique[id(element)] = (y, element)
    candidates = sorted(unique.values(), key=lambda item: item[0])

    if want == "usage":
        general_y = _settings_nav_y_for_label(app, "General")
        if general_y is not None:
            below = [(y, el) for y, el in candidates if y > general_y + 4]
            if below:
                candidates = below

    return candidates


def _click_at_element_center(element: Any) -> None:
    """Click the center of an element via System Events (Electron fallback)."""
    pos = element.AXPosition
    size = element.AXSize
    x = int(pos.x + size.width / 2)
    y = int(pos.y + size.height / 2)
    keystroke_in_claude(
        f'tell application "System Events" to click at {{{x}, {y}}}',
    )


def _activate_element(element: Any) -> None:
    try:
        press_element(element)
    except Exception:
        _click_at_element_center(element)


def _click_settings_nav(app: Any, name: str) -> bool:
    """Click a settings sidebar item (e.g. Usage), verifying Usage page when relevant."""
    candidates = _settings_nav_candidates(app, name)
    if not candidates:
        return False

    ordered = sorted(candidates, key=lambda item: item[0], reverse=(name.casefold() == "usage"))
    want_usage = name.casefold() == "usage"

    for _y, element in ordered:
        _activate_element(element)
        if want_usage:
            if _poll_until(
                lambda: _is_usage_page_visible(_refresh_app_ref()),
                timeout=2.5,
            ):
                return True
            continue
        time.sleep(AFTER_ACTION_S)
        return True
    return False


def dump_settings_nav(app: Any) -> None:
    """Print settings nav click targets (for `claude-continue inspect --settings-nav`)."""
    left, right = _settings_nav_x_bounds(app)
    print(f"Settings nav x band: {left:.0f} … {right:.0f}")
    print(f"Settings open: {_is_settings_panel_open(app)}")
    print(f"Usage page visible: {_is_usage_page_visible(app)}\n")

    for label in ("General", "Usage", "Profile", "Billing"):
        candidates = _settings_nav_candidates(app, label)
        print(f"{label}: {len(candidates)} candidate(s)")
        for y, element in candidates:
            role = get_attr(element, "AXRole")
            print(
                f"  y={y:6.0f} x={_element_x(element):6.0f}  role={role}  "
                f"label={_element_label(element)!r}  direct={_direct_labels(element)!r}",
            )


def _open_settings_via_menu_bar() -> bool:
    """Menu bar fallback when ⌘, did not open Settings."""
    for item in ("Settings…", "Settings...", "Settings"):
        if run_applescript(
            "tell application \"System Events\" to tell process \"Claude\"",
            f'click menu item "{item}" of menu 1 of menu bar item "Claude" of menu bar 1',
            "end tell",
        ):
            return True
    return False


def _wait_for_settings_panel(app: Any, *, timeout: float = SETTINGS_OPEN_TIMEOUT_S) -> Any:
    def _ready() -> bool:
        nonlocal app
        app = _refresh_app_ref()
        return _is_settings_panel_open(app) or _is_usage_page_visible(app)

    _poll_until(_ready, timeout=timeout)
    return _refresh_app_ref()


def _ensure_settings_open(app: Any) -> Any:
    """Open in-app Settings (⌘, first — works on home screen)."""
    current = _refresh_app_ref()
    if _is_settings_panel_open(current) or _is_usage_page_visible(current):
        return current

    activate_claude()
    open_settings_shortcut()
    current = _wait_for_settings_panel(app, timeout=SETTINGS_OPEN_TIMEOUT_S)
    if _is_settings_panel_open(current) or _is_usage_page_visible(current):
        return current

    if _open_settings_via_menu_bar():
        current = _wait_for_settings_panel(app, timeout=4.0)
        if _is_settings_panel_open(current) or _is_usage_page_visible(current):
            return current

    raise RuntimeError(
        "Could not open Settings. Click Claude, press ⌘, (Command+Comma), then retry."
    )


_ax_enabled = False


def _prepare_ax_tree(app: Any) -> Any:
    global _ax_enabled
    if not _ax_enabled:
        running = find_running_app(BUNDLE_ID)
        if running is not None:
            enable_manual_accessibility(running.processIdentifier())
        _ax_enabled = True
        time.sleep(AX_PREPARE_S)
    return _refresh_app_ref()


def _navigate_to_usage(app: Any) -> Any:
    _prepare_ax_tree(app)
    current = _ensure_settings_open(app)

    if _is_usage_page_visible(current):
        return current

    if _click_settings_nav(current, "Usage"):
        return _refresh_app_ref()

    if _poll_until(lambda: _is_usage_page_visible(_refresh_app_ref()), timeout=1.5):
        return _refresh_app_ref()

    raise RuntimeError(
        "Usage page did not open. Open Settings → Usage manually, or run "
        "`claude-continue inspect --settings-nav` while Settings is open."
    )


def _find_settings_modal_bounds(app: Any) -> tuple[float, float, float, float] | None:
    """Bounding box of the centered Settings card (not the full window)."""
    anchors: list[tuple[float, float, float, float]] = []

    for role in ("AXStaticText",) + _SETTINGS_NAV_ROLES:
        for element in app.findAllR(AXRole=role):
            label = _element_label(element).casefold()
            if label not in SETTINGS_NAV_LABELS and label != "plan usage limits":
                continue
            bounds = _element_bounds(element)
            if bounds[2] < 1:
                continue
            anchors.append(bounds)

    if not anchors:
        return None

    left = min(b[0] for b in anchors)
    top = min(b[1] for b in anchors)
    right = max(b[0] + b[2] for b in anchors)
    bottom = max(b[1] + b[3] for b in anchors)
    pad_x, pad_y = 48, 56
    return left - pad_x, top - pad_y, (right - left) + 2 * pad_x, (bottom - top) + 2 * pad_y


def _find_settings_close_button(app: Any) -> Any | None:
    """Close (X) control on the Settings modal header."""
    modal = _find_settings_modal_bounds(app)
    if modal is None:
        return None

    mx, my, mw, mh = modal
    header_bottom = my + min(mh * 0.18, 72)
    close_labels = frozenset({"close", "dismiss", "×", "x", "✕"})

    best: tuple[float, Any] | None = None
    for element in app.findAllR(AXRole="AXButton"):
        x, y, w, h = _element_bounds(element)
        if w < 1 or h < 1:
            continue
        cx, cy = x + w / 2, y + h / 2
        if cx < mx + mw * 0.65 or cy > header_bottom:
            continue
        label = _element_label(element).casefold()
        direct = _direct_labels(element)
        is_close = (
            any(tok in label for tok in close_labels)
            or bool(direct & close_labels)
            or "close" in " ".join(direct)
        )
        if is_close or (not label and w <= 48 and h <= 48):
            score = cx + (header_bottom - cy)
            if best is None or score > best[0]:
                best = (score, element)
    return best[1] if best else None


def _click_settings_close(app: Any) -> bool:
    button = _find_settings_close_button(app)
    if button is None:
        for label in ("Close", "×", "✕"):
            for element in app.findAllR(AXRole="AXButton"):
                if _matches_label(element, label):
                    button = element
                    break
            if button is not None:
                break
    if button is None:
        return False
    _activate_element(button)
    return True


def _click_settings_backdrop(app: Any) -> bool:
    """Click the dimmed overlay outside the Settings card."""
    modal = _find_settings_modal_bounds(app)
    try:
        windows = app.windows()
        if not windows:
            return False
        win = windows[0]
        wx, wy, ww, wh = _element_bounds(win)
    except Exception:
        return False

    if modal is None:
        _click_screen_xy(int(wx + 40), int(wy + wh / 2))
        return True

    mx, my, mw, mh = modal
    margin = 36
    targets = [
        (int(mx - margin), int(my + mh / 2)),
        (int(mx + mw + margin), int(my + mh / 2)),
        (int(wx + ww / 2), int(my - margin)),
        (int(wx + ww / 2), int(my + mh + margin)),
    ]
    for x, y in targets:
        if wx + 8 <= x <= wx + ww - 8 and wy + 8 <= y <= wy + wh - 8:
            inside_modal = mx <= x <= mx + mw and my <= y <= my + mh
            if not inside_modal:
                _click_screen_xy(x, y)
                return True
    _click_screen_xy(int(wx + 40), int(wy + wh / 2))
    return True


def close_settings(app: Any) -> None:
    """Leave Settings: X button, then backdrop click, then ⌘, toggle."""
    current = _prepare_ax_tree(app)
    if not _is_settings_panel_open(current):
        return

    activate_claude()

    def _closed() -> bool:
        return not _is_settings_panel_open(_refresh_app_ref())

    if _click_settings_close(current):
        if _poll_until(_closed, timeout=2.0):
            activate_claude()
            return

    current = _refresh_app_ref()
    if _click_settings_backdrop(current):
        if _poll_until(_closed, timeout=2.0):
            activate_claude()
            return

    open_settings_shortcut()
    _poll_until(_closed, timeout=2.0)
    activate_claude()


def open_usage_page(app: Any) -> Any:
    """Open Settings → Usage via sidebar menu, shortcuts, or menu bar."""

    def _open() -> Any:
        return _navigate_to_usage(app)

    return retry(_open, description="open Settings → Usage", attempts=2, delay=0.35)


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
    def _has_rows() -> bool:
        rows = _collect_text_rows(_refresh_app_ref())
        return any("all models" in t.lower() for _y, t in rows)

    if _poll_until(_has_rows, timeout=20):
        return _refresh_app_ref()
    raise RuntimeError("Usage page did not show usage data in time")
