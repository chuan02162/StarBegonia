from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.extensions import db
from app.models import Bill, InternalTransferLink
from app.services.aa_rules import AaRuleError, require_household
from app.services.analytics import INCOME_IDS
from app.services.classify import STATUS_CONFIRMED

STATUS_LINKED = "linked"
_REF_RE = re.compile(r"(?:^|;\s*)ref=([A-Za-z0-9]+)", re.IGNORECASE)
_TYPE_RE = re.compile(r"(?:^|;\s*)type=([A-Za-z0-9_]+)", re.IGNORECASE)
_AMOUNT_TOLERANCE = Decimal("0.01")
_TIME_WINDOW_SECONDS = 48 * 3600
_TRANSFER_CATEGORY = "transfer"

Direction = Literal["in", "out", "unknown"]


class InternalTransferError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def parse_reference(note: str | None) -> str | None:
    if not note:
        return None
    m = _REF_RE.search(note)
    return m.group(1) if m else None


def parse_txn_type(note: str | None) -> str | None:
    if not note:
        return None
    m = _TYPE_RE.search(note)
    return m.group(1).upper() if m else None


def bill_direction(bill: Bill) -> Direction:
    """Infer credit vs debit — note type, then signed amount, then category."""
    txn_type = parse_txn_type(bill.note) or ""
    if txn_type in {
        "TRANSFER_INCOMING",
        "INTEREST_PAID",
        "CREDIT",
        "DEPOSIT",
    }:
        return "in"
    if txn_type in {
        "TRANSFER_OUTGOING",
        "PAYMENT",
        "DEBIT",
        "WITHDRAWAL",
    }:
        return "out"

    total = Decimal(str(bill.total_amount or 0))
    if total > 0:
        return "in"
    if total < 0:
        return "out"

    # Fallback: entry categories
    cats = {e.category_id for e in (bill.entries or []) if e.category_id}
    if cats & INCOME_IDS and not (cats - INCOME_IDS - {_TRANSFER_CATEGORY}):
        return "in"
    if cats and not (cats & INCOME_IDS):
        return "out"
    return "unknown"


def bill_abs_amount(bill: Bill) -> Decimal:
    return abs(Decimal(str(bill.total_amount or 0)))


def _bill_busy(bill_id: int) -> bool:
    q = InternalTransferLink.query.filter(
        InternalTransferLink.status == STATUS_LINKED,
        db.or_(
            InternalTransferLink.outgoing_bill_id == bill_id,
            InternalTransferLink.incoming_bill_id == bill_id,
        ),
    )
    return db.session.query(q.exists()).scalar()


def _snapshot_categories(bill: Bill) -> dict[str, str | None]:
    """Store primary entry category before override (CommBank = one entry)."""
    if not bill.entries:
        return {str(bill.id): None}
    entry = bill.entries[0]
    return {str(bill.id): entry.category_id}


def _apply_transfer_category(bill: Bill) -> None:
    for entry in bill.entries:
        entry.category_id = _TRANSFER_CATEGORY
        entry.classification_status = STATUS_CONFIRMED
        entry.category_confidence = None


def _restore_categories(bill: Bill, previous: dict[str, Any] | None) -> None:
    prev = (previous or {}).get(str(bill.id))
    for entry in bill.entries:
        entry.category_id = prev
        if prev:
            entry.classification_status = STATUS_CONFIRMED
        else:
            entry.classification_status = "unclassified"
        entry.category_confidence = None


