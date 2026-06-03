"""Navigate Claude Desktop Settings → Usage and read limit state.

Layout reference (repo root): Home.png (chat home + usage banner), Settings.png
(⌘, opens Settings on Desktop app → General; Usage is in the main nav above
the "Desktop app" section — two "General" rows exist).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from claude_continue.ax import (
    enable_manual_accessibility,
    find_running_app,
    get_attr,
    press_element,
)
from claude_continue.claude_app import (
    BUNDLE_ID,
    _element_label,
    _element_x,
    _element_y,
    _refresh_app_ref,
)
from claude_continue.mac_focus import (
    activate_claude,
    click_at_screen,
    dismiss_settings_escape,
    open_settings_shortcut,
    run_applescript,
)
from claude_continue.usage_parse import UsageSnapshot

SETTINGS_OPEN_TIMEOUT_S = 3.0
SETTINGS_OPEN_POLL_S = 0.04
SETTINGS_CLOSE_TIMEOUT_S = 1.2
SETTINGS_CLOSE_POLL_S = 0.05
AX_PREPARE_S = 0.05
_FAST_SCAN_CAP = 120
_SNAPSHOT_SCAN_CAP = 220
_NAV_SCAN_CAP_PER_ROLE = 350
_USAGE_MARKERS = frozenset(
    {"plan usage limits", "all models", "current session"},
)
_USAGE_VISIBLE_WAIT_S = 0.85
_USAGE_VISIBLE_POLL_S = 0.06
_SETTINGS_MARKERS = frozenset({"general", "usage", "appearance", "desktop app"})
_NAV_INDEX_READY_LABELS = frozenset({"usage"})

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
        "extensions",
        "developer",
        "claude code",
        "cowork",
        "search",
        "labs",
        "appearance",
    }
)
_SETTINGS_PANEL_NAV_LABELS = SETTINGS_NAV_LABELS - {"cowork", "search"}

# Roles that often wrap a nav label in Electron settings.
_SETTINGS_NAV_ROLES = ("AXButton", "AXLink", "AXGroup", "AXRow", "AXListItem", "AXCell")
_PRESSABLE_ROLES = _SETTINGS_NAV_ROLES + ("AXMenuItem",)

_nav_index: "_SettingsNavIndex | None" = None


@dataclass
class _SettingsNavIndex:
    """Single-pass scan of Settings left nav (avoids repeated findAllR)."""

    x_bounds: tuple[float, float]
    by_label: dict[str, list[tuple[float, float, Any, Any]]] = field(
        default_factory=dict
    )  # label -> [(y, x, click_target, source_element)]
    backdrop_xy: tuple[int, int] | None = None


def _clear_nav_index() -> None:
    global _nav_index
    _nav_index = None


def _element_bounds(element: Any) -> tuple[float, float, float, float]:
    try:
        pos = element.AXPosition
        size = element.AXSize
        return float(pos.x), float(pos.y), float(size.width), float(size.height)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _click_screen_xy(x: int, y: int) -> None:
    click_at_screen(x, y)


def _direct_static_label(element: Any) -> str:
    for attr in ("AXTitle", "AXValue", "AXDescription"):
        value = get_attr(element, attr).strip()
        if value:
            return value.casefold()
    return ""


def _static_display_label(element: Any) -> str:
    for attr in ("AXTitle", "AXValue", "AXDescription"):
        value = get_attr(element, attr).strip()
        if value:
            return value
    return ""


def _scan_static_text_fast(
    app: Any,
    markers: frozenset[str],
    *,
    cap: int = _FAST_SCAN_CAP,
) -> bool:
    for n, element in enumerate(app.findAllR(AXRole="AXStaticText")):
        if n >= cap:
            break
        if _direct_static_label(element) in markers:
            return True
    return False


def _collect_text_rows(app: Any) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    saw_session = False
    saw_all_models = False
    saw_usage_header = False
    for n, element in enumerate(app.findAllR(AXRole="AXStaticText")):
        if n >= _SNAPSHOT_SCAN_CAP:
            break
        label = _static_display_label(element)
        if not label:
            continue
        low = label.lower()
        if low == "current session":
            saw_session = True
        elif low == "all models":
            saw_all_models = True
        elif low == "plan usage limits":
            saw_usage_header = True
        rows.append((_element_y(element), label))
        if (
            saw_usage_header
            and saw_session
            and saw_all_models
            and any("100% used" in r[1].lower() for r in rows)
            and n >= 40
        ):
            break
    rows.sort(key=lambda item: item[0])
    return rows


def _is_usage_page_visible(app: Any) -> bool:
    if _scan_static_text_fast(app, _USAGE_MARKERS, cap=_FAST_SCAN_CAP):
        return True
    for n, element in enumerate(app.findAllR(AXRole="AXStaticText")):
        if n >= _FAST_SCAN_CAP:
            break
        label = _direct_static_label(element)
        if "100% used" in label or label.startswith("resets"):
            return True
    return False


def _wait_for_usage_page(
    app: Any | None = None,
    *,
    timeout: float = _USAGE_VISIBLE_WAIT_S,
) -> bool:
    deadline = time.monotonic() + timeout
    current = app
    while time.monotonic() < deadline:
        try:
            if current is None:
                current = _refresh_app_ref()
            if _is_usage_page_visible(current):
                return True
        except (ValueError, RuntimeError):
            current = None
        time.sleep(_USAGE_VISIBLE_POLL_S)
    try:
        current = current or _refresh_app_ref()
        return _is_usage_page_visible(current)
    except (ValueError, RuntimeError):
        return False


def _is_settings_panel_open(app: Any) -> bool:
    index = _nav_index
    if index is not None and _index_has_settings_nav(index):
        return True
    if _scan_static_text_fast(app, _SETTINGS_MARKERS, cap=40):
        return True
    return _is_usage_page_visible(app)


def _direct_labels(element: Any) -> set[str]:
    """Labels on this element only (not descendant text)."""
    found: set[str] = set()
    for attr in ("AXTitle", "AXDescription", "AXValue", "AXIdentifier"):
        value = get_attr(element, attr).strip()
        if value:
            found.add(value.casefold())
    return found


def _default_nav_x_bounds(app: Any) -> tuple[float, float]:
    try:
        windows = app.windows()
        if windows:
            width = float(windows[0].AXSize.width)
            return width * 0.12, width * 0.58
    except Exception:
        pass
    return 200.0, 900.0


def _nav_index_is_complete(index: _SettingsNavIndex) -> bool:
    return _NAV_INDEX_READY_LABELS.issubset(index.by_label.keys())


def _index_has_settings_nav(index: _SettingsNavIndex) -> bool:
    return any(label in _SETTINGS_PANEL_NAV_LABELS for label in index.by_label)


def _build_settings_nav_index(
    app: Any,
    *,
    cache: bool = True,
    stop_when_ready: bool = True,
) -> _SettingsNavIndex:
    global _nav_index
    xs: list[float] = []
    by_label: dict[str, list[tuple[float, float, Any, Any]]] = {}

    # Buttons first (Usage nav is usually AXButton); stop once we have key rows.
    for role in ("AXButton", "AXStaticText"):
        for n, element in enumerate(app.findAllR(AXRole=role)):
            if n >= _NAV_SCAN_CAP_PER_ROLE:
                break
            label = _direct_static_label(element)
            if label not in SETTINGS_NAV_LABELS:
                continue
            x = _element_x(element)
            y = _element_y(element)
            xs.append(x)
            if role == "AXStaticText":
                target = _pressable_ancestor(element) or element
            else:
                target = element
            by_label.setdefault(label, []).append((y, x, target, element))
        if stop_when_ready and _nav_index_is_complete(
            _SettingsNavIndex(x_bounds=(0, 0), by_label=by_label)
        ):
            break

    if xs:
        x_bounds = (min(xs) - 40, max(xs) + 120)
    else:
        x_bounds = _default_nav_x_bounds(app)

    index = _SettingsNavIndex(x_bounds=x_bounds, by_label=by_label)
    index.backdrop_xy = _backdrop_click_xy(index)
    if cache:
        _nav_index = index
    return index


def _get_nav_index(app: Any) -> _SettingsNavIndex:
    global _nav_index
    if _nav_index is None:
        return _build_settings_nav_index(app)
    return _nav_index


def _in_nav_column(x: float, index: _SettingsNavIndex) -> bool:
    left, right = index.x_bounds
    return left <= x <= right


def _main_settings_section_y_max(index: _SettingsNavIndex) -> float | None:
    """Max Y for main Settings nav (excludes Desktop app → General / Extensions)."""
    desktop = index.by_label.get("desktop app", [])
    if desktop:
        return min(e[0] for e in desktop) - 12.0

    generals = sorted(
        e[0]
        for e in index.by_label.get("general", [])
        if _in_nav_column(e[1], index)
    )
    if len(generals) < 2:
        generals = sorted(e[0] for e in index.by_label.get("general", []))
    if len(generals) >= 2:
        return (generals[-2] + generals[-1]) / 2.0
    return None


def _in_main_settings_nav(y: float, index: _SettingsNavIndex) -> bool:
    y_max = _main_settings_section_y_max(index)
    if y_max is None:
        return True
    return y < y_max


def _nav_entries_for_label(
    index: _SettingsNavIndex,
    label: str,
) -> list[tuple[float, float, Any, Any]]:
    want = label.casefold()
    entries = list(index.by_label.get(want, []))

    if not entries and want == "usage":
        for indexed_label, items in index.by_label.items():
            if "usage" in indexed_label:
                entries.extend(items)

    in_column = [e for e in entries if _in_nav_column(e[1], index)]
    if in_column:
        entries = in_column
    return _filter_main_nav_entries(entries, index)


def _has_usage_nav_target(index: _SettingsNavIndex) -> bool:
    return bool(_nav_entries_for_label(index, "usage"))


def _filter_main_nav_entries(
    entries: list[tuple[float, float, Any, Any]],
    index: _SettingsNavIndex,
) -> list[tuple[float, float, Any, Any]]:
    filtered = [e for e in entries if _in_main_settings_nav(e[0], index)]
    return filtered if filtered else entries


def _backdrop_click_xy(index: _SettingsNavIndex) -> tuple[int, int] | None:
    """Dimmed area left of the settings card (computed once while nav is open)."""
    usage_rows = _nav_entries_for_label(index, "usage")
    if not usage_rows:
        return None
    left, _right = index.x_bounds
    y_center = sum(row[0] for row in usage_rows) / len(usage_rows)
    return int(left - 48), int(y_center)


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


def _settings_nav_candidates(app: Any, name: str) -> list[tuple[float, Any, Any]]:
    """Click targets: (y, target, source_element) from cached nav index."""
    index = _get_nav_index(app)
    want = name.casefold()
    entries = _nav_entries_for_label(index, want)

    unique: dict[int, tuple[float, Any, Any]] = {}
    for y, _x, target, source in entries:
        if _clickable_center(source) is None and _clickable_center(target) is None:
            continue
        unique[id(target)] = (y, target, source)
    candidates = sorted(unique.values(), key=lambda item: item[0])

    if want == "usage":
        candidates.sort(
            key=lambda c: (
                0 if get_attr(c[2], "AXRole") == "AXButton" else 1,
                c[0],
            ),
        )

    return candidates


def _clickable_center(element: Any) -> tuple[int, int] | None:
    x, y, w, h = _element_bounds(element)
    if w < 2 or h < 2 or x < 50:
        return None
    return int(x + w / 2), int(y + h / 2)


def _activate_nav_element(element: Any) -> bool:
    """Press a settings nav row (AX first, then process-relative click)."""
    try:
        press_element(element)
        return True
    except Exception:
        pass
    try:
        element.click()
        return True
    except Exception:
        pass
    center = _clickable_center(element)
    if center is None:
        return False
    click_at_screen(*center)
    return True


def _click_at_element_center(element: Any) -> bool:
    return _activate_nav_element(element)


def _click_usage_by_applescript() -> bool:
    """Fallback: click the Usage row by name in Claude's process."""
    snippets = [
        'click (first button of window 1 whose name is "Usage")',
        'click (first UI element of window 1 whose name is "Usage")',
        'click (first static text of window 1 whose value is "Usage")',
    ]
    for snippet in snippets:
        if run_applescript(
            "tell application \"System Events\" to tell process \"Claude\"",
            "set frontmost to true",
            snippet,
            "end tell",
        ):
            return True
    return False


