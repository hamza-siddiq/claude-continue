"""Tests for schedule.sleep_until."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from claude_continue.schedule import sleep_until


def test_sleep_until_returns_when_target_passed() -> None:
    target = datetime.now() - timedelta(seconds=1)
    with patch("claude_continue.schedule.time.sleep") as mock_sleep:
        sleep_until(target)
    mock_sleep.assert_not_called()


def test_sleep_until_uses_caffeinate_in_final_window() -> None:
    target = datetime.now() + timedelta(seconds=60)
    with (
        patch("claude_continue.schedule.time.sleep"),
        patch(
            "claude_continue.schedule.prevent_idle_sleep"
        ) as mock_caffeinate,
        patch("claude_continue.schedule.try_schedule_relative_wake") as mock_wake,
    ):
        sleep_until(target)
    mock_wake.assert_not_called()
    mock_caffeinate.assert_called_once()
    assert mock_caffeinate.call_args[0][0] > 0


def test_sleep_until_schedules_wake_when_far_away() -> None:
    target = datetime.now() + timedelta(hours=2)
    with (
        patch("claude_continue.schedule.time.sleep"),
        patch("claude_continue.schedule.prevent_idle_sleep"),
        patch(
            "claude_continue.schedule.try_schedule_relative_wake", return_value=True
        ) as mock_wake,
    ):
        sleep_until(target)
    mock_wake.assert_called_once()
    wake_seconds = mock_wake.call_args[0][0]
    assert wake_seconds > 60 * 60
