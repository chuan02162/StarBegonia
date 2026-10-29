from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import login_required
from app.services import people as people_service

bp = Blueprint("people", __name__)


@bp.get("")
@login_required
def list_people():
    people = people_service.list_people()
    return jsonify(
        {
            "people": [p.to_dict(include_credentials=True) for p in people],
        }
    )


@bp.get("/<int:person_id>")
@login_required
def get_person(person_id: int):
    try:
        person = people_service.get_person(person_id)
    except people_service.PeopleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"person": person.to_dict(include_credentials=True)})


@bp.patch("/<int:person_id>")
@login_required
def update_person(person_id: int):
    body = request.get_json(silent=True) or {}
    try:
        person = people_service.update_person(
            person_id, display_name=body.get("display_name", "")
        )
    except people_service.PeopleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"person": person.to_dict(include_credentials=True)})


@bp.put("/<int:person_id>/credentials/<source_type>")
@login_required
def upsert_credential(person_id: int, source_type: str):
    body = request.get_json(silent=True) or {}
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return jsonify({"error": "payload object is required"}), 400
    try:
        cred = people_service.upsert_credential(
            person_id,
            source_type=source_type,
            payload=payload,
            label=body.get("label"),
        )
    except people_service.PeopleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"credential": cred.to_public_dict()})


@bp.delete("/<int:person_id>/credentials/<source_type>")
@login_required
def delete_credential(person_id: int, source_type: str):
    try:
        people_service.delete_credential(person_id, source_type)
    except people_service.PeopleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return "", 204
