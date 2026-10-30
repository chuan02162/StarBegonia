from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, redirect, request
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.deps import current_person, login_required
from app.extensions import db
from app.jobs.coles_sync import run_coles_sync
from app.jobs.openfeed_sync import run_openfeed_sync
from app.models import SourceCredential
from app.security.crypto import decrypt_payload, encrypt_payload
from app.services import openfeed_auth
from app.services.openfeed_auth import OpenFeedAuthError
from app.services.sync import SyncError, sync_coles_source, sync_openfeed_source
from app.sources import list_sources
from app.sources.openfeed import MAX_LOOKBACK_DAYS

bp = Blueprint("sources", __name__)


def _redis() -> Redis:
    return Redis.from_url(current_app.config["REDIS_URL"])


@bp.get("")
@login_required
def get_sources():
    return jsonify({"sources": list_sources()})


@bp.get("/.well-known/jwks.json")
@bp.get("/openfeed/jwks.json")
def openfeed_jwks():
    """Public App JWKS for OpenFeed dashboard jwksUri registration."""
    try:
        return jsonify(openfeed_auth.app_jwks())
    except OpenFeedAuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code


@bp.get("/openfeed/status")
@login_required
def openfeed_status():
    person = current_person()
    cred = SourceCredential.query.filter_by(
        person_id=person.id, source_type="openfeed"
    ).first()
    payload = None
    if cred:
        try:
            payload = decrypt_payload(cred.payload_encrypted)
        except ValueError:
            payload = None
    return jsonify(
        {
            "app_configured": openfeed_auth.configured(),
            "connected": bool(cred and payload and payload.get("refresh_token")),
            "grant_id": (payload or {}).get("grant_id"),
            "lookback_days": (payload or {}).get("lookback_days", 90),
            "updated_at": cred.updated_at.isoformat() + "Z" if cred else None,
            "jwks_uri": f"{(current_app.config.get('APP_PUBLIC_URL') or '').rstrip('/')}/api/v1/sources/.well-known/jwks.json",
            "public_url": current_app.config.get("APP_PUBLIC_URL") or "",
        }
    )


@bp.get("/openfeed/connect")
@login_required
def openfeed_connect():
    """Start OpenFeed OAuth (PAR → redirect)."""
    person = current_person()
    try:
        url = openfeed_auth.start_authorization(person_id=person.id)
    except OpenFeedAuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"authorize_url": url})


@bp.get("/openfeed/callback")
def openfeed_callback():
    """OAuth redirect_uri — no JWT; person_id recovered from state in Redis."""
    err = request.args.get("error")
    if err:
        return _front_redirect("openfeed", error=err)
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return _front_redirect("openfeed", error="missing_code_or_state")
    try:
        person_id, token = openfeed_auth.exchange_code(code=code, state=state)
    except OpenFeedAuthError as exc:
        return _front_redirect("openfeed", error=exc.message)

    refresh = token.get("refresh_token")
    if not refresh:
        return _front_redirect("openfeed", error="no_refresh_token")

    grant_id = openfeed_auth.grant_id_from_token_response(token)
    _upsert_openfeed_cred(
        person_id,
        {
            "refresh_token": refresh,
            "grant_id": grant_id,
            "lookback_days": 90,
            "skip_pending": True,
        },
    )

    if not grant_id:
        # Phase A — user must complete disclosure consent
        return redirect(openfeed_auth.disclosure_consent_url(person_id=person_id))

    return _front_redirect("openfeed", connected="1")


