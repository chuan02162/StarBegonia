from __future__ import annotations

from typing import Any


def run_coles_sync(person_id: int, max_pages: int | None = None) -> dict[str, Any]:
    """RQ entrypoint — always open an app context."""
    from app import create_app
    from app.services.sync import SyncError, sync_coles_source

    app = create_app()
    with app.app_context():
        try:
            return sync_coles_source(person_id, max_pages=max_pages)
        except SyncError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
