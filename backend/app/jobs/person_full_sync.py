from __future__ import annotations

from typing import Any


def run_person_full_sync(
    person_id: int,
    overwrite: bool = True,
    full_sync: bool = True,
) -> dict[str, Any]:
    """RQ entrypoint — overwrite full sync for all connected sources."""
    from app import create_app
    from app.services.sync import SyncError, sync_person_sources

    app = create_app()
    with app.app_context():
        try:
            return sync_person_sources(
                person_id, overwrite=overwrite, full_sync=full_sync
            )
        except SyncError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
