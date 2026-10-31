from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
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
from app.sources.openfeed import OpenFeedAdapter, OpenFeedError
from app.sources.wws import WwsAdapter, WwsError

# Re-fetch a short overlap so pending→posted / Flybuys adjustments still land.
_COLES_OVERLAP_DAYS = 2
_OPENFEED_OVERLAP_DAYS = 3


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
    overwrite: bool = False,
    defer_scans: bool = False,
) -> dict[str, Any]:
    from app.jobs.progress import set_progress

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
        raise SyncError(
            "Coles 凭证无法解密（密钥已更换？请到账户 › Coles 重新保存 refresh token）",
            400,
        ) from exc

    # Re-seal under current CREDENTIAL_FERNET_KEY after legacy-key decrypt.
    cred_row.payload_encrypted = encrypt_payload(payload)

    if max_pages is not None:
        payload = {**payload, "max_pages": max_pages}

    force_full = full_sync or overwrite
    runtime = _runtime_credential(
        payload,
        person_id=person_id,
        source_type="coles",
        full_sync=force_full,
        overlap_days=_COLES_OVERLAP_DAYS,
    )

    adapter = ColesAdapter()
    if not adapter.validate_credential(runtime):
        raise SyncError("invalid coles credential: refresh_token required", 400)

    def _fetch_progress(*, current: int, total: int, message: str = "") -> None:
        set_progress(
            stage="coles",
            current=current,
            total=max(total, 1),
            message=message or "拉取 Coles 订单…",
        )

    runtime["_on_progress"] = _fetch_progress
    set_progress(stage="coles", current=0, total=1, message="拉取 Coles 订单…")
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
        overwrite=overwrite,
        scan_related=not defer_scans,
    )
    result["incremental"] = bool((raw.data or {}).get("incremental"))
    result["since"] = (raw.data or {}).get("since")
    result["listed"] = (raw.data or {}).get("listed")
    result["detailed"] = (raw.data or {}).get("detailed")
    result["overwrite"] = overwrite
    return result


def sync_wws_source(
    person_id: int,
    *,
    overwrite: bool = False,
    defer_scans: bool = False,
    full_sync: bool = False,
) -> dict[str, Any]:
    """Import in-store Woolworths purchases from Everyday Rewards eReceipts."""
    from app.jobs.progress import set_progress

    person = db.session.get(Person, person_id)
    if not person:
        raise SyncError("person not found", 404)

    try:
        household = household_service.require_active_household(person_id)
    except household_service.HouseholdError as exc:
        raise SyncError(exc.message, exc.status_code) from exc

    cred_row = SourceCredential.query.filter_by(
        person_id=person_id, source_type="wws"
    ).first()
    if not cred_row:
        raise SyncError("Woolworths is not connected for this person", 400)

    try:
        payload = decrypt_payload(cred_row.payload_encrypted)
    except ValueError as exc:
        raise SyncError("could not decrypt Woolworths credential", 400) from exc

    adapter = WwsAdapter()
    if not adapter.validate_credential(payload):
        raise SyncError("invalid Woolworths credential; reconnect Woolworths", 400)

    def _fetch_progress(*, current: int, total: int, message: str = "") -> None:
        set_progress(
            stage="wws",
            current=current,
            total=max(total, 1),
            message=message or "拉取 Woolworths 收据…",
        )

    since: datetime | None = None
    incremental = False
    if not full_sync:
        watermark = _latest_occurred_at(person_id, "wws")
        if watermark:
            since = watermark - timedelta(days=1)
            incremental = True

    runtime = {**payload, "_on_progress": _fetch_progress}
    set_progress(stage="wws", current=0, total=1, message="读取 Everyday Rewards 收据…")
    try:
        raw = adapter.fetch_raw(runtime)
        drafts = adapter.parse(raw)
    except WwsError as exc:
        raise SyncError(exc.message, exc.status_code or 502) from exc

    cred_row.last_validated_at = datetime.utcnow()
    cred_row.payload_encrypted = encrypt_payload(payload)
    if since is not None:
        drafts = [draft for draft in drafts if draft.occurred_at > since]
    result = _persist_drafts(
        person_id=person_id,
        household_id=household.id,
        source_type="wws",
        adapter=adapter,
        drafts=drafts,
        backfill_images=True,
        overwrite=overwrite,
        scan_related=not defer_scans,
    )
    result["listed"] = (raw.data or {}).get("listed")
    result["detailed"] = (raw.data or {}).get("detailed")
    result["images_matched"] = (raw.data or {}).get("images_matched", 0)
    result["image_candidates_count"] = (raw.data or {}).get(
        "image_candidates_count", 0
    )
    result["image_time_matched_receipts"] = (raw.data or {}).get(
        "image_time_matched_receipts", 0
    )
    result["image_name_matches"] = (raw.data or {}).get("image_name_matches", 0)
    result["image_enrichment_available"] = (raw.data or {}).get(
        "image_enrichment_available", False
    )
    result["image_enrichment_error"] = (raw.data or {}).get(
        "image_enrichment_error"
    )
    result["overwrite"] = overwrite
    result["incremental"] = incremental
    result["since"] = since.isoformat() if since else None
    return result


