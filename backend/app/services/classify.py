from __future__ import annotations

from typing import Any

from flask import current_app

from app.extensions import db
from app.models import Bill, Entry
from app.services.categories import get_vocabulary
from app.services.jev import JevError, classify_entry_state


class ClassifyError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


STATUS_UNCLASSIFIED = "unclassified"
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"


def classify_entry(entry_id: int, *, force: bool = False) -> Entry:
    entry = db.session.get(Entry, entry_id)
    if not entry:
        raise ClassifyError("entry not found", 404)
    if (
        not force
        and entry.classification_status == STATUS_CONFIRMED
        and entry.category_id
    ):
        return entry

    vocab = get_vocabulary()
    categories = vocab.get("categories") or []
    bill = entry.bill

    try:
        result = classify_entry_state(
            name=entry.name,
            amount=str(entry.amount),
            merchant=bill.merchant if bill else None,
            source_type=bill.source_type if bill else None,
            note=entry.note or (bill.note if bill else None),
            categories=categories,
        )
    except JevError as exc:
        raise ClassifyError(exc.message, exc.status_code or 502) from exc

    category_id = result.get("category_id")
    confidence = result.get("confidence")
    threshold = float(current_app.config.get("JEV_CONFIDENCE_THRESHOLD", 0.7))

    if category_id:
        entry.category_id = category_id
    entry.category_confidence = confidence
    entry.tags = []

    if confidence is not None and confidence >= threshold and category_id:
        entry.classification_status = STATUS_CONFIRMED
    elif category_id:
        entry.classification_status = STATUS_PENDING
    else:
        entry.classification_status = STATUS_UNCLASSIFIED

    db.session.commit()
    return entry


def classify_entries(
    entry_ids: list[int] | None = None,
    *,
    only_unclassified: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    q = Entry.query
    if entry_ids is not None:
        q = q.filter(Entry.id.in_(entry_ids))
    elif only_unclassified:
        q = q.filter(Entry.classification_status == STATUS_UNCLASSIFIED)

    entries = q.order_by(Entry.id.asc()).limit(min(limit, 200)).all()
    classified = 0
    pending = 0
    failed: list[dict[str, Any]] = []

    for entry in entries:
        try:
            classify_entry(entry.id, force=True)
            classified += 1
            refreshed = db.session.get(Entry, entry.id)
            if refreshed and refreshed.classification_status == STATUS_PENDING:
                pending += 1
        except ClassifyError as exc:
            failed.append({"entry_id": entry.id, "error": exc.message})
            db.session.rollback()

    return {
        "requested": len(entries),
        "classified": classified,
        "pending_after": pending,
        "failed": failed,
    }


def classify_bill_entries(bill_id: int) -> dict[str, Any]:
    bill = db.session.get(Bill, bill_id)
    if not bill:
        raise ClassifyError("bill not found", 404)
    ids = [e.id for e in bill.entries if e.classification_status != STATUS_CONFIRMED]
    return classify_entries(ids, only_unclassified=False, limit=len(ids) or 1)


def list_pending_entries(
    *, viewer_person_id: int, limit: int = 50, offset: int = 0
) -> list[Entry]:
    from app.services import households as household_service

    visible_ids = [
        b.id for b in household_service.visible_bills_query(viewer_person_id).all()
    ]
    if not visible_ids:
        return []
    return (
        Entry.query.filter(
            Entry.classification_status == STATUS_PENDING,
            Entry.bill_id.in_(visible_ids),
        )
        .order_by(Entry.id.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


UNSET = object()


def update_entry_classification(
    entry_id: int,
    *,
    category_id: Any = UNSET,
    confirm: bool = False,
) -> Entry:
    entry = db.session.get(Entry, entry_id)
    if not entry:
        raise ClassifyError("entry not found", 404)

    vocab = get_vocabulary()
    valid_cats = {c["id"] for c in (vocab.get("categories") or []) if c.get("id")}

    changed = False
    if category_id is not UNSET:
        if category_id in (None, ""):
            entry.category_id = None
            entry.classification_status = STATUS_UNCLASSIFIED
            entry.category_confidence = None
            db.session.commit()
            return entry
        if category_id not in valid_cats:
            raise ClassifyError(f"unknown category_id: {category_id}")
        entry.category_id = category_id
        changed = True

    if confirm or changed:
        if entry.category_id:
            entry.classification_status = STATUS_CONFIRMED
        elif confirm:
            raise ClassifyError("cannot confirm without category_id")

    db.session.commit()
    return entry
