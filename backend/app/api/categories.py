from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.deps import current_person, login_required
from app.jobs.classify_job import run_classify_batch
from app.services import classify as classify_service
from app.services.categories import get_vocabulary

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
    """Classify unclassified (or given) entries via Jev. Async by default."""
    body = request.get_json(silent=True) or {}
    entry_ids = body.get("entry_ids")
    limit = int(body.get("limit") or 50)
    only_unclassified = bool(body.get("only_unclassified", True))
    async_mode = body.get("async", True)

    if async_mode:
        try:
            from rq import Queue

            queue = Queue("default", connection=_redis())
            job = queue.enqueue(
                run_classify_batch,
                entry_ids,
                only_unclassified,
                limit,
                job_timeout=1800,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued"}), 202
        except Exception:
            pass

    try:
        result = classify_service.classify_entries(
            entry_ids,
            only_unclassified=only_unclassified,
            limit=limit,
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

    payload: dict = {"job_id": job.id, "status": job.get_status()}
    if job.is_finished:
        payload["result"] = job.result
    if job.is_failed:
        payload["error"] = str(job.exc_info or "failed")
    return jsonify(payload)
