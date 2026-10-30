"""Nightly sequential sync for all configured sources.

Run via worker scheduler (Sydney midnight) or:
  python -m app.jobs.daily_sync
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

SYNCABLE = ("coles", "commbank")


def seconds_until_local_time(
    *,
    tz_name: str = "Australia/Sydney",
    hour: int = 0,
    minute: int = 0,
    now: datetime | None = None,
) -> float:
    """Seconds until the next wall-clock hour:minute in tz (handles DST)."""
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if current >= target:
        target += timedelta(days=1)
    return max(0.0, (target - current).total_seconds())


def run_daily_sync_all(*, gap_seconds: float = 45.0) -> dict[str, Any]:
    """Sync every Coles/CommBank credential one-by-one (never concurrent)."""
    from app.models import SourceCredential
    from app.services.sync import SyncError, sync_coles_source, sync_commbank_source

    rows = (
        SourceCredential.query.filter(SourceCredential.source_type.in_(SYNCABLE))
        .order_by(SourceCredential.source_type.asc(), SourceCredential.person_id.asc())
        .all()
    )
    results: list[dict[str, Any]] = []
    started = datetime.utcnow().isoformat() + "Z"

    for index, cred in enumerate(rows):
        if index > 0 and gap_seconds > 0:
            time.sleep(gap_seconds)

        item: dict[str, Any] = {
            "person_id": cred.person_id,
            "source_type": cred.source_type,
            "credential_id": cred.id,
        }
        try:
            if cred.source_type == "coles":
                outcome = sync_coles_source(cred.person_id)
            elif cred.source_type == "commbank":
                outcome = sync_commbank_source(cred.person_id)
            else:
                continue
            item["ok"] = True
            item["fetched"] = outcome.get("fetched")
            item["imported"] = outcome.get("imported")
            item["updated"] = outcome.get("updated")
            item["skipped"] = outcome.get("skipped")
            item["incremental"] = outcome.get("incremental")
            logger.info(
                "daily_sync ok person=%s source=%s fetched=%s",
                cred.person_id,
                cred.source_type,
                outcome.get("fetched"),
            )
        except SyncError as exc:
            item["ok"] = False
            item["error"] = exc.message
            item["status_code"] = exc.status_code
            logger.warning(
                "daily_sync sync_error person=%s source=%s: %s",
                cred.person_id,
                cred.source_type,
                exc.message,
            )
        except Exception as exc:  # noqa: BLE001 — keep going through the queue
            item["ok"] = False
            item["error"] = str(exc)
            logger.exception(
                "daily_sync failed person=%s source=%s",
                cred.person_id,
                cred.source_type,
            )
        results.append(item)

    summary = {
        "started_at": started,
        "finished_at": datetime.utcnow().isoformat() + "Z",
        "credentials": len(rows),
        "ok": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }
    logger.info(
        "daily_sync finished ok=%s failed=%s",
        summary["ok"],
        summary["failed"],
    )
    return summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from app import create_app

    app = create_app()
    with app.app_context():
        gap = float(app.config.get("DAILY_SYNC_GAP_SECONDS") or 45)
        summary = run_daily_sync_all(gap_seconds=gap)
        print(summary)


if __name__ == "__main__":
    main()
