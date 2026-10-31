from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, redirect, request
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.deps import current_person, login_required
from app.extensions import db
from app.jobs.coles_sync import run_coles_sync
from app.jobs.commbank_sync import run_commbank_sync
from app.jobs.person_full_sync import run_person_full_sync
from app.jobs.wws_sync import run_wws_sync
from app.jobs.progress import job_progress_payload
from app.jobs.queues import sync_queue
from app.models import SourceCredential
from app.security.crypto import decrypt_payload, encrypt_payload
from app.services import openfeed_auth
from app.services.openfeed_auth import OpenFeedAuthError
from app.services.sync import (
    SyncError,
    sync_coles_source,
    sync_commbank_source,
    sync_person_sources,
    sync_wws_source,
)
from app.sources import list_sources
from app.sources.coles import ColesAdapter, ColesError
from app.sources.openfeed import MAX_LOOKBACK_DAYS
from app.sources.wws import WwsAdapter, WwsError

bp = Blueprint("sources", __name__)


@bp.get("/wws/status")
@login_required
def wws_status():
    person = current_person()
    cred = SourceCredential.query.filter_by(
        person_id=person.id, source_type="wws"
    ).first()
    return jsonify(
        {
            "connected": cred is not None,
            "updated_at": cred.updated_at.isoformat() + "Z" if cred else None,
        }
    )


@bp.get("/wws/check")
@login_required
def wws_check():
    person = current_person()
    cred = SourceCredential.query.filter_by(
        person_id=person.id, source_type="wws"
    ).first()
    if not cred:
        return jsonify({"ok": False, "message": "尚未连接"})
    try:
        payload = decrypt_payload(cred.payload_encrypted)
    except ValueError:
        return jsonify({"ok": False, "message": "凭证无法解密"})
    adapter = WwsAdapter()
    if not adapter.validate_credential(payload):
        return jsonify({"ok": False, "message": "凭证无效，请重新连接"})
    try:
        adapter.check(payload)
    except WwsError as exc:
        return jsonify({"ok": False, "message": exc.message})
    return jsonify({"ok": True, "message": "连接正常"})


@bp.delete("/wws/credential")
@login_required
def wws_delete_credential():
    person = current_person()
    row = SourceCredential.query.filter_by(
        person_id=person.id, source_type="wws"
    ).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    return "", 204


