from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import login_required
from app.services import classify as classify_service
from app.services.classify import UNSET

bp = Blueprint("entries", __name__)


@bp.patch("/<int:entry_id>")
@login_required
def patch_entry(entry_id: int):
    body = request.get_json(silent=True) or {}
    try:
        entry = classify_service.update_entry_classification(
            entry_id,
            category_id=body["category_id"] if "category_id" in body else UNSET,
            confirm=bool(body.get("confirm")),
        )
    except classify_service.ClassifyError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"entry": entry.to_dict()})


@bp.post("/<int:entry_id>/classify")
@login_required
def classify_one(entry_id: int):
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", True))
    try:
        entry = classify_service.classify_entry(entry_id, force=force)
    except classify_service.ClassifyError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"entry": entry.to_dict()})