def _best_usage_nav_target(app: Any) -> Any | None:
    """Single Usage row in the main settings nav (never Desktop app → General)."""
    index = _get_nav_index(app)
    entries = _nav_entries_for_label(index, "usage")
    if not entries:
        return None

    for _y, _x, target, source in sorted(entries, key=lambda e: e[0]):
        for element in (target, source):
            if get_attr(element, "AXRole") != "AXButton":
                continue
            if _direct_static_label(element) == "usage":
                return element

    _y, _x, target, source = entries[0]
    if get_attr(target, "AXRole") == "AXButton":
        return target
    if get_attr(source, "AXRole") == "AXButton":
        return source
    return target


def _click_usage_tab(app: Any) -> bool:
    """Click Usage only — Settings may already show General selected."""
    if _is_usage_page_visible(app):
        return True

    activate_claude()
    target = _best_usage_nav_target(app)
    if target is None:
        app = _refresh_app_ref()
        _build_settings_nav_index(app)
        target = _best_usage_nav_target(app)

    if target is not None and _activate_nav_element(target):
        time.sleep(0.06)
        if _wait_for_usage_page(app, timeout=_USAGE_VISIBLE_WAIT_S):
            return True

    if _click_usage_by_applescript():
        time.sleep(0.06)
        if _wait_for_usage_page(app, timeout=0.65):
            return True

    return _wait_for_usage_page(app, timeout=0.2)


