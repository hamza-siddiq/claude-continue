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


def enable_manual_accessibility(pid: int) -> None:
    """Expose Electron's full accessibility tree (required for Claude Desktop)."""
    app_ref = AXUIElementCreateApplication(pid)
    if app_ref is None:
        raise RuntimeError(f"Could not create AX element for PID {pid}")
    err = AXUIElementSetAttributeValue(
        app_ref, AX_MANUAL_ACCESSIBILITY, kCFBooleanTrue
    )
    if err != kAXErrorSuccess:
        raise RuntimeError(
            f"Failed to set AXManualAccessibility (error {err}). "
            "Grant Accessibility permission to your terminal."
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
