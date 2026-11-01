from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import bills as bills_service
from app.services import dedup as dedup_service

bp = Blueprint("bills", __name__)


@bp.get("")
@login_required
def list_bills():
    person = current_person()
    source_type = request.args.get("source_type")
    person_id = request.args.get("person_id", type=int)
    category_id = request.args.get("category_id")
    classification_status = request.args.get("classification_status")
    q = request.args.get("q")
    date_from = request.args.get("date_from") or request.args.get("from")
    date_to = request.args.get("date_to") or request.args.get("to")
    limit = request.args.get("limit", default=40, type=int)
    offset = request.args.get("offset", default=0, type=int)
    try:
        result = bills_service.list_bills(
            viewer_person_id=person.id,
            source_type=source_type,
            person_id=person_id,
            category_id=category_id,
            classification_status=classification_status,
            q=q,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except bills_service.BillsError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    bills = result["bills"]
    peer_map = dedup_service.commbank_peer_for(bills)
    payload = []
    for b in bills:
        data = b.to_dict()
        peer = peer_map.get(b.id)
        if peer:
            data["account"] = peer.account
            data["account_person_id"] = peer.person_id
        else:
            data["account_person_id"] = b.person_id
        payload.append(data)
    return jsonify(
        {
            "bills": payload,
            "has_more": result["has_more"],
            "limit": result["limit"],
            "offset": result["offset"],
        }
    )


@bp.get("/<int:bill_id>")
@login_required
def get_bill(bill_id: int):
    person = current_person()
    try:
        bill = bills_service.get_bill(bill_id, viewer_person_id=person.id)
    except bills_service.BillsError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    peer = dedup_service.linked_peer(bill.id)
    return jsonify(
        {
            "bill": bill.to_dict(),
            "dedup_peer": peer.to_dict(include_entries=False) if peer else None,
        }
    )


@bp.post("")
@login_required
def create_bill():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = body.get("person_id") or person.id
    try:
        bill = bills_service.create_manual_bill(
            person_id=int(person_id),
            occurred_at=body.get("occurred_at"),
            merchant=body.get("merchant"),
            currency=body.get("currency") or "AUD",
            note=body.get("note"),
            entries=body.get("entries") or [],
        )
    except (bills_service.BillsError, TypeError, ValueError) as exc:
        if isinstance(exc, bills_service.BillsError):
            return jsonify({"error": exc.message}), exc.status_code
        return jsonify({"error": "invalid request"}), 400
    return jsonify({"bill": bill.to_dict()}), 201


@bp.patch("/<int:bill_id>")
@login_required
def update_bill(bill_id: int):
    body = request.get_json(silent=True) or {}
    person = current_person()
    try:
        bill = bills_service.update_manual_bill(
            bill_id, body, viewer_person_id=person.id
        )
    except bills_service.BillsError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"bill": bill.to_dict()})


@bp.delete("/<int:bill_id>")
@login_required
def delete_bill(bill_id: int):
    person = current_person()
    try:
        bills_service.delete_bill(bill_id, viewer_person_id=person.id)
    except bills_service.BillsError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return "", 204