def _click_settings_nav(app: Any, name: str) -> bool:
    """Click a settings sidebar item (e.g. Usage), verifying Usage page when relevant."""
    if name.casefold() == "usage":
        return _click_usage_tab(app)

    candidates = _settings_nav_candidates(app, name)
    if not candidates:
        return False

    _y, target, source = candidates[0]
    return _click_at_element_center(source) or _click_at_element_center(target)


def dump_settings_nav(app: Any) -> None:
    """Print settings nav click targets (for `claude-continue inspect --settings-nav`)."""
    index = _build_settings_nav_index(app, stop_when_ready=False)
    left, right = index.x_bounds
    print(f"Settings nav x band: {left:.0f} … {right:.0f}")
    y_max = _main_settings_section_y_max(index)
    if y_max is not None:
        print(f"Main settings nav y < {y_max:.0f} (Desktop app section below)")
    print(f"Settings open: {_is_settings_panel_open(app)}")
    print(f"Usage page visible: {_is_usage_page_visible(app)}\n")
    print(f"Index labels: {sorted(index.by_label.keys())}\n")
    for label in ("General", "Usage", "Profile", "Billing"):
        candidates = _settings_nav_candidates(app, label)
        print(f"{label}: {len(candidates)} candidate(s)")
        for y, _target, source in candidates:
            role = get_attr(source, "AXRole")
            print(
                f"  y={y:6.0f} x={_element_x(source):6.0f}  role={role}  "
                f"label={_element_label(source)!r}  direct={_direct_labels(source)!r}",
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


def _wait_for_settings_nav(
    app: Any,
    *,
    timeout: float = SETTINGS_OPEN_TIMEOUT_S,
) -> Any | None:
    deadline = time.monotonic() + timeout
    last_open: Any | None = None
    current = app

    while time.monotonic() < deadline:
        try:
            current = _refresh_app_ref()
            index = _build_settings_nav_index(current)
            if _has_usage_nav_target(index) or _is_usage_page_visible(current):
                return current
            if _index_has_settings_nav(index) or _scan_static_text_fast(
                current, _SETTINGS_MARKERS, cap=40
            ):
                last_open = current
        except (ValueError, RuntimeError):
            pass
        time.sleep(SETTINGS_OPEN_POLL_S)

    try:
        current = _refresh_app_ref()
        index = _build_settings_nav_index(current)
        if (
            _has_usage_nav_target(index)
            or _index_has_settings_nav(index)
            or _is_usage_page_visible(current)
        ):
            return current
    except (ValueError, RuntimeError):
        pass

    return last_open


def _ensure_settings_open(app: Any) -> Any:
    """Open in-app Settings (⌘, first — works on home screen)."""
    activate_claude()
    open_settings_shortcut()
    current = _wait_for_settings_nav(app)
    if current is not None:
        return current

    if _open_settings_via_menu_bar():
        current = _wait_for_settings_nav(app)
        if current is not None:
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
    _clear_nav_index()
    _prepare_ax_tree(app)
    activate_claude()
    current = _refresh_app_ref()

    if _is_settings_panel_open(current):
        if _nav_index is None:
            _build_settings_nav_index(current)
    else:
        current = _ensure_settings_open(app)

    current = _refresh_app_ref()
    if _is_usage_page_visible(current):
        return current

    if _nav_index is None or not _nav_index_is_complete(_nav_index):
        _build_settings_nav_index(current)
    if _click_usage_tab(current):
        return _refresh_app_ref()

    current = _refresh_app_ref()
    if _is_usage_page_visible(current):
        return current

    raise RuntimeError(
        "Usage page did not open. Open Settings → Usage manually, or run "
        "`claude-continue inspect --settings-nav` while Settings is open."
    )


def _click_settings_backdrop(app: Any) -> bool:
    """Click the dimmed overlay outside the Settings card."""
    index = _nav_index
    if index is not None and index.backdrop_xy is not None:
        x, y = index.backdrop_xy
        _click_screen_xy(x, y)
        return True

    if index is not None and index.by_label:
        xy = _backdrop_click_xy(index)
        if xy is not None:
            _click_screen_xy(*xy)
            return True

    try:
        win = app.windows()[0]
        wx, wy, _ww, wh = _element_bounds(win)
        _click_screen_xy(int(wx + 32), int(wy + wh / 2))
        return True
    except Exception:
        return False


def _settings_panel_open_uncached(app: Any) -> bool:
    index = _build_settings_nav_index(app, cache=False)
    if _index_has_settings_nav(index):
        return True
    if _scan_static_text_fast(app, _SETTINGS_MARKERS, cap=40):
        return True
    return _is_usage_page_visible(app)


def _wait_for_settings_closed(
    app: Any,
    *,
    timeout: float = SETTINGS_CLOSE_TIMEOUT_S,
) -> bool:
    deadline = time.monotonic() + timeout
    current = app
    while time.monotonic() < deadline:
        try:
            current = _refresh_app_ref()
            if not _settings_panel_open_uncached(current):
                return True
        except (ValueError, RuntimeError):
            return True
        time.sleep(SETTINGS_CLOSE_POLL_S)

    try:
        return not _settings_panel_open_uncached(current)
    except (ValueError, RuntimeError):
        return True


def close_settings(app: Any) -> None:
    """Dismiss Settings with Escape; cached backdrop click only as fallback."""
    if dismiss_settings_escape() and _wait_for_settings_closed(app):
        _clear_nav_index()
        return

    index = _nav_index
    clicked = False
    if index is not None and index.backdrop_xy is not None:
        click_at_screen(*index.backdrop_xy)
        clicked = True
    elif index is not None and index.by_label:
        clicked = _click_settings_backdrop(app)

    if clicked and _wait_for_settings_closed(app):
        _clear_nav_index()


def open_usage_page(app: Any) -> Any:
    """Open Settings (⌘,) → Usage in the main settings nav."""
    return _navigate_to_usage(app)


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
    if _is_usage_page_visible(app):
        return _refresh_app_ref()
    if _wait_for_usage_page(app, timeout=0.35):
        return _refresh_app_ref()
    raise RuntimeError("Usage page did not show usage data in time")
