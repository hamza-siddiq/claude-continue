"""macOS Accessibility helpers for Electron apps."""

from __future__ import annotations

import time
from typing import Any

from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    kAXErrorSuccess,
)
from Cocoa import NSRunningApplication
from CoreFoundation import kCFBooleanTrue

AX_MANUAL_ACCESSIBILITY = "AXManualAccessibility"
AX_ENHANCED_USER_INTERFACE = "AXEnhancedUserInterface"

# macOS AXError codes (negative FourCharCodes).
_AX_ERROR_API_DISABLED = -25211
_AX_ERROR_ATTRIBUTE_UNSUPPORTED = -25204
_AX_ERROR_CANNOT_SET_ATTRIBUTE = -25205


def _set_ax_flag(app_ref: Any, attribute: str) -> int:
    return AXUIElementSetAttributeValue(app_ref, attribute, kCFBooleanTrue)


def enable_manual_accessibility(pid: int) -> None:
    """
    Expose Electron's full accessibility tree (required for Claude Desktop).

    Electron may return attributeUnsupported (-25204) even when the tree becomes
    usable; we retry briefly and fall back to AXEnhancedUserInterface.
    """
    last_err: int | None = None
    for attempt in range(6):
        app_ref = AXUIElementCreateApplication(pid)
        if app_ref is None:
            raise RuntimeError(f"Could not create AX element for PID {pid}")

        err = _set_ax_flag(app_ref, AX_MANUAL_ACCESSIBILITY)
        if err == kAXErrorSuccess:
            return

        last_err = err
        if err == _AX_ERROR_API_DISABLED:
            raise RuntimeError(
                "Accessibility is disabled for this terminal. "
                "Open System Settings → Privacy & Security → Accessibility, "
                "and enable your terminal app (Terminal, iTerm, or Cursor)."
            )

        enhanced_err = _set_ax_flag(app_ref, AX_ENHANCED_USER_INTERFACE)
        if enhanced_err == kAXErrorSuccess:
            return
        if enhanced_err == _AX_ERROR_API_DISABLED:
            raise RuntimeError(
                "Accessibility is disabled for this terminal. "
                "Open System Settings → Privacy & Security → Accessibility, "
                "and enable your terminal app (Terminal, iTerm, or Cursor)."
            )

        # Claude may not expose the attribute until fully launched.
        if err in (_AX_ERROR_ATTRIBUTE_UNSUPPORTED, _AX_ERROR_CANNOT_SET_ATTRIBUTE):
            time.sleep(0.35 + attempt * 0.15)
            continue

        time.sleep(0.35)

    if last_err in (_AX_ERROR_ATTRIBUTE_UNSUPPORTED, _AX_ERROR_CANNOT_SET_ATTRIBUTE):
        # Electron often still builds the tree; let atomacos verify on first use.
        return

    raise RuntimeError(
        f"Failed to enable Claude accessibility (error {last_err}). "
        "Ensure Claude Desktop is running and Accessibility is granted to your terminal."
    )


def get_attr(element: Any, name: str, default: str = "") -> str:
    try:
        value = getattr(element, name)
    except (AttributeError, TypeError):
        return default
    if value is None:
        return default
    return str(value)


def press_element(element: Any) -> None:
    """Press a UI element via AX action or click fallback."""
    try:
        if "Press" in element.getActions():
            element.Press()
            return
    except Exception:
        pass
    try:
        element.click()
    except Exception as exc:
        raise RuntimeError(f"Could not activate element: {exc}") from exc


def show_menu(element: Any) -> None:
    """Open a control's menu (profile chevron, etc.)."""
    try:
        actions = element.getActions()
        if "ShowMenu" in actions:
            element.ShowMenu()
            return
    except Exception:
        pass
    press_element(element)


def retry(fn, *, attempts: int = 3, delay: float = 0.5, description: str = "action"):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay)
    raise RuntimeError(f"{description} failed after {attempts} attempts: {last_error}")


def find_running_app(bundle_id: str) -> NSRunningApplication | None:
    for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id):
        return app
    return None
