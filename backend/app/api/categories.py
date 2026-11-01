from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.deps import current_person, login_required
from app.extensions import db
from app.jobs.classify_job import run_classify_batch
from app.jobs.progress import job_progress_payload
from app.jobs.queues import default_queue
from app.models import ClassificationRule
from app.services import classify as classify_service
from app.services import households as household_service
from app.services.categories import get_vocabulary
from app.services.classification_rules import (
    apply_rules_to_household,
    count_matches,
    merge_rules,
)

bp = Blueprint("categories", __name__)


def _redis() -> Redis:
    return Redis.from_url(current_app.config["REDIS_URL"])


@bp.get("")
@login_required
def get_categories():
    try:
        vocab = get_vocabulary()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(vocab)


def _active_household():
    person = current_person()
    return household_service.require_active_household(person.id)


def _validate_keywords(keywords) -> list[str] | None:
    if not isinstance(keywords, list) or not keywords:
        return None
    cleaned = []
    for kw in keywords:
        if not isinstance(kw, str) or not kw.strip():
            return None
        cleaned.append(kw.strip())
    if not cleaned or len(cleaned) > 40:
        return None
    return cleaned


@bp.get("/rules")
@login_required
def list_classification_rules():
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    rules = (
        ClassificationRule.query.filter_by(household_id=household.id)
        .order_by(ClassificationRule.position.asc(), ClassificationRule.id.asc())
        .all()
    )
    return jsonify({"rules": [rule.to_dict() for rule in rules]})


