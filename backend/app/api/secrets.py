from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import abr as abr_service
from app.services import households as household_service
from app.services import secrets as secrets_service

bp = Blueprint("secrets", __name__)

ALLOWED_KEYS = {"abr_guid", "jev_api_key"}


def _active_household():
    person = current_person()
    return household_service.require_active_household(person.id)


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


@bp.get("")
@login_required
def list_secrets():
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    secrets = {}
    for key in sorted(ALLOWED_KEYS):
        value = secrets_service.get_secret(household.id, key)
        secrets[key] = {"configured": bool(value), "masked": _mask(value)}
    return jsonify({"secrets": secrets})


@bp.put("")
@login_required
def upsert_secret():
    body = request.get_json(silent=True) or {}
    key = str(body.get("key") or "").strip()
    value = body.get("value")
    if key not in ALLOWED_KEYS:
        return jsonify({"error": "unknown key"}), 400
    if value is not None and not isinstance(value, str):
        return jsonify({"error": "value must be a string"}), 400
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    secrets_service.set_secret(household.id, key, value)
    stored = secrets_service.get_secret(household.id, key)
    return jsonify({"key": key, "configured": bool(stored), "masked": _mask(stored)})


@bp.post("/abr/validate")
@login_required
def validate_abr_guid():
    body = request.get_json(silent=True) or {}
    guid = body.get("guid")
    if guid is not None and not isinstance(guid, str):
        return jsonify({"error": "guid must be a string"}), 400
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    if guid is None:
        guid = secrets_service.get_secret(household.id, "abr_guid")
    try:
        result = abr_service.validate_guid(guid)
    except abr_service.AbrError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "names": result.get("names", 0)})
