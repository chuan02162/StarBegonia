from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from app.api.deps import current_person, current_user, login_required
from app.services import auth as auth_service

bp = Blueprint("auth", __name__)


@bp.get("/bootstrap-status")
def bootstrap_status():
    return jsonify({"needs_bootstrap": auth_service.needs_bootstrap()})


@bp.post("/bootstrap")
def bootstrap():
    body = request.get_json(silent=True) or {}
    try:
        user = auth_service.bootstrap_household(
            email=body.get("email", ""),
            password=body.get("password", ""),
            display_name=body.get("display_name", ""),
        )
    except auth_service.AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    try:
        user = auth_service.login(body.get("email", ""), body.get("password", ""))
    except auth_service.AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()})


@bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    try:
        user = auth_service.register_with_invite(
            code=body.get("invite_code", ""),
            email=body.get("email", ""),
            password=body.get("password", ""),
            display_name=body.get("display_name", ""),
        )
    except auth_service.AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


@bp.get("/me")
@login_required
def me():
    return jsonify({"user": current_user().to_dict()})


@bp.get("/invites")
@login_required
def list_invites():
    """Deprecated path — prefer /households/invites. Kept for compatibility."""
    person = current_person()
    invites = auth_service.list_invites(person.id)
    return jsonify({"invites": [i.to_dict() for i in invites]})


@bp.post("/invites")
@login_required
def create_invite():
    body = request.get_json(silent=True) or {}
    person = current_person()
    try:
        invite = auth_service.create_invite(
            created_by_person_id=person.id,
            display_name_hint=body.get("display_name_hint"),
        )
    except auth_service.AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"invite": invite.to_dict()}), 201
