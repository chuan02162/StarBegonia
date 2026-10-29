from __future__ import annotations

from datetime import datetime
from typing import Any

from app.extensions import db
from app.models import Bill, Entry, Person, SourceCredential
from app.security.crypto import decrypt_payload, encrypt_payload
from app.services import households as household_service
from app.services.classify import STATUS_CONFIRMED, STATUS_UNCLASSIFIED
from app.sources.base import BillDraft
from app.sources.coles import ColesAdapter, ColesError
from app.sources.commbank import CommBankAdapter, CommBankError


class SyncError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def sync_coles_source(person_id: int, *, max_pages: int | None = None) -> dict[str, Any]:
    person = db.session.get(Person, person_id)
    if not person:
        raise SyncError("person not found", 404)

    try:
        household = household_service.require_active_household(person_id)
    except household_service.HouseholdError as exc:
        raise SyncError(exc.message, exc.status_code) from exc

    cred_row = SourceCredential.query.filter_by(
        person_id=person_id, source_type="coles"
    ).first()
    if not cred_row:
        raise SyncError("coles credential not configured for this person", 400)

    try:
        payload = decrypt_payload(cred_row.payload_encrypted)
    except ValueError as exc:
        raise SyncError("could not decrypt credential", 400) from exc

    if max_pages is not None:
        payload = {**payload, "max_pages": max_pages}

    adapter = ColesAdapter()
    if not adapter.validate_credential(payload):
        raise SyncError("invalid coles credential: refresh_token required", 400)

    try:
        raw = adapter.fetch_raw(payload)
        drafts = adapter.parse(raw)
    except ColesError as exc:
        raise SyncError(exc.message, exc.status_code or 502) from exc

    new_refresh = (raw.data or {}).get("refresh_token")
    new_access = (raw.data or {}).get("access_token")
    changed = False
    if new_refresh and new_refresh != payload.get("refresh_token"):
        payload["refresh_token"] = new_refresh
        changed = True
    if new_access:
        payload["access_token"] = new_access
        changed = True
    if changed:
        cred_row.payload_encrypted = encrypt_payload(payload)
        cred_row.last_validated_at = datetime.utcnow()

    return _persist_drafts(
        person_id=person_id,
        household_id=household.id,
        source_type="coles",
        adapter=adapter,
        drafts=drafts,
        backfill_images=True,
    )


