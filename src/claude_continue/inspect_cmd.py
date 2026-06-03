"""Dump Claude Desktop accessibility tree for debugging."""

from __future__ import annotations

import sys
from typing import Any

from claude_continue.ax import get_attr
from claude_continue.claude_app import get_app_ref


def _dump(element: Any, depth: int, max_depth: int, indent: int) -> None:
    if depth > max_depth:
        return
    role = get_attr(element, "AXRole", "?")
    title = get_attr(element, "AXTitle")
    desc = get_attr(element, "AXDescription")
    value = get_attr(element, "AXValue")
    label = title or desc or value
    if label and len(label) > 80:
        label = label[:77] + "..."
    parts = [role]
    if label:
        parts.append(repr(label))
    print("  " * indent + " ".join(parts))

    try:
        children = element.AXChildren or []
    except Exception:
        children = []
    for child in children:
        _dump(child, depth + 1, max_depth, indent + 1)


def _dump_sidebar_candidates(app: Any) -> None:
    from claude_continue.claude_app import (
        CHAT_ROW_ROLES,
        _element_label,
        _element_x,
        _element_y,
        _is_skipped_sidebar_label,
        _sidebar_max_x,
    )

    max_x = _sidebar_max_x(app)
    print(f"Sidebar candidates (x <= {max_x:.0f}):\n")
    for role in CHAT_ROW_ROLES:
        for element in app.findAllR(AXRole=role):
            label = _element_label(element)
            if not label:
                continue
            skipped = _is_skipped_sidebar_label(label)
            print(
                f"  {role:12} y={_element_y(element):6.0f} x={_element_x(element):6.0f}"
                f"  skip={skipped}  {label[:60]!r}"
            )


def run_inspect(*, max_depth: int = 6, sidebar: bool = False, usage: bool = False) -> int:
    try:
        app = get_app_ref()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if usage:
        from claude_continue.usage_ui import (
            open_usage_page,
            read_usage_snapshot,
            wait_for_usage_rows,
            _collect_text_rows,
        )

        try:
            app = open_usage_page(app)
            app = wait_for_usage_rows(app)
            snap = read_usage_snapshot(app)
            print("Usage snapshot:")
            print(f"  all_models_full={snap.all_models_full}")
            print(f"  session_full={snap.session_full}")
            print(f"  all_models_reset={snap.all_models_reset_text!r}")
            print(f"  session_reset={snap.session_reset_text!r}")
            print("\nText rows on page:")
            for y, text in _collect_text_rows(app):
                print(f"  y={y:6.0f}  {text[:80]!r}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if sidebar:
        _dump_sidebar_candidates(app)
        return 0

    windows = app.windows()
    if not windows:
        print("No windows found.", file=sys.stderr)
        return 1

    print(f"Claude UI tree (depth <= {max_depth}):\n")
    for i, window in enumerate(windows):
        print(f"--- Window {i} ---")
        _dump(window, 0, max_depth, 0)
    return 0