@bp.post("/rules")
@login_required
def create_classification_rule():
    body = request.get_json(silent=True) or {}
    category_id = body.get("category_id")
    keywords = _validate_keywords(body.get("keywords"))
    match_field = (body.get("match_field") or "name").strip().lower()
    if not isinstance(category_id, str) or not category_id.strip():
        return jsonify({"error": "category_id is required"}), 400
    if keywords is None:
        return jsonify({"error": "keywords must be a non-empty list of strings"}), 400
    if match_field not in {"name", "merchant"}:
        return jsonify({"error": "match_field must be name or merchant"}), 400

    vocab = get_vocabulary()
    valid = {c["id"] for c in (vocab.get("categories") or []) if c.get("id")}
    if category_id not in valid:
        return jsonify({"error": "unknown category_id"}), 400

    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    max_pos = (
        db.session.query(db.func.max(ClassificationRule.position))
        .filter_by(household_id=household.id)
        .scalar()
    )
    rule = ClassificationRule(
        household_id=household.id,
        category_id=category_id,
        keywords=keywords,
        match_field=match_field,
        enabled=True,
        position=(max_pos or 0) + 1,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify({"rule": rule.to_dict()}), 201


@bp.patch("/rules/<int:rule_id>")
@login_required
def update_classification_rule(rule_id: int):
    body = request.get_json(silent=True) or {}
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    rule = ClassificationRule.query.filter_by(
        id=rule_id, household_id=household.id
    ).first()
    if not rule:
        return jsonify({"error": "rule not found"}), 404

    if "category_id" in body:
        category_id = body.get("category_id")
        vocab = get_vocabulary()
        valid = {c["id"] for c in (vocab.get("categories") or []) if c.get("id")}
        if not isinstance(category_id, str) or category_id not in valid:
            return jsonify({"error": "unknown category_id"}), 400
        rule.category_id = category_id
    if "keywords" in body:
        keywords = _validate_keywords(body.get("keywords"))
        if keywords is None:
            return jsonify({"error": "keywords must be a non-empty list of strings"}), 400
        rule.keywords = keywords
    if "match_field" in body:
        match_field = (body.get("match_field") or "name").strip().lower()
        if match_field not in {"name", "merchant"}:
            return jsonify({"error": "match_field must be name or merchant"}), 400
        rule.match_field = match_field
    if "enabled" in body:
        rule.enabled = bool(body.get("enabled"))
    db.session.commit()
    return jsonify({"rule": rule.to_dict()})


@bp.delete("/rules/<int:rule_id>")
@login_required
def delete_classification_rule(rule_id: int):
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    rule = ClassificationRule.query.filter_by(
        id=rule_id, household_id=household.id
    ).first()
    if not rule:
        return jsonify({"error": "rule not found"}), 404
    db.session.delete(rule)
    db.session.commit()
    return "", 204


@bp.post("/rules/apply")
@login_required
def apply_classification_rules():
    body = request.get_json(silent=True) or {}
    scope = (body.get("scope") or "unclassified").strip().lower()
    if scope not in {"unclassified", "pending", "confirmed"}:
        return jsonify({"error": "invalid scope"}), 400
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    result = apply_rules_to_household(household.id, scope=scope)
    return jsonify(result)


@bp.post("/rules/preview")
@login_required
def preview_classification_rule():
    body = request.get_json(silent=True) or {}
    keywords = body.get("keywords")
    match_field = (body.get("match_field") or "name").strip().lower()
    if not isinstance(keywords, list) or not keywords or not any(
        isinstance(k, str) and k.strip() for k in keywords
    ):
        return jsonify({"matched": 0})
    if match_field not in {"name", "merchant"}:
        return jsonify({"error": "match_field must be name or merchant"}), 400
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    matched = count_matches(household.id, keywords, match_field)
    return jsonify({"matched": matched})


@bp.post("/rules/merge")
@login_required
def merge_classification_rules():
    try:
        household = _active_household()
    except household_service.HouseholdError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    rules = merge_rules(household.id)
    return jsonify({"rules": [rule.to_dict() for rule in rules]})


@bp.get("/pending")
@login_required
def pending_entries():
    person = current_person()
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    entries = classify_service.list_pending_entries(
        viewer_person_id=person.id, limit=limit, offset=offset
    )
    return jsonify(
        {
            "entries": [
                {
                    **e.to_dict(),
                    "bill": {
                        "id": e.bill.id,
                        "merchant": e.bill.merchant,
                        "source_type": e.bill.source_type,
                        "occurred_at": e.bill.occurred_at.isoformat() + "Z",
                        "currency": e.bill.currency,
                    }
                    if e.bill
                    else None,
                }
                for e in entries
            ]
        }
    )


@bp.post("/classify")
@login_required
def classify_batch():
    """Classify unclassified (or given) entries via Jev. Async by default.

    Body flags:
      - only_unclassified (default true)
      - scope=household + full=true → scrub stale cats, force-Jev all visible,
        then rescan internal transfers
    """
    body = request.get_json(silent=True) or {}
    entry_ids = body.get("entry_ids")
    limit = int(body.get("limit") or 50)
    only_unclassified = bool(body.get("only_unclassified", True))
    async_mode = body.get("async", True)
    scope = (body.get("scope") or "").strip().lower()
    full = bool(body.get("full", False))
    person = current_person()
    viewer_person_id = person.id if scope == "household" or full else None
    if full:
        only_unclassified = False
        limit = max(limit, 5000)
        viewer_person_id = person.id

    if async_mode:
        try:
            job = default_queue(_redis()).enqueue(
                run_classify_batch,
                entry_ids,
                only_unclassified,
                limit,
                viewer_person_id,
                full,
                job_timeout=3600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued"}), 202
        except Exception:
            pass

    try:
        if full:
            result = classify_service.reclassify_household(person.id, limit=limit)
        else:
            result = classify_service.classify_entries(
                entry_ids,
                only_unclassified=only_unclassified,
                limit=limit,
                viewer_person_id=viewer_person_id,
            )
    except classify_service.ClassifyError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.get("/jobs/<job_id>")
@login_required
def get_classify_job(job_id: str):
    try:
        job = Job.fetch(job_id, connection=_redis())
    except NoSuchJobError:
        return jsonify({"error": "job not found"}), 404
    except Exception as exc:
        return jsonify({"error": f"could not fetch job: {exc}"}), 503

    status = job.get_status()
    status_value = getattr(status, "value", None) or str(status)
    payload: dict = {"job_id": job.id, "status": status_value}
    progress = job_progress_payload(job)
    if progress:
        payload["progress"] = progress
    elif status_value == "queued":
        payload["progress"] = {
            "percent": 0,
            "message": "排队等待 worker…",
        }
    elif status_value == "started":
        payload["progress"] = {"percent": 0, "message": "分类运行中…"}
    if job.is_finished:
        payload["result"] = job.result
    if job.is_failed:
        payload["error"] = str(job.exc_info or "failed")
    return jsonify(payload)
