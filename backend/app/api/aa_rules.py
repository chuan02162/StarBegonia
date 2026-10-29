from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import current_person, login_required
from app.services import aa_rules as aa_service

bp = Blueprint("aa_rules", __name__)


@bp.get("")
@login_required
def list_aa_rules():
    person = current_person()
    try:
        rules = aa_service.list_rules(person_id=person.id)
    except aa_service.AaRuleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"rules": rules, "aa_residual": aa_service.aa_residual_meta()})


@bp.post("")
@login_required
def create_aa_rule():
    person = current_person()
    body = request.get_json(silent=True) or {}
    try:
        rule = aa_service.create_rule(
            person_id=person.id,
            source_types=body.get("source_types"),
            category_ids=body.get("category_ids"),
            shares=body.get("shares"),
            enabled=body.get("enabled", True),
            name=body.get("name"),
        )
    except aa_service.AaRuleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"rule": rule}), 201


@bp.get("/<int:rule_id>")
@login_required
def get_aa_rule(rule_id: int):
    person = current_person()
    try:
        rule = aa_service.get_rule(person_id=person.id, rule_id=rule_id)
    except aa_service.AaRuleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"rule": rule})


@bp.patch("/<int:rule_id>")
@login_required
def update_aa_rule(rule_id: int):
    person = current_person()
    body = request.get_json(silent=True) or {}
    kwargs: dict = {"person_id": person.id, "rule_id": rule_id}
    if "source_types" in body:
        kwargs["source_types"] = body["source_types"]
    if "category_ids" in body:
        kwargs["category_ids"] = body["category_ids"]
    if "shares" in body:
        kwargs["shares"] = body["shares"]
    if "enabled" in body:
        kwargs["enabled"] = body["enabled"]
    if "name" in body:
        kwargs["name"] = body["name"]
    try:
        rule = aa_service.update_rule(**kwargs)
    except aa_service.AaRuleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"rule": rule})


@bp.delete("/<int:rule_id>")
@login_required
def delete_aa_rule(rule_id: int):
    person = current_person()
    try:
        aa_service.delete_rule(person_id=person.id, rule_id=rule_id)
    except aa_service.AaRuleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"ok": True})
