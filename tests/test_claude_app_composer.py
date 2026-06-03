from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from claude_continue import claude_app


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _TextElement:
    def __init__(
        self,
        *,
        value: str = "",
        x: float = 100,
        y: float = 100,
        width: float = 400,
        height: float = 80,
    ) -> None:
        self.AXRole = "AXTextArea"
        self.AXValue = value
        self.AXPosition = _Point(x, y)
        self.AXSize = _Size(width, height)


class _Window:
    def __init__(self) -> None:
        self.AXPosition = _Point(0, 0)
        self.AXSize = _Size(1200, 900)


class FindVisibleFilledComposerTests(unittest.TestCase):
    def _app_with_fields(self, *fields: _TextElement) -> MagicMock:
        app = MagicMock()
        app.windows.return_value = [_Window()]
        app.findAllR.side_effect = lambda AXRole: list(fields) if AXRole == "AXTextArea" else []
        return app

    def test_picks_bottom_most_filled(self) -> None:
        top = _TextElement(value="top draft", y=200)
        bottom = _TextElement(value="bottom draft", y=700)
        result = claude_app.find_visible_filled_composer(self._app_with_fields(top, bottom))
        self.assertIs(result, bottom)

    def test_skips_empty_value(self) -> None:
        empty = _TextElement(value="", y=700)
        filled = _TextElement(value="ready", y=500)
        result = claude_app.find_visible_filled_composer(self._app_with_fields(empty, filled))
        self.assertIs(result, filled)

    def test_skips_outside_window(self) -> None:
        inside = _TextElement(value="inside", x=100, y=500)
        outside = _TextElement(value="outside", x=2000, y=500)
        result = claude_app.find_visible_filled_composer(self._app_with_fields(inside, outside))
        self.assertIs(result, inside)

    def test_returns_none_when_no_candidate(self) -> None:
        app = MagicMock()
        app.windows.return_value = [_Window()]
        app.findAllR.return_value = []
        self.assertIsNone(claude_app.find_visible_filled_composer(app))

    def test_returns_none_without_window(self) -> None:
        app = MagicMock()
        app.windows.return_value = []
        app.findAllR.return_value = [_TextElement(value="text")]
        self.assertIsNone(claude_app.find_visible_filled_composer(app))


if __name__ == "__main__":
    unittest.main()
