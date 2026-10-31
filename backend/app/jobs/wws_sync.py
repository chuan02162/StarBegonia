from __future__ import annotations


def run_wws_sync(
    person_id: int, overwrite: bool = False, full_sync: bool = False
) -> dict:
    """RQ entrypoint — sync one person's Woolworths/Rewards receipts."""
    from app import create_app
    from app.services.sync import SyncError, sync_wws_source

    app = create_app()
    with app.app_context():
        try:
            return sync_wws_source(
                person_id, overwrite=overwrite, full_sync=full_sync
            )
        except SyncError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
