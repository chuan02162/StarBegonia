from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.extensions import db
from app.models import Bill, Entry, Person, SourceCredential
from app.security.crypto import decrypt_payload, encrypt_payload
from app.services import households as household_service
from app.services.classify import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_UNCLASSIFIED,
)
from app.services.titles import is_generic_title
from app.sources.base import BillDraft
from app.sources.coles import ColesAdapter, ColesError
from app.sources.commbank import CommBankAdapter, CommBankError

# Re-fetch a short overlap so pending→posted / Flybuys adjustments still land.
_COLES_OVERLAP_DAYS = 2
_COMMBANK_OVERLAP_DAYS = 3


class SyncError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _latest_occurred_at(person_id: int, source_type: str) -> datetime | None:
    row = (
        Bill.query.filter_by(person_id=person_id, source_type=source_type)
        .order_by(Bill.occurred_at.desc())
        .first()
    )
    return row.occurred_at if row else None


def _runtime_credential(
    payload: dict[str, Any],
    *,
    person_id: int,
    source_type: str,
    full_sync: bool,
    overlap_days: int,
) -> dict[str, Any]:
    """Copy credential and attach incremental watermark (not persisted)."""
    runtime = dict(payload)
    if full_sync or runtime.get("from") or runtime.get("since"):
        runtime["incremental"] = False
        return runtime
    watermark = _latest_occurred_at(person_id, source_type)
    if not watermark:
        runtime["incremental"] = False
        return runtime
    since = watermark - timedelta(days=overlap_days)
    runtime["since"] = since.replace(microsecond=0).isoformat()
    runtime["incremental"] = True
    runtime["watermark"] = watermark.replace(microsecond=0).isoformat()
    return runtime


def sync_coles_source(
    person_id: int,
    *,
    max_pages: int | None = None,
    full_sync: bool = False,
) -> dict[str, Any]:
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

    runtime = _runtime_credential(
        payload,
        person_id=person_id,
        source_type="coles",
        full_sync=full_sync,
        overlap_days=_COLES_OVERLAP_DAYS,
    )

    adapter = ColesAdapter()
    if not adapter.validate_credential(runtime):
        raise SyncError("invalid coles credential: refresh_token required", 400)

    try:
        raw = adapter.fetch_raw(runtime)
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

    result = _persist_drafts(
        person_id=person_id,
        household_id=household.id,
        source_type="coles",
        adapter=adapter,
        drafts=drafts,
        backfill_images=True,
    )
    result["incremental"] = bool((raw.data or {}).get("incremental"))
    result["since"] = (raw.data or {}).get("since")
    result["listed"] = (raw.data or {}).get("listed")
    result["detailed"] = (raw.data or {}).get("detailed")
    return result


