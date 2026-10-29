from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.jobs.daily_sync import seconds_until_local_time


def test_seconds_until_sydney_midnight_before():
    # 2026-10-30 23:00 Sydney → ~1 hour to midnight
    now = datetime(2026, 10, 30, 23, 0, 0, tzinfo=ZoneInfo("Australia/Sydney"))
    delay = seconds_until_local_time(
        tz_name="Australia/Sydney", hour=0, minute=0, now=now
    )
    assert 3500 <= delay <= 3700


def test_seconds_until_sydney_midnight_after():
    now = datetime(2026, 10, 30, 0, 1, 0, tzinfo=ZoneInfo("Australia/Sydney"))
    delay = seconds_until_local_time(
        tz_name="Australia/Sydney", hour=0, minute=0, now=now
    )
    # almost a full day
    assert delay > 86000
