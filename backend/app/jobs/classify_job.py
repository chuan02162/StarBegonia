from __future__ import annotations

from typing import Any


def run_classify_batch(
    entry_ids: list[int] | None = None,
    only_unclassified: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    from app import create_app
    from app.services.classify import ClassifyError, classify_entries

    app = create_app()
    with app.app_context():
        try:
            return classify_entries(
                entry_ids,
                only_unclassified=only_unclassified,
                limit=limit,
            )
        except ClassifyError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
