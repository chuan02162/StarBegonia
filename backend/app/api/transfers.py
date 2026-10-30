from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.deps import current_person, login_required
from app.services import internal_transfers as transfer_service

bp = Blueprint("transfers", __name__)


@bp.post("/scan")
@login_required
def scan():
    person = current_person()
    try:
        result = transfer_service.scan_for_person(person.id)
    except transfer_service.InternalTransferError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.get("/links")
@login_required
def links():
    person = current_person()
    try:
        rows = transfer_service.list_links(person_id=person.id)
    except transfer_service.InternalTransferError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"links": rows})


@bp.post("/links/<int:link_id>/unlink")
@login_required
def unlink(link_id: int):
    person = current_person()
    try:
        result = transfer_service.unlink(person_id=person.id, link_id=link_id)
    except transfer_service.InternalTransferError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)
