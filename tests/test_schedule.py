"""Tests for schedule.sleep_until."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from claude_continue.power import CAFFEINATE_LEAD_SECONDS
from claude_continue.schedule import sleep_until


def _mock_now(*values: datetime):
    fake_datetime = Mock()
    fake_datetime.now.side_effect = values
    return patch("claude_continue.schedule.datetime", fake_datetime)


def test_sleep_until_returns_when_target_passed() -> None:
    now = datetime(2026, 6, 4, 10, 0, 0)
    target = now - timedelta(seconds=1)

    with _mock_now(now, now), patch("claude_continue.schedule.time.sleep") as mock_sleep:
        sleep_until(target)

    mock_sleep.assert_not_called()


def test_sleep_until_uses_caffeinate_in_final_window() -> None:
    now = datetime(2026, 6, 4, 10, 0, 0)
    target = now + timedelta(seconds=60)

    with (
        _mock_now(now, now, target + timedelta(seconds=1)),
        patch("claude_continue.schedule.time.sleep"),
        patch(
            "claude_continue.schedule.start_idle_sleep_preventer"
        ) as mock_preventer,
        patch("claude_continue.schedule.try_schedule_wake_at") as mock_wake,
    ):
        sleep_until(target)

    mock_wake.assert_not_called()
    mock_preventer.assert_called_once()
    assert mock_preventer.call_args[0][0] > 0


def test_sleep_until_schedules_absolute_wake_when_far_away() -> None:
    now = datetime(2026, 6, 4, 10, 0, 0)
    target = now + timedelta(hours=2)

    with (
        _mock_now(now, now, target + timedelta(seconds=1)),
        patch("claude_continue.schedule.time.sleep"),
        patch("claude_continue.schedule.try_schedule_wake_at", return_value=True)
        as mock_wake,
        patch(
            "claude_continue.schedule.start_idle_sleep_preventer"
        ) as mock_preventer,
    ):
        sleep_until(target)

    mock_wake.assert_called_once_with(
        target - timedelta(seconds=CAFFEINATE_LEAD_SECONDS)
    )
    mock_preventer.assert_not_called()


def test_sleep_until_keeps_awake_when_wake_schedule_fails() -> None:
    now = datetime(2026, 6, 4, 10, 0, 0)
    target = now + timedelta(hours=2)

    with (
        _mock_now(now, now, target + timedelta(seconds=1)),
        patch("claude_continue.schedule.time.sleep"),
        patch("claude_continue.schedule.try_schedule_wake_at", return_value=False),
        patch(
            "claude_continue.schedule.start_idle_sleep_preventer"
        ) as mock_preventer,
    ):
        sleep_until(target)

    mock_preventer.assert_called_once()
    assert mock_preventer.call_args[0][0] > 60 * 60


def test_sleep_until_allow_sleep_does_not_keep_awake_when_wake_schedule_fails() -> None:
    now = datetime(2026, 6, 4, 10, 0, 0)
    target = now + timedelta(hours=2)

    with (
        _mock_now(now, now, target + timedelta(seconds=1)),
        patch("claude_continue.schedule.time.sleep"),
        patch("claude_continue.schedule.try_schedule_wake_at", return_value=False),
        patch(
            "claude_continue.schedule.start_idle_sleep_preventer"
        ) as mock_preventer,
    ):
        sleep_until(target, allow_sleep=True)

    mock_preventer.assert_not_called()