def sync_commbank_source(
    person_id: int,
    *,
    lookback_days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    full_sync: bool = False,
    overwrite: bool = False,
    defer_scans: bool = False,
) -> dict[str, Any]:
    from app.jobs.progress import set_progress
    from app.sources.openfeed import MAX_LOOKBACK_DAYS

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
        raise SyncError("CommBank 未连接，请通过 OpenFeed 完成授权", 400)

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
    if (full_sync or overwrite) and lookback_days is None and not from_date:
        # An account wide overwrite must not inherit a date range saved by an
        # earlier, narrower sync. OpenFeed exposes at most two years of history.
        payload.pop("from", None)
        if not to_date:
            payload.pop("to", None)
        payload = {
            **payload,
            "lookback_days": MAX_LOOKBACK_DAYS,
        }

    force_full = (
        full_sync or overwrite or bool(from_date) or lookback_days is not None
    )
    runtime = _runtime_credential(
        payload,
        person_id=person_id,
        source_type="commbank",
        full_sync=force_full,
        overlap_days=_OPENFEED_OVERLAP_DAYS,
    )

    adapter = OpenFeedAdapter()
    if not adapter.validate_credential(runtime):
        raise SyncError(
            "invalid CommBank credential: reconnect via OpenFeed authorization",
            400,
        )

    def _fetch_progress(*, current: int, total: int, message: str = "") -> None:
        set_progress(
            stage="commbank",
            current=current,
            total=max(total, 1),
            message=message or "拉取 CommBank 交易…",
        )

    runtime["_on_progress"] = _fetch_progress
    set_progress(stage="commbank", current=0, total=1, message="拉取 CommBank 交易…")
    try:
        raw = adapter.fetch_raw(runtime)
        drafts = adapter.parse(raw)
    except OpenFeedError as exc:
        raise SyncError(exc.message, exc.status_code or 502) from exc

    # Persist rotated refresh_token if OpenFeed issued a new one.
    new_refresh = (raw.data or {}).get("refresh_token")
    if new_refresh and new_refresh != payload.get("refresh_token"):
        payload = {**payload, "refresh_token": new_refresh}
        cred_row.payload_encrypted = encrypt_payload(payload)

    cred_row.last_validated_at = datetime.utcnow()

    result = _persist_drafts(
        person_id=person_id,
        household_id=household.id,
        source_type="commbank",
        adapter=adapter,
        drafts=drafts,
        backfill_images=False,
        overwrite=overwrite,
        scan_related=not defer_scans,
    )
    result["accounts"] = len((raw.data or {}).get("accounts") or [])
    result["from"] = (raw.data or {}).get("from")
    result["to"] = (raw.data or {}).get("to")
    result["incremental"] = bool((raw.data or {}).get("incremental"))
    result["overwrite"] = overwrite
    return result


