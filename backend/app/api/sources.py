from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.deps import current_person, login_required
from app.jobs.coles_sync import run_coles_sync
from app.jobs.commbank_sync import run_commbank_sync
from app.services.sync import SyncError, sync_coles_source, sync_commbank_source
from app.sources import list_sources

bp = Blueprint("sources", __name__)


def _redis() -> Redis:
    return Redis.from_url(current_app.config["REDIS_URL"])


@bp.get("")
@login_required
def get_sources():
    return jsonify({"sources": list_sources()})


@bp.post("/coles/sync")
@login_required
def sync_coles():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = int(body.get("person_id") or person.id)
    max_pages = body.get("max_pages")
    if max_pages is not None:
        try:
            max_pages = int(max_pages)
        except (TypeError, ValueError):
            return jsonify({"error": "max_pages must be an integer"}), 400

    async_mode = body.get("async", True)
    if async_mode:
        try:
            from rq import Queue

            queue = Queue("default", connection=_redis())
            job = queue.enqueue(
                run_coles_sync,
                person_id,
                max_pages,
                job_timeout=600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued", "person_id": person_id}), 202
        except Exception:
            pass

    try:
        result = sync_coles_source(person_id, max_pages=max_pages)
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.post("/commbank/sync")
@login_required
def sync_commbank():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = int(body.get("person_id") or person.id)
    lookback_days = body.get("lookback_days")
    if lookback_days is not None:
        try:
            lookback_days = int(lookback_days)
        except (TypeError, ValueError):
            return jsonify({"error": "lookback_days must be an integer"}), 400
    from_date = body.get("from")
    to_date = body.get("to")

    async_mode = body.get("async", True)
    if async_mode:
        try:
            from rq import Queue

            queue = Queue("default", connection=_redis())
            job = queue.enqueue(
                run_commbank_sync,
                person_id,
                lookback_days,
                from_date,
                to_date,
                job_timeout=600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued", "person_id": person_id}), 202
        except Exception:
            pass

    try:
        result = sync_commbank_source(
            person_id,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.get("/jobs/<job_id>")
@login_required
def get_job(job_id: str):
    try:
        job = Job.fetch(job_id, connection=_redis())
    except NoSuchJobError:
        return jsonify({"error": "job not found"}), 404
    except Exception as exc:
        return jsonify({"error": f"could not fetch job: {exc}"}), 503

    status = job.get_status()
    payload: dict = {
        "job_id": job.id,
        "status": status,
    }
    if job.is_finished:
        payload["result"] = job.result
    if job.is_failed:
        payload["error"] = str(job.exc_info or job.latest_result() or "failed")
    return jsonify(payload)