def sync_commbank_source(
    person_id: int,
    *,
    lookback_days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    person = db.session.get(Person, person_id)
    if not person:
        raise SyncError("person not found", 404)

    try:
        household = household_service.require_active_household(person_id)
    except household_service.HouseholdError as exc:
        raise SyncError(exc.message, exc.status_code) from exc

    cred_row = SourceCredential.query.filter_by(
        person_id=person_id, source_type="commbank"
    ).first()
    if not cred_row:
        raise SyncError("commbank credential not configured for this person", 400)

    try:
        payload = decrypt_payload(cred_row.payload_encrypted)
    except ValueError as exc:
        raise SyncError("could not decrypt credential", 400) from exc

    if lookback_days is not None:
        payload = {**payload, "lookback_days": lookback_days}
    if from_date:
        payload = {**payload, "from": from_date}
    if to_date:
        payload = {**payload, "to": to_date}

    adapter = CommBankAdapter()
    if not adapter.validate_credential(payload):
        raise SyncError(
            "invalid commbank credential: BANKSYNC_API_KEY or api_key required",
            400,
        )

    try:
        raw = adapter.fetch_raw(payload)
        drafts = adapter.parse(raw)
    except CommBankError as exc:
        raise SyncError(exc.message, exc.status_code or 502) from exc

    cred_row.last_validated_at = datetime.utcnow()

    result = _persist_drafts(
        person_id=person_id,
        household_id=household.id,
        source_type="commbank",
        adapter=adapter,
        drafts=drafts,
        backfill_images=False,
    )
    result["bank_id"] = (raw.data or {}).get("bank", {}).get("id")
    result["accounts"] = len((raw.data or {}).get("accounts") or [])
    result["from"] = (raw.data or {}).get("from")
    result["to"] = (raw.data or {}).get("to")
    return result


def _persist_drafts(
    *,
    person_id: int,
    household_id: int,
    source_type: str,
    adapter: Any,
    drafts: list[BillDraft],
    backfill_images: bool,
) -> dict[str, Any]:
    imported = 0
    skipped = 0
    updated = 0
    new_entry_ids: list[int] = []
    for draft in drafts:
        external_id = adapter.external_id(draft)
        if not external_id:
            continue
        existing = Bill.query.filter_by(
            source_type=source_type, external_id=external_id
        ).first()
        if existing:
            if backfill_images and _backfill_images(existing, draft):
                updated += 1
            else:
                skipped += 1
            continue
        bill = _insert_bill(
            person_id, draft, household_id=household_id, source_type=source_type
        )
        db.session.flush()
        imported += 1
        new_entry_ids.extend(e.id for e in bill.entries)

    db.session.commit()

    classify_job_id = None
    # Only enqueue classify for unclassified (skip pre-tagged income)
    classify_ids = [
        eid
        for eid in new_entry_ids
        if (e := db.session.get(Entry, eid))
        and e.classification_status == STATUS_UNCLASSIFIED
    ]
    if classify_ids:
        classify_job_id = _enqueue_classify(classify_ids)

    return {
        "source_type": source_type,
        "person_id": person_id,
        "fetched": len(drafts),
        "imported": imported,
        "skipped": skipped,
        "updated": updated,
        "classify_job_id": classify_job_id,
        "classify_queued": len(classify_ids) if classify_ids else 0,
    }


def _enqueue_classify(entry_ids: list[int]) -> str | None:
    from flask import current_app

    try:
        from redis import Redis
        from rq import Queue

        from app.jobs.classify_job import run_classify_batch

        conn = Redis.from_url(current_app.config["REDIS_URL"])
        queue = Queue("default", connection=conn)
        job = queue.enqueue(
            run_classify_batch,
            entry_ids,
            False,
            len(entry_ids),
            job_timeout=1800,
            result_ttl=3600,
            failure_ttl=3600,
        )
        return job.id
    except Exception:
        try:
            from app.services.classify import classify_entries

            classify_entries(entry_ids, only_unclassified=False, limit=len(entry_ids))
        except Exception:
            pass
        return None


def _backfill_images(bill: Bill, draft: BillDraft) -> bool:
    draft_by_name = {e.name: e for e in draft.entries if e.image_url}
    if not draft_by_name:
        return False
    changed = False
    for entry in bill.entries:
        if entry.image_url:
            continue
        match = draft_by_name.get(entry.name)
        if match and match.image_url:
            entry.image_url = match.image_url
            changed = True
    return changed


def _insert_bill(
    person_id: int,
    draft: BillDraft,
    *,
    household_id: int,
    source_type: str,
) -> Bill:
    bill = Bill(
        source_type=source_type,
        person_id=person_id,
        household_id=household_id,
        occurred_at=draft.occurred_at,
        merchant=draft.merchant,
        currency=draft.currency or "AUD",
        external_id=draft.external_id,
        note=draft.note,
        dedup_status="unmatched",
    )
    db.session.add(bill)
    db.session.flush()
    for entry in draft.entries:
        status = STATUS_CONFIRMED if entry.category_id else STATUS_UNCLASSIFIED
        db.session.add(
            Entry(
                bill_id=bill.id,
                name=entry.name,
                quantity=entry.quantity,
                unit_price=entry.unit_price,
                discount=entry.discount,
                amount=entry.amount,
                currency=entry.currency or bill.currency,
                category_id=entry.category_id,
                tags=entry.tags or [],
                note=entry.note,
                image_url=entry.image_url,
                classification_status=status,
            )
        )
    return bill