def _persist_drafts(
    *,
    person_id: int,
    household_id: int,
    source_type: str,
    adapter: Any,
    drafts: list[BillDraft],
    backfill_images: bool,
    overwrite: bool = False,
    scan_related: bool = True,
) -> dict[str, Any]:
    from app.jobs.progress import set_progress

    imported = 0
    skipped = 0
    updated = 0
    classify_ids: list[int] = []
    total = max(len(drafts), 1)
    for idx, draft in enumerate(drafts):
        if idx == 0 or idx == len(drafts) - 1 or idx % 25 == 0:
            set_progress(
                stage=source_type,
                current=idx,
                total=total,
                message=f"写入 {source_type} 账单 {idx}/{len(drafts)}…",
            )
        external_id = adapter.external_id(draft)
        if not external_id:
            continue
        existing = Bill.query.filter_by(
            source_type=source_type, external_id=external_id
        ).first()
        if existing:
            changed, need_classify = _refresh_existing_bill(
                existing, draft, overwrite=overwrite
            )
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
    set_progress(
        stage=source_type,
        current=total,
        total=total,
        message=f"{source_type} 写入完成",
    )

    classify_job_id = None
    # Dedupe while preserving order
    seen: set[int] = set()
    classify_ids = [i for i in classify_ids if not (i in seen or seen.add(i))]
    # Overwrite full sync can touch hundreds of rows — don't auto-flood the
    # classify queue (blocks interactive syncs). User can run 全量 Jev separately.
    if classify_ids and not overwrite:
        classify_job_id = _enqueue_classify(classify_ids)
    elif classify_ids and overwrite:
        classify_ids = []

    dedup_scan = None
    if scan_related and (imported or updated):
        try:
            from app.services import dedup as dedup_service

            dedup_scan = dedup_service.scan_household(household_id)
        except Exception:
            dedup_scan = None

    transfer_scan = None
    if scan_related and source_type == "commbank":
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
        "overwrite": overwrite,
        "classify_job_id": classify_job_id,
        "classify_queued": len(classify_ids) if classify_ids else 0,
        "dedup_scan": dedup_scan,
        "transfer_scan": transfer_scan,
    }


def _enqueue_classify(entry_ids: list[int]) -> str | None:
    from flask import current_app

    try:
        from redis import Redis

        from app.jobs.classify_job import run_classify_batch
        from app.jobs.queues import default_queue

        conn = Redis.from_url(current_app.config["REDIS_URL"])
        job = default_queue(conn).enqueue(
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
    bill: Bill, draft: BillDraft, *, overwrite: bool = False
) -> tuple[bool, list[int]]:
    """Fix generic titles / queue unclassified rows for Jev on re-sync.

    Returns (changed, entry_ids_needing_classify).
    With overwrite=True, always replace bill fields + line items from the source.
    """
    changed = False
    need_classify: list[int] = []
    if overwrite:
        if draft.occurred_at and draft.occurred_at != bill.occurred_at:
            bill.occurred_at = draft.occurred_at
            changed = True
        currency = draft.currency or "AUD"
        if currency != bill.currency:
            bill.currency = currency
            changed = True
        merchant = (draft.merchant or "")[:255] or None
        if merchant != bill.merchant:
            bill.merchant = merchant
            changed = True
        if draft.note != bill.note:
            bill.note = draft.note
            changed = True
        if draft.net_amount is not None and Decimal(str(draft.net_amount)) != bill.net_amount:
            bill.net_amount = draft.net_amount
            changed = True
        need_classify = _replace_bill_entries(bill, draft)
        changed = True
        return changed, need_classify

    if draft.occurred_at and draft.occurred_at != bill.occurred_at:
        # Backfill clock time from provider posting datetime on re-sync.
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
        need_classify = _replace_bill_entries(bill, draft)
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


