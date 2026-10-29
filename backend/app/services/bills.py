from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.extensions import db
from app.models import Bill, Entry, Person
from app.services import households as household_service


class BillsError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _parse_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BillsError(f"invalid {field}") from exc


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise BillsError("occurred_at must be an ISO datetime string")
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError as exc:
        raise BillsError("invalid occurred_at") from exc


def list_bills(
    *,
    viewer_person_id: int,
    source_type: str | None = None,
    person_id: int | None = None,
    category_id: str | None = None,
    classification_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Bill]:
    q = household_service.visible_bills_query(viewer_person_id)
    if source_type:
        q = q.filter(Bill.source_type == source_type)
    if person_id:
        q = q.filter(Bill.person_id == person_id)
    if category_id or classification_status:
        q = q.join(Entry)
        if category_id:
            q = q.filter(Entry.category_id == category_id)
        if classification_status:
            q = q.filter(Entry.classification_status == classification_status)
        q = q.distinct()
    return (
        q.order_by(Bill.occurred_at.desc(), Bill.id.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


def get_bill(bill_id: int, *, viewer_person_id: int) -> Bill:
    bill = db.session.get(Bill, bill_id)
    if not bill or not household_service.bill_visible_to(viewer_person_id, bill):
        raise BillsError("bill not found", 404)
    return bill


def create_manual_bill(
    *,
    person_id: int,
    occurred_at: Any,
    merchant: str | None,
    currency: str,
    note: str | None,
    entries: list[dict[str, Any]],
    auto_classify: bool = True,
) -> Bill:
    if not db.session.get(Person, person_id):
        raise BillsError("person not found", 404)
    if not entries:
        raise BillsError("at least one entry is required")

    try:
        hh = household_service.require_active_household(person_id)
    except household_service.HouseholdError as exc:
        raise BillsError(exc.message, exc.status_code) from exc

    bill = Bill(
        source_type="manual",
        person_id=person_id,
        household_id=hh.id,
        occurred_at=_parse_datetime(occurred_at),
        merchant=merchant,
        currency=(currency or "AUD").upper(),
        note=note,
    )
    db.session.add(bill)
    db.session.flush()

    built: list[Entry] = []
    for raw in entries:
        entry = _build_entry(bill, raw)
        db.session.add(entry)
        built.append(entry)

    db.session.commit()

    if auto_classify:
        from app.services.classify import ClassifyError, classify_entry

        for entry in built:
            if entry.category_id:
                continue
            try:
                classify_entry(entry.id)
            except ClassifyError:
                # Leave unclassified; user can retry from pending / detail UI
                pass

    return get_bill(bill.id)


def update_manual_bill(
    bill_id: int, data: dict[str, Any], *, viewer_person_id: int
) -> Bill:
    bill = get_bill(bill_id, viewer_person_id=viewer_person_id)
    if bill.source_type != "manual":
        raise BillsError("only manual bills can be edited this way", 400)

    if "occurred_at" in data:
        bill.occurred_at = _parse_datetime(data["occurred_at"])
    if "merchant" in data:
        bill.merchant = data["merchant"]
    if "currency" in data and data["currency"]:
        bill.currency = str(data["currency"]).upper()
    if "note" in data:
        bill.note = data["note"]

    if "entries" in data:
        entries = data["entries"]
        if not isinstance(entries, list) or not entries:
            raise BillsError("entries must be a non-empty list")
        bill.entries.clear()
        db.session.flush()
        for raw in entries:
            db.session.add(_build_entry(bill, raw))

    db.session.commit()
    return bill


def delete_bill(bill_id: int, *, viewer_person_id: int) -> None:
    bill = get_bill(bill_id, viewer_person_id=viewer_person_id)
    db.session.delete(bill)
    db.session.commit()


def _build_entry(bill: Bill, raw: dict[str, Any]) -> Entry:
    name = (raw.get("name") or "").strip()
    if not name:
        raise BillsError("entry name is required")

    quantity = _parse_decimal(raw.get("quantity", 1), "quantity")
    discount = _parse_decimal(raw.get("discount", 0), "discount")
    if "amount" in raw and raw["amount"] is not None:
        amount = _parse_decimal(raw["amount"], "amount")
    elif raw.get("unit_price") is not None:
        unit_price = _parse_decimal(raw["unit_price"], "unit_price")
        amount = unit_price * quantity - discount
    else:
        raise BillsError("entry requires amount or unit_price")

    unit_price = (
        _parse_decimal(raw["unit_price"], "unit_price")
        if raw.get("unit_price") is not None
        else None
    )
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        raise BillsError("tags must be a list")

    image_url = raw.get("image_url")
    if image_url is not None:
        image_url = str(image_url).strip() or None

    category_id = raw.get("category_id") or None
    if isinstance(category_id, str):
        category_id = category_id.strip() or None

    from app.services.classify import STATUS_CONFIRMED, STATUS_UNCLASSIFIED

    entry = Entry(
        bill_id=bill.id,
        name=name,
        quantity=quantity,
        unit_price=unit_price,
        discount=discount,
        amount=amount,
        currency=(raw.get("currency") or bill.currency).upper(),
        category_id=category_id,
        tags=tags,
        note=raw.get("note"),
        image_url=image_url,
        classification_status=STATUS_CONFIRMED if category_id else STATUS_UNCLASSIFIED,
        category_confidence=None,
    )
    return entry