@bp.get("/openfeed/consent-return")
def openfeed_consent_return():
    """Return from OpenFeed disclosure consent deep-link."""
    consented = (request.args.get("consented") or "").lower() == "true"
    grant_id = request.args.get("grantId") or request.args.get("grant_id")
    person_id_raw = request.args.get("pid")

    if not consented or not grant_id:
        reason = request.args.get("reason") or "consent_declined"
        return _front_redirect("openfeed", error=reason)
    try:
        person_id = int(person_id_raw)
    except (TypeError, ValueError):
        return _front_redirect("openfeed", error="missing_pid_on_consent_return")

    cred = SourceCredential.query.filter_by(
        person_id=person_id, source_type="openfeed"
    ).first()
    if not cred:
        return _front_redirect("openfeed", error="credential_missing_after_consent")

    try:
        payload = decrypt_payload(cred.payload_encrypted)
    except ValueError:
        payload = {}
    payload["grant_id"] = grant_id
    try:
        token = openfeed_auth.refresh_access_token(payload["refresh_token"])
        if token.get("refresh_token"):
            payload["refresh_token"] = token["refresh_token"]
        gid = openfeed_auth.grant_id_from_token_response(token)
        if gid:
            payload["grant_id"] = gid
    except OpenFeedAuthError:
        pass
    cred.payload_encrypted = encrypt_payload(payload)
    cred.last_validated_at = datetime.utcnow()
    db.session.commit()
    return _front_redirect("openfeed", connected="1", grant="1")


@bp.post("/openfeed/sync")
@login_required
def sync_openfeed():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = int(body.get("person_id") or person.id)
    lookback_days = body.get("lookback_days")
    if lookback_days is not None:
        try:
            lookback_days = int(lookback_days)
        except (TypeError, ValueError):
            return jsonify({"error": "lookback_days must be an integer"}), 400
        if lookback_days > MAX_LOOKBACK_DAYS:
            return jsonify(
                {
                    "error": (
                        f"lookback_days max is {MAX_LOOKBACK_DAYS} (~2 years CDR)."
                    )
                }
            ), 400
        if lookback_days < 1:
            return jsonify({"error": "lookback_days must be >= 1"}), 400

        # Persist preferred lookback on credential
        cred = SourceCredential.query.filter_by(
            person_id=person_id, source_type="openfeed"
        ).first()
        if cred:
            try:
                payload = decrypt_payload(cred.payload_encrypted)
                payload["lookback_days"] = lookback_days
                cred.payload_encrypted = encrypt_payload(payload)
                db.session.commit()
            except ValueError:
                pass

    from_date = body.get("from")
    to_date = body.get("to")
    full_sync = bool(body.get("full_sync"))
    async_mode = body.get("async", True)

    if async_mode:
        try:
            from rq import Queue

            timeout = 1800 if (lookback_days or 0) > 120 else 600
            queue = Queue("default", connection=_redis())
            job = queue.enqueue(
                run_openfeed_sync,
                person_id,
                lookback_days,
                from_date,
                to_date,
                full_sync,
                job_timeout=timeout,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued", "person_id": person_id}), 202
        except Exception:
            pass

    try:
        result = sync_openfeed_source(
            person_id,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
            full_sync=full_sync,
        )
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


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
    full_sync = bool(body.get("full_sync"))

    async_mode = body.get("async", True)
    if async_mode:
        try:
            from rq import Queue

            queue = Queue("default", connection=_redis())
            job = queue.enqueue(
                run_coles_sync,
                person_id,
                max_pages,
                full_sync,
                job_timeout=600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued", "person_id": person_id}), 202
        except Exception:
            pass

    try:
        result = sync_coles_source(
            person_id, max_pages=max_pages, full_sync=full_sync
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


def _upsert_openfeed_cred(person_id: int, payload: dict) -> SourceCredential:
    row = SourceCredential.query.filter_by(
        person_id=person_id, source_type="openfeed"
    ).first()
    if row:
        try:
            existing = decrypt_payload(row.payload_encrypted)
        except ValueError:
            existing = {}
        merged = {**existing, **payload}
        row.payload_encrypted = encrypt_payload(merged)
        row.label = row.label or "OpenFeed"
    else:
        row = SourceCredential(
            person_id=person_id,
            source_type="openfeed",
            label="OpenFeed",
            payload_encrypted=encrypt_payload(payload),
        )
        db.session.add(row)
    row.last_validated_at = datetime.utcnow()
    db.session.commit()
    return row


def _front_redirect(source: str, **params: str):
    base = (current_app.config.get("APP_PUBLIC_URL") or "").rstrip("/")
    q = urlencode({k: v for k, v in params.items() if v is not None})
    target = f"{base}/account/sources/{source}"
    if q:
        target = f"{target}?{q}"
    return redirect(target)