def pair_candidates(
    a: Bill, b: Bill, *, max_delta_seconds: float = _TIME_WINDOW_SECONDS
) -> tuple[Bill, Bill, float] | None:
    """Return (outgoing, incoming, abs_delta_seconds) if a valid pair."""
    if a.id == b.id:
        return None
    if a.household_id != b.household_id or not a.household_id:
        return None
    if a.source_type != "commbank" or b.source_type != "commbank":
        return None

    ref_a = parse_reference(a.note)
    ref_b = parse_reference(b.note)
    if not ref_a or ref_a != ref_b:
        return None

    if abs(bill_abs_amount(a) - bill_abs_amount(b)) > _AMOUNT_TOLERANCE:
        return None

    dir_a = bill_direction(a)
    dir_b = bill_direction(b)
    if {dir_a, dir_b} != {"in", "out"}:
        return None

    delta = abs((a.occurred_at - b.occurred_at).total_seconds())
    if delta > max_delta_seconds:
        return None

    outgoing = a if dir_a == "out" else b
    incoming = b if dir_a == "out" else a
    return outgoing, incoming, delta


def scan_household(household_id: int) -> dict[str, Any]:
    bills = (
        Bill.query.filter_by(household_id=household_id, source_type="commbank")
        .order_by(Bill.occurred_at.desc())
        .limit(800)
        .all()
    )

    by_ref: dict[str, list[Bill]] = {}
    for bill in bills:
        ref = parse_reference(bill.note)
        if not ref:
            continue
        by_ref.setdefault(ref, []).append(bill)

    created = 0
    considered = 0
    used: set[int] = set()

    for ref, group in by_ref.items():
        for bill in group:
            if _bill_busy(bill.id):
                used.add(bill.id)

        candidates: list[tuple[float, Bill, Bill]] = []
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                considered += 1
                paired = pair_candidates(a, b)
                if not paired:
                    continue
                outgoing, incoming, delta = paired
                candidates.append((delta, outgoing, incoming))
        candidates.sort(key=lambda row: row[0])

        for delta, outgoing, incoming in candidates:
            if outgoing.id in used or incoming.id in used:
                continue
            if _bill_busy(outgoing.id) or _bill_busy(incoming.id):
                used.add(outgoing.id)
                used.add(incoming.id)
                continue

            prev = {}
            prev.update(_snapshot_categories(outgoing))
            prev.update(_snapshot_categories(incoming))

            link = InternalTransferLink(
                household_id=household_id,
                outgoing_bill_id=outgoing.id,
                incoming_bill_id=incoming.id,
                reference=ref,
                status=STATUS_LINKED,
                previous_categories=prev,
                matched_at=datetime.utcnow(),
            )
            db.session.add(link)
            _apply_transfer_category(outgoing)
            _apply_transfer_category(incoming)
            used.add(outgoing.id)
            used.add(incoming.id)
            created += 1

    db.session.commit()
    return {
        "household_id": household_id,
        "considered_pairs": considered,
        "created": created,
    }


def scan_for_person(person_id: int) -> dict[str, Any]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise InternalTransferError(exc.message, exc.status_code) from exc
    return scan_household(hh.id)


def list_links(*, person_id: int) -> list[dict[str, Any]]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise InternalTransferError(exc.message, exc.status_code) from exc
    rows = (
        InternalTransferLink.query.filter_by(
            household_id=hh.id, status=STATUS_LINKED
        )
        .order_by(InternalTransferLink.matched_at.desc(), InternalTransferLink.id.desc())
        .limit(200)
        .all()
    )
    return [r.to_dict(include_bills=True) for r in rows]


def unlink(*, person_id: int, link_id: int) -> dict[str, Any]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise InternalTransferError(exc.message, exc.status_code) from exc
    link = db.session.get(InternalTransferLink, link_id)
    if not link or link.household_id != hh.id:
        raise InternalTransferError("link not found", 404)

    outgoing = db.session.get(Bill, link.outgoing_bill_id)
    incoming = db.session.get(Bill, link.incoming_bill_id)
    prev = link.previous_categories or {}
    if outgoing:
        _restore_categories(outgoing, prev)
    if incoming:
        _restore_categories(incoming, prev)

    db.session.delete(link)
    db.session.commit()
    return {"ok": True, "link_id": link_id}
