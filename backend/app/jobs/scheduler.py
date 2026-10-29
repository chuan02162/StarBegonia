"""Background loop: fire daily_sync at a local wall-clock time."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from app.jobs.daily_sync import run_daily_sync_all, seconds_until_local_time

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


def start_daily_sync_scheduler(app: Flask) -> threading.Thread | None:
    if not app.config.get("DAILY_SYNC_ENABLED"):
        logger.info("daily_sync scheduler disabled")
        return None

    tz_name = app.config.get("DAILY_SYNC_TZ") or "Australia/Sydney"
    hour = int(app.config.get("DAILY_SYNC_HOUR") or 0)
    minute = int(app.config.get("DAILY_SYNC_MINUTE") or 0)
    gap = float(app.config.get("DAILY_SYNC_GAP_SECONDS") or 45)

    def loop() -> None:
        logger.info(
            "daily_sync scheduler started tz=%s at %02d:%02d gap=%ss",
            tz_name,
            hour,
            minute,
            gap,
        )
        while True:
            delay = seconds_until_local_time(tz_name=tz_name, hour=hour, minute=minute)
            logger.info("daily_sync sleeping %.0fs until next run", delay)
            # Wake periodically so config/process restarts stay responsive.
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                time.sleep(min(60.0, deadline - time.monotonic()))
            with app.app_context():
                try:
                    run_daily_sync_all(gap_seconds=gap)
                except Exception:
                    logger.exception("daily_sync scheduler run crashed")

    thread = threading.Thread(
        target=loop,
        name="daily-sync-scheduler",
        daemon=True,
    )
    thread.start()
    return thread
