from __future__ import annotations

from typing import Any


def run_commbank_sync(
    person_id: int,
    lookback_days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    from app import create_app
    from app.services.sync import SyncError, sync_commbank_source

    app = create_app()
    with app.app_context():
        try:
            return sync_commbank_source(
                person_id,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
                full_sync=full_sync,
                overwrite=overwrite,
            )
        except SyncError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
