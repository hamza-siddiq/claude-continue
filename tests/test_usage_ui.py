from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from claude_continue import usage_ui


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _Element:
    def __init__(
        self,
        role: str,
        label: str,
        *,
        x: float = 240,
        y: float = 100,
        width: float = 180,
        height: float = 32,
        pressable: bool = True,
    ) -> None:
        self.AXRole = role
        self.AXTitle = label
        self.AXValue = ""
        self.AXDescription = ""
        self.AXIdentifier = ""
        self.AXPosition = _Point(x, y)
        self.AXSize = _Size(width, height)
        self._pressable = pressable
        self.pressed = False
        self.clicked = False

    def getActions(self) -> list[str]:
        return ["Press"] if self._pressable else []

    def Press(self) -> None:
        self.pressed = True

    def click(self) -> None:
        self.clicked = True


class _Window:
    AXSize = _Size(1200, 900)


class _App:
    def __init__(self, elements: list[_Element]) -> None:
        self.elements = elements

    def findAllR(self, *, AXRole: str) -> list[_Element]:
        return [element for element in self.elements if element.AXRole == AXRole]

    def windows(self) -> list[_Window]:
        return [_Window()]


class UsageUiTest(unittest.TestCase):
    def tearDown(self) -> None:
        usage_ui._clear_nav_index()

    def test_upper_usage_and_general_are_filtered_above_desktop_section(self) -> None:
        upper_general = _Element("AXButton", "General", y=252)
        usage = _Element("AXButton", "Usage", y=462)
        desktop_app = _Element("AXStaticText", "Desktop app", y=798, pressable=False)
        lower_general = _Element("AXButton", "General", y=854)
        app = _App([upper_general, usage, desktop_app, lower_general])

        usage_ui._build_settings_nav_index(app, stop_when_ready=False)

        self.assertIs(usage_ui._best_usage_nav_target(app), usage)
        general_candidates = usage_ui._settings_nav_candidates(app, "General")
        self.assertEqual([candidate[2] for candidate in general_candidates], [upper_general])

    def test_usage_click_uses_index_before_applescript(self) -> None:
        usage = _Element("AXButton", "Usage", y=462)
        app = _App([usage])
        usage_ui._build_settings_nav_index(app)

        with (
            patch.object(usage_ui, "activate_claude"),
            patch.object(usage_ui, "_is_usage_page_visible", return_value=False),
            patch.object(usage_ui, "_wait_for_usage_page", return_value=True),
            patch.object(
                usage_ui,
                "_click_usage_by_applescript",
                side_effect=AssertionError("AppleScript fallback ran before AX click"),
            ),
            patch.object(usage_ui.time, "sleep"),
        ):
            self.assertTrue(usage_ui._click_usage_tab(app))

        self.assertTrue(usage.pressed)

    def test_nav_ready_requires_usage_only(self) -> None:
        usage = _Element("AXButton", "Usage", y=462)
        app = _App([usage])

        index = usage_ui._build_settings_nav_index(app)

        self.assertTrue(usage_ui._nav_index_is_complete(index))
        self.assertEqual(set(index.by_label), {"usage"})

    def test_close_keeps_nav_cache_until_close_is_verified(self) -> None:
        usage = _Element("AXButton", "Usage", y=462)
        usage_ui._nav_index = usage_ui._SettingsNavIndex(
            x_bounds=(200, 500),
            by_label={"usage": [(462, 240, usage, usage)]},
            backdrop_xy=(160, 462),
        )

        with (
            patch.object(usage_ui, "dismiss_settings_escape", return_value=True),
            patch.object(usage_ui, "_wait_for_settings_closed", return_value=False),
        ):
            usage_ui.close_settings(_App([]))

        self.assertIsNotNone(usage_ui._nav_index)

        with (
            patch.object(usage_ui, "dismiss_settings_escape", return_value=True),
            patch.object(usage_ui, "_wait_for_settings_closed", return_value=True),
        ):
            usage_ui.close_settings(_App([]))

        self.assertIsNone(usage_ui._nav_index)


if __name__ == "__main__":
    unittest.main()
