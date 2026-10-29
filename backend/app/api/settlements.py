from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import settlements as settlement_service

bp = Blueprint("settlements", __name__)


@bp.get("")
@login_required
def list_settlements():
    person = current_person()
    try:
        rows = settlement_service.list_settlements(person_id=person.id)
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception as exc:
        # AaRuleError from require_household
        from app.services.aa_rules import AaRuleError

        if isinstance(exc, AaRuleError):
            return jsonify({"error": exc.message}), exc.status_code
        raise
    return jsonify({"settlements": rows})


@bp.post("")
@login_required
def create_settlement():
    person = current_person()
    body = request.get_json(silent=True) or {}
    try:
        row = settlement_service.create_settlement(
            person_id=person.id,
            granularity=body.get("granularity"),
            period_start=body.get("period_start"),
            period_end=body.get("period_end"),
            currency=body.get("currency") or "AUD",
            note=body.get("note"),
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"settlement": row}), 201


@bp.get("/<int:settlement_id>")
@login_required
def get_settlement(settlement_id: int):
    person = current_person()
    try:
        row = settlement_service.get_settlement(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"settlement": row})


@bp.get("/<int:settlement_id>/lines")
@login_required
def settlement_lines(settlement_id: int):
    person = current_person()
    try:
        data = settlement_service.get_settlement_lines(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(data)


@bp.post("/<int:settlement_id>/recompute")
@login_required
def recompute(settlement_id: int):
    person = current_person()
    try:
        row = settlement_service.recompute_settlement(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"settlement": row})


@bp.post("/<int:settlement_id>/confirm")
@login_required
def confirm(settlement_id: int):
    person = current_person()
    try:
        row = settlement_service.confirm_settlement(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"settlement": row})


@bp.post("/<int:settlement_id>/settle")
@login_required
def settle(settlement_id: int):
    person = current_person()
    try:
        row = settlement_service.settle_settlement(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"settlement": row})


@bp.delete("/<int:settlement_id>")
@login_required
def delete_settlement(settlement_id: int):
    person = current_person()
    try:
        settlement_service.delete_settlement(
            person_id=person.id, settlement_id=settlement_id
        )
    except settlement_service.SettlementError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"ok": True})