@bp.post("/wws/sync")
@login_required
def sync_wws():
    body = request.get_json(silent=True) or {}
    person_id = current_person().id
    overwrite = bool(body.get("overwrite", False))
    full_sync = bool(body.get("full_sync", False))
    async_mode = body.get("async", True)

    if async_mode:
        try:
            job = sync_queue(_redis()).enqueue(
                run_wws_sync,
                person_id,
                overwrite,
                full_sync,
                job_timeout=3600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify(
                {"job_id": job.id, "status": "queued", "person_id": person_id}
            ), 202
        except Exception:
            pass

    try:
        result = sync_wws_source(
            person_id, overwrite=overwrite, full_sync=full_sync
        )
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


def _redis() -> Redis:
    return Redis.from_url(current_app.config["REDIS_URL"])


@bp.get("")
@login_required
def get_sources():
    return jsonify({"sources": list_sources()})


@bp.get("/status")
@login_required
def sources_status():
    """Live connection status for each syncable source (for status dots)."""
    person = current_person()
    out: list[dict[str, Any]] = []
    for source_type in ("coles", "commbank", "wws"):
        connected = False
        cred = SourceCredential.query.filter_by(
            person_id=person.id, source_type=source_type
        ).first()
        payload = None
        if cred:
            try:
                payload = decrypt_payload(cred.payload_encrypted)
            except ValueError:
                payload = None

        if source_type == "commbank":
            connected = bool(payload and payload.get("refresh_token"))
        elif source_type == "wws" and payload and WwsAdapter().validate_credential(payload):
            try:
                WwsAdapter().check(payload)
                connected = True
            except WwsError:
                connected = False
        elif source_type == "coles" and payload and ColesAdapter().validate_credential(payload):
            try:
                updated = ColesAdapter().check(payload)
                connected = True
                if (
                    updated.get("refresh_token") != payload.get("refresh_token")
                    or updated.get("access_token") != payload.get("access_token")
                ):
                    cred.payload_encrypted = encrypt_payload(updated)
                    db.session.commit()
            except ColesError:
                connected = False
        out.append({"source_type": source_type, "connected": connected})
    return jsonify({"sources": out})


@bp.get("/.well-known/jwks.json")
@bp.get("/openfeed/jwks.json")
def openfeed_jwks():
    """Public App JWKS for OpenFeed dashboard jwksUri registration."""
    try:
        return jsonify(openfeed_auth.app_jwks())
    except OpenFeedAuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code


@bp.get("/openfeed/status")
@bp.get("/commbank/status")
@login_required
def commbank_status():
    person = current_person()
    cred = SourceCredential.query.filter_by(
        person_id=person.id, source_type="commbank"
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


@bp.get("/coles/check")
@login_required
def coles_check():
    person = current_person()
    cred = SourceCredential.query.filter_by(
        person_id=person.id, source_type="coles"
    ).first()
    if not cred:
        return jsonify({"ok": False, "message": "尚未连接"})
    try:
        payload = decrypt_payload(cred.payload_encrypted)
    except ValueError:
        return jsonify({"ok": False, "message": "凭证无法解密"})
    adapter = ColesAdapter()
    if not adapter.validate_credential(payload):
        return jsonify({"ok": False, "message": "凭证无效，请重新连接"})
    try:
        updated = adapter.check(payload)
    except ColesError as exc:
        return jsonify({"ok": False, "message": exc.message})
    if (
        updated.get("refresh_token") != payload.get("refresh_token")
        or updated.get("access_token") != payload.get("access_token")
    ):
        cred.payload_encrypted = encrypt_payload(updated)
        db.session.commit()
    return jsonify({"ok": True, "message": "连接正常"})


@bp.get("/openfeed/connect")
@bp.get("/commbank/connect")
@login_required
def commbank_connect():
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
        return _front_redirect("commbank", error=err)
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return _front_redirect("commbank", error="missing_code_or_state")
    try:
        person_id, token = openfeed_auth.exchange_code(code=code, state=state)
    except OpenFeedAuthError as exc:
        return _front_redirect("commbank", error=exc.message)

    refresh = token.get("refresh_token")
    if not refresh:
        return _front_redirect("commbank", error="no_refresh_token")

    grant_id = openfeed_auth.grant_id_from_token_response(token)
    _upsert_commbank_cred(
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
    return _front_redirect("commbank", connected="1")


@bp.get("/openfeed/consent-return")
def openfeed_consent_return():
    """Return from OpenFeed disclosure consent deep-link."""
    consented = (request.args.get("consented") or "").lower() == "true"
    grant_id = request.args.get("grantId") or request.args.get("grant_id")
    person_id_raw = request.args.get("pid")

    if not consented or not grant_id:
        reason = request.args.get("reason") or "consent_declined"
        return _front_redirect("commbank", error=reason)
    try:
        person_id = int(person_id_raw)
    except (TypeError, ValueError):
        return _front_redirect("commbank", error="missing_pid_on_consent_return")

    cred = SourceCredential.query.filter_by(
        person_id=person_id, source_type="commbank"
    ).first()
    if not cred:
        return _front_redirect("commbank", error="credential_missing_after_consent")

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
    return _front_redirect("commbank", connected="1", grant="1")


@bp.post("/openfeed/sync")
@bp.post("/commbank/sync")
@login_required
def sync_commbank():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = person.id
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
            person_id=person_id, source_type="commbank"
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
    overwrite = bool(body.get("overwrite"))
    async_mode = body.get("async", True)

    if async_mode:
        try:
            timeout = 1800 if (lookback_days or 0) > 120 or overwrite else 600
            job = sync_queue(_redis()).enqueue(
                run_commbank_sync,
                person_id,
                lookback_days,
                from_date,
                to_date,
                full_sync,
                overwrite,
                job_timeout=timeout,
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
            full_sync=full_sync,
            overwrite=overwrite,
        )
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.post("/coles/sync")
@login_required
def sync_coles():
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = person.id
    max_pages = body.get("max_pages")
    if max_pages is not None:
        try:
            max_pages = int(max_pages)
        except (TypeError, ValueError):
            return jsonify({"error": "max_pages must be an integer"}), 400
    full_sync = bool(body.get("full_sync"))
    overwrite = bool(body.get("overwrite"))

    async_mode = body.get("async", True)
    if async_mode:
        try:
            job = sync_queue(_redis()).enqueue(
                run_coles_sync,
                person_id,
                max_pages,
                full_sync,
                overwrite,
                job_timeout=600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify({"job_id": job.id, "status": "queued", "person_id": person_id}), 202
        except Exception:
            pass

    try:
        result = sync_coles_source(
            person_id,
            max_pages=max_pages,
            full_sync=full_sync,
            overwrite=overwrite,
        )
    except SyncError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@bp.post("/full-sync")
@login_required
def full_sync_person():
    """Overwrite full sync for every connected source on the account page."""
    body = request.get_json(silent=True) or {}
    person = current_person()
    person_id = person.id
    overwrite = bool(body.get("overwrite", True))
    full_sync = bool(body.get("full_sync", True))
    async_mode = body.get("async", True)

    if async_mode:
        try:
            job = sync_queue(_redis()).enqueue(
                run_person_full_sync,
                person_id,
                overwrite,
                full_sync,
                job_timeout=3600,
                result_ttl=3600,
                failure_ttl=3600,
            )
            return jsonify(
                {"job_id": job.id, "status": "queued", "person_id": person_id}
            ), 202
        except Exception:
            pass

    try:
        result = sync_person_sources(
            person_id, overwrite=overwrite, full_sync=full_sync
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
    status_value = getattr(status, "value", None) or str(status)
    payload: dict = {
        "job_id": job.id,
        "status": status_value,
    }
    progress = job_progress_payload(job)
    if progress:
        payload["progress"] = progress
    elif status_value == "queued":
        payload["progress"] = {
            "percent": 0,
            "message": "排队等待 worker（同步队列优先于分类）…",
        }
    elif status_value == "started":
        payload["progress"] = {"percent": 0, "message": "任务运行中…"}
    if job.is_finished:
        payload["result"] = job.result
    if job.is_failed:
        payload["error"] = str(job.exc_info or job.latest_result() or "failed")
    return jsonify(payload)


def _upsert_commbank_cred(person_id: int, payload: dict) -> SourceCredential:
    row = SourceCredential.query.filter_by(
        person_id=person_id, source_type="commbank"
    ).first()
    if row:
        try:
            existing = decrypt_payload(row.payload_encrypted)
        except ValueError:
            existing = {}
        merged = {**existing, **payload}
        row.payload_encrypted = encrypt_payload(merged)
        row.label = "CommBank"
    else:
        row = SourceCredential(
            person_id=person_id,
            source_type="commbank",
            label="CommBank",
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
