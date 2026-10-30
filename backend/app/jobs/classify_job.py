from __future__ import annotations

from typing import Any


def run_classify_batch(
    entry_ids: list[int] | None = None,
    only_unclassified: bool = True,
    limit: int = 50,
    viewer_person_id: int | None = None,
    full_household: bool = False,
) -> dict[str, Any]:
    from app import create_app
    from app.services.classify import ClassifyError, classify_entries, reclassify_household

    app = create_app()
    with app.app_context():
        try:
            if full_household:
                if viewer_person_id is None:
                    return {"error": "viewer_person_id required", "status_code": 400}
                return reclassify_household(viewer_person_id, limit=limit)
            return classify_entries(
                entry_ids,
                only_unclassified=only_unclassified,
                limit=limit,
                viewer_person_id=viewer_person_id,
            )
        except ClassifyError as exc:
            return {"error": exc.message, "status_code": exc.status_code}