def _replace_bill_entries(bill: Bill, draft: BillDraft) -> list[int]:
    need_classify: list[int] = []
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
    return need_classify


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


def sync_person_sources(
    person_id: int,
    *,
    overwrite: bool = True,
    full_sync: bool = True,
) -> dict[str, Any]:
    """Sync every connected syncable source for a person (account-page full sync)."""
    from app.jobs.progress import set_progress

    person = db.session.get(Person, person_id)
    if not person:
        raise SyncError("person not found", 404)

    creds = SourceCredential.query.filter_by(person_id=person_id).all()
    types = {c.source_type for c in creds}
    ordered = [t for t in ("commbank", "coles", "wws") if t in types]
    if not ordered:
        raise SyncError("没有已连接的可同步数据源", 400)

    set_progress(
        stage="prepare",
        current=0,
        total=len(ordered),
        message="准备全量同步…",
    )
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    total_steps = len(ordered) + 2
    for i, source_type in enumerate(ordered):
        set_progress(
            stage=source_type,
            current=i,
            total=max(total_steps, 1),
            message=f"同步 {source_type}…",
        )
        try:
            if source_type == "commbank":
                results["commbank"] = sync_commbank_source(
                    person_id,
                    full_sync=full_sync,
                    overwrite=overwrite,
                    defer_scans=True,
                )
            elif source_type == "coles":
                results["coles"] = sync_coles_source(
                    person_id,
                    full_sync=full_sync,
                    overwrite=overwrite,
                    defer_scans=True,
                )
            elif source_type == "wws":
                results["wws"] = sync_wws_source(
                    person_id,
                    overwrite=overwrite,
                    full_sync=full_sync,
                    defer_scans=True,
                )
        except SyncError as exc:
            errors[source_type] = exc.message
            results[source_type] = {
                "error": exc.message,
                "status_code": exc.status_code,
            }
        except Exception as exc:  # noqa: BLE001 — continue other sources and scans
            errors[source_type] = str(exc)
            results[source_type] = {"error": str(exc)}

    successful_sources = [
        name
        for name, result in results.items()
        if isinstance(result, dict) and not result.get("error")
    ]
    dedup_scan = None
    transfer_scan = None
    if successful_sources:
        try:
            household = household_service.require_active_household(person_id)
        except household_service.HouseholdError as exc:
            errors["postprocess"] = exc.message
        else:
            set_progress(
                stage="dedup",
                current=len(ordered),
                total=max(total_steps, 1),
                message="扫描重复账单…",
            )
            try:
                from app.services import dedup as dedup_service

                dedup_scan = dedup_service.scan_household(household.id)
            except Exception as exc:
                dedup_scan = {"error": str(exc)}
                errors["dedup"] = str(exc)

            set_progress(
                stage="internal_transfers",
                current=len(ordered) + 1,
                total=max(total_steps, 1),
                message="扫描内部转账…",
            )
            try:
                from app.services import internal_transfers as transfer_service

                transfer_scan = transfer_service.scan_household(household.id)
            except Exception as exc:
                transfer_scan = {"error": str(exc)}
                errors["internal_transfers"] = str(exc)

    set_progress(
        stage="done",
        current=total_steps,
        total=max(total_steps, 1),
        message="全量同步完成" if not errors else f"同步结束（失败：{'、'.join(errors)}）",
    )
    out: dict[str, Any] = {
        "person_id": person_id,
        "overwrite": overwrite,
        "full_sync": full_sync,
        "sources": ordered,
        "results": results,
        "dedup_scan": dedup_scan,
        "transfer_scan": transfer_scan,
        "errors": errors,
    }
    if errors and not any(
        isinstance(v, dict) and not v.get("error") for v in results.values()
    ):
        # Every source failed — surface top-level error for older UI
        out["error"] = "; ".join(f"{k}: {v}" for k, v in errors.items())
        out["status_code"] = 400
    return out


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
        net_amount=draft.net_amount,
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
