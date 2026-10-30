from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, current_user, login_required
from app.services import households as household_service

bp = Blueprint("households", __name__)


@bp.get("/me")
@login_required
def my_household():
    person = current_person()
    data = household_service.get_household_for_person(person.id)
    pending = household_service.list_pending_email_invites_for_user(current_user())
    return jsonify(
        {
            "household": data,
            "pending_invites": [i.to_dict() for i in pending],
        }
    )


@bp.post("")
@login_required
def create_household():
    body = request.get_json(silent=True) or {}
    person = current_person()
    try:
        hh = household_service.create_household(
            person_id=person.id, name=body.get("name") or ""
        )
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"household": hh.to_dict(include_members=True)}), 201


@bp.patch("/me")
@login_required
def update_my_household():
    body = request.get_json(silent=True) or {}
    person = current_person()
    kwargs: dict = {"person_id": person.id}
    if "name" in body:
        kwargs["name"] = body.get("name")
    if "jev_context" in body:
        kwargs["jev_context"] = body.get("jev_context")
    try:
        hh = household_service.update_household(**kwargs)
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    data = household_service.get_household_for_person(person.id)
    return jsonify({"household": data or hh.to_dict(include_members=True)})


@bp.post("/leave")
@login_required
def leave():
    person = current_person()
    try:
        household_service.leave_household(person_id=person.id)
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"ok": True})


@bp.post("/invites")
@login_required
def create_invite():
    """Owner: create invite code, optionally bind target_email."""
    body = request.get_json(silent=True) or {}
    person = current_person()
    email = body.get("email")
    try:
        if email:
            invite = household_service.invite_by_email(
                person_id=person.id, email=email
            )
        else:
            invite = household_service.create_invite_code(
                person_id=person.id,
                display_name_hint=body.get("display_name_hint"),
            )
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"invite": invite.to_dict()}), 201


@bp.get("/invites")
@login_required
def list_invites():
    person = current_person()
    invites = household_service.list_household_invites(person.id)
    return jsonify({"invites": [i.to_dict() for i in invites]})


@bp.post("/join")
@login_required
def join():
    """Accept invite by code or invite_id (email invite)."""
    body = request.get_json(silent=True) or {}
    person = current_person()
    try:
        hh = household_service.accept_invite(
            person_id=person.id,
            code=body.get("code"),
            invite_id=body.get("invite_id"),
        )
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"household": hh.to_dict(include_members=True)})


@bp.post("/invites/<int:invite_id>/decline")
@login_required
def decline(invite_id: int):
    person = current_person()
    try:
        household_service.decline_invite(person_id=person.id, invite_id=invite_id)
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"ok": True})