def sync_commbank_source(
    person_id: int,
    *,
    lookback_days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
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

    # Explicit from/lookback forces a windowed (non-watermark) pull.
    force_full = full_sync or bool(from_date) or lookback_days is not None
    runtime = _runtime_credential(
        payload,
        person_id=person_id,
        source_type="commbank",
        full_sync=force_full,
        overlap_days=_COMMBANK_OVERLAP_DAYS,
    )

    adapter = CommBankAdapter()
    if not adapter.validate_credential(runtime):
        raise SyncError(
            "invalid commbank credential: BANKSYNC_API_KEY or api_key required",
            400,
        )

    try:
        raw = adapter.fetch_raw(runtime)
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
    result["incremental"] = bool((raw.data or {}).get("incremental"))
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
    classify_ids: list[int] = []
    for draft in drafts:
        external_id = adapter.external_id(draft)
        if not external_id:
            continue
        existing = Bill.query.filter_by(
            source_type=source_type, external_id=external_id
        ).first()
        if existing:
            changed, need_classify = _refresh_existing_bill(existing, draft)
            if backfill_images and _backfill_images(existing, draft):
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
            classify_ids.extend(need_classify)
            continue
        bill = _insert_bill(
            person_id, draft, household_id=household_id, source_type=source_type
        )
        db.session.flush()
        imported += 1
        classify_ids.extend(
            e.id
            for e in bill.entries
            if e.classification_status == STATUS_UNCLASSIFIED
        )

    db.session.commit()

    classify_job_id = None
    # Dedupe while preserving order
    seen: set[int] = set()
    classify_ids = [i for i in classify_ids if not (i in seen or seen.add(i))]
    if classify_ids:
        classify_job_id = _enqueue_classify(classify_ids)

    dedup_scan = None
    if imported or updated:
        try:
            from app.services import dedup as dedup_service

            dedup_scan = dedup_service.scan_household(household_id)
        except Exception:
            dedup_scan = None

    transfer_scan = None
    if source_type == "commbank":
        try:
            from app.services import internal_transfers as transfer_service

            transfer_scan = transfer_service.scan_household(household_id)
        except Exception:
            transfer_scan = None

    return {
        "source_type": source_type,
        "person_id": person_id,
        "fetched": len(drafts),
        "imported": imported,
        "skipped": skipped,
        "updated": updated,
        "classify_job_id": classify_job_id,
        "classify_queued": len(classify_ids) if classify_ids else 0,
        "dedup_scan": dedup_scan,
        "transfer_scan": transfer_scan,
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


def _refresh_existing_bill(
    bill: Bill, draft: BillDraft
) -> tuple[bool, list[int]]:
    """Fix generic titles / apply BankSync category on re-sync.

    Returns (changed, entry_ids_needing_classify).
    """
    changed = False
    need_classify: list[int] = []
    if draft.occurred_at and draft.occurred_at != bill.occurred_at:
        # Backfill clock time from BankSync providerPostingDateTime on re-sync.
        bill.occurred_at = draft.occurred_at
        changed = True
    if draft.merchant and (
        not bill.merchant or is_generic_title(bill.merchant)
    ):
        bill.merchant = draft.merchant[:255]
        changed = True
    if draft.note and draft.note != bill.note:
        bill.note = draft.note
        changed = True

    # Coles (etc.): replace line items when tender total / Flybuys adjustment appears
    if _should_replace_entries(bill, draft):
        for old in list(bill.entries):
            db.session.delete(old)
        db.session.flush()
        for de in draft.entries:
            status = STATUS_CONFIRMED if de.category_id else STATUS_UNCLASSIFIED
            ent = Entry(
                bill_id=bill.id,
                name=de.name,
                quantity=de.quantity,
                unit_price=de.unit_price,
                discount=de.discount,
                amount=de.amount,
                currency=de.currency or bill.currency,
                category_id=de.category_id,
                tags=de.tags or [],
                note=de.note,
                image_url=de.image_url,
                classification_status=status,
            )
            db.session.add(ent)
            db.session.flush()
            if status == STATUS_UNCLASSIFIED:
                need_classify.append(ent.id)
        changed = True
        return changed, need_classify

    draft_entries = list(draft.entries)
    for i, entry in enumerate(bill.entries):
        de = (
            draft_entries[i]
            if i < len(draft_entries)
            else (draft_entries[0] if draft_entries else None)
        )
        if not de:
            continue
        title_fixed = False
        if is_generic_title(entry.name) and de.name and not is_generic_title(de.name):
            entry.name = de.name[:255]
            changed = True
            title_fixed = True
        if de.category_id and entry.classification_status in (
            STATUS_UNCLASSIFIED,
            STATUS_PENDING,
        ):
            entry.category_id = de.category_id
            entry.classification_status = STATUS_CONFIRMED
            entry.category_confidence = None
            changed = True
        elif entry.classification_status == STATUS_UNCLASSIFIED:
            need_classify.append(entry.id)
        elif entry.classification_status == STATUS_PENDING and title_fixed:
            need_classify.append(entry.id)
    return changed, need_classify


def _should_replace_entries(bill: Bill, draft: BillDraft) -> bool:
    if not draft.entries:
        return False
    from decimal import Decimal

    old_total = sum((Decimal(str(e.amount or 0)) for e in bill.entries), Decimal("0"))
    new_total = sum((e.amount for e in draft.entries), Decimal("0"))
    if abs(old_total - new_total) >= Decimal("0.01"):
        return True
    if len(bill.entries) != len(draft.entries):
        return True
    return False


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
