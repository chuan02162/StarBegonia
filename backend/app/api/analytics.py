from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import analytics as analytics_service

bp = Blueprint("analytics", __name__)

_ALLOWED = {"week", "month", "quarter", "year"}


@bp.get("/overview")
@login_required
def overview():
    person = current_person()
    granularity = (request.args.get("granularity") or "month").lower()
    if granularity not in _ALLOWED:
        return jsonify({"error": "granularity must be week|month|quarter|year"}), 400
    series_count = request.args.get("series_count", default=6, type=int)
    currency = (request.args.get("currency") or "AUD").upper()
    data = analytics_service.overview(
        viewer_person_id=person.id,
        granularity=granularity,  # type: ignore[arg-type]
        series_count=series_count or 6,
        currency=currency,
    )
    return jsonify(data)
