from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import dedup as dedup_service

bp = Blueprint("dedup", __name__)


@bp.post("/scan")
@login_required
def scan():
    person = current_person()
    try:
        result = dedup_service.scan_for_person(person.id)
    except dedup_service.DedupError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.get("/links")
@login_required
def links():
    """List auto-linked dedup pairs for the active household."""
    person = current_person()
    status = request.args.get("status") or "linked"
    try:
        rows = dedup_service.list_links(person_id=person.id, status=status)
    except dedup_service.DedupError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"links": rows})


# Back-compat alias used by older clients
@bp.get("/suggestions")
@login_required
def suggestions():
    return links()


@bp.post("/links/<int:link_id>/unlink")
@login_required
def unlink(link_id: int):
    person = current_person()
    try:
        result = dedup_service.unlink(person_id=person.id, link_id=link_id)
    except dedup_service.DedupError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)
