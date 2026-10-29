from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models import Bill, DedupLink
from app.services.aa_rules import AaRuleError, require_household

STATUS_UNMATCHED = "unmatched"
STATUS_SUGGESTED = "suggested"  # legacy; scan auto-promotes to linked
STATUS_LINKED = "linked"
STATUS_IGNORED = "ignored"  # legacy; treated as free to re-match

# Prefer detailed retail/manual as primary over bank feed.
_SOURCE_RANK = {
    "coles": 30,
    "manual": 20,
    "commbank": 10,
}

_AMOUNT_TOLERANCE = Decimal("0.01")
# Card posting can lag the retail receipt by a day or so.
_TIME_WINDOW_SECONDS = 2 * 86400


class DedupError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def secondary_bill_ids(household_id: int) -> set[int]:
    rows = DedupLink.query.filter_by(
        household_id=household_id, status=STATUS_LINKED
    ).all()
    return {r.secondary_bill_id for r in rows}


def assign_primary_secondary(a: Bill, b: Bill) -> tuple[Bill, Bill]:
    ra = _SOURCE_RANK.get(a.source_type, 0)
    rb = _SOURCE_RANK.get(b.source_type, 0)
    if ra > rb:
        return a, b
    if rb > ra:
        return b, a
    if len(a.entries) >= len(b.entries):
        return a, b
    return b, a


def match_pair(a: Bill, b: Bill) -> tuple[float, str] | None:
    """Match cross-source bank↔other bills by amount + time proximity.

    Returns (abs_delta_seconds, reason) or None.
    """
    if a.id == b.id:
        return None
    if a.household_id != b.household_id or not a.household_id:
        return None
    if a.currency != b.currency:
        return None
    if a.source_type == b.source_type:
        return None
    sources = {a.source_type, b.source_type}
    if "commbank" not in sources:
        return None

    amt_a = abs(Decimal(str(a.total_amount)))
    amt_b = abs(Decimal(str(b.total_amount)))
    if amt_a <= 0 or abs(amt_a - amt_b) > _AMOUNT_TOLERANCE:
        return None

    delta = abs((a.occurred_at - b.occurred_at).total_seconds())
    if delta > _TIME_WINDOW_SECONDS:
        return None

    reason = f"amount={amt_a}; hours={delta / 3600:.1f}"
    return delta, reason


def _bill_busy(bill_id: int) -> bool:
    q = DedupLink.query.filter(
        DedupLink.status == STATUS_LINKED,
        db.or_(
            DedupLink.primary_bill_id == bill_id,
            DedupLink.secondary_bill_id == bill_id,
        ),
    )
    return db.session.query(q.exists()).scalar()


def _existing_pair(a_id: int, b_id: int) -> DedupLink | None:
    return DedupLink.query.filter(
        db.or_(
            db.and_(
                DedupLink.primary_bill_id == a_id,
                DedupLink.secondary_bill_id == b_id,
            ),
            db.and_(
                DedupLink.primary_bill_id == b_id,
                DedupLink.secondary_bill_id == a_id,
            ),
        )
    ).first()


def _apply_linked(link: DedupLink, primary: Bill, secondary: Bill) -> None:
    link.status = STATUS_LINKED
    link.primary_bill_id = primary.id
    link.secondary_bill_id = secondary.id
    if not link.resolved_at:
        link.resolved_at = datetime.utcnow()
    primary.dedup_status = STATUS_LINKED
    primary.dedup_primary_id = None
    secondary.dedup_status = STATUS_LINKED
    secondary.dedup_primary_id = primary.id


def _promote_legacy_suggestions(household_id: int) -> int:
    """Turn leftover suggested/ignored rows into linked (or drop ignored)."""
    promoted = 0
    rows = DedupLink.query.filter(
        DedupLink.household_id == household_id,
        DedupLink.status.in_([STATUS_SUGGESTED, STATUS_IGNORED]),
    ).all()
    for link in rows:
        if link.status == STATUS_IGNORED:
            db.session.delete(link)
            continue
        primary = db.session.get(Bill, link.primary_bill_id)
        secondary = db.session.get(Bill, link.secondary_bill_id)
        if not primary or not secondary:
            db.session.delete(link)
            continue
        if _bill_busy(primary.id) or _bill_busy(secondary.id):
            # Already linked elsewhere — drop stale suggestion
            db.session.delete(link)
            continue
        _apply_linked(link, *assign_primary_secondary(primary, secondary))
        promoted += 1
    return promoted


def scan_household(household_id: int) -> dict[str, Any]:
    promoted = _promote_legacy_suggestions(household_id)

    bills = (
        Bill.query.filter_by(household_id=household_id)
        .order_by(Bill.occurred_at.desc())
        .limit(800)
        .all()
    )
    created = 0
    refreshed = 0
    considered = 0

    by_amount: dict[str, list[Bill]] = {}
    for bill in bills:
        key = str(abs(Decimal(str(bill.total_amount))).quantize(Decimal("0.01")))
        by_amount.setdefault(key, []).append(bill)

    # Greedy: closest time wins among unused bills in each amount bucket.
    used: set[int] = set()
    for group in by_amount.values():
        # Pre-mark already-linked bills
        for bill in group:
            if _bill_busy(bill.id):
                used.add(bill.id)

        candidates: list[tuple[float, Bill, Bill, str]] = []
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                considered += 1
                matched = match_pair(a, b)
                if not matched:
                    continue
                delta, reason = matched
                candidates.append((delta, a, b, reason))
        candidates.sort(key=lambda row: row[0])

        for delta, a, b, reason in candidates:
            if a.id in used or b.id in used:
                continue
            if _bill_busy(a.id) or _bill_busy(b.id):
                used.add(a.id)
                used.add(b.id)
                continue

            primary, secondary = assign_primary_secondary(a, b)
            existing = _existing_pair(a.id, b.id)
            score = Decimal("1") - (
                Decimal(str(delta)) / Decimal(str(_TIME_WINDOW_SECONDS))
            )
            score = max(Decimal("0"), min(Decimal("0.99"), score.quantize(Decimal("0.0001"))))

            if existing:
                if existing.status == STATUS_LINKED:
                    used.add(a.id)
                    used.add(b.id)
                    continue
                existing.score = score
                existing.reason = reason[:255]
                _apply_linked(existing, primary, secondary)
                refreshed += 1
            else:
                link = DedupLink(
                    household_id=household_id,
                    primary_bill_id=primary.id,
                    secondary_bill_id=secondary.id,
                    status=STATUS_LINKED,
                    score=score,
                    reason=reason[:255],
                    resolved_at=datetime.utcnow(),
                )
                db.session.add(link)
                _apply_linked(link, primary, secondary)
                created += 1

            used.add(a.id)
            used.add(b.id)

    db.session.commit()
    return {
        "household_id": household_id,
        "considered_pairs": considered,
        "created": created,
        "refreshed": refreshed,
        "promoted": promoted,
    }


def scan_for_person(person_id: int) -> dict[str, Any]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise DedupError(exc.message, exc.status_code) from exc
    return scan_household(hh.id)


def list_links(
    *,
    person_id: int,
    status: str | None = None,
) -> list[dict[str, Any]]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise DedupError(exc.message, exc.status_code) from exc
    q = DedupLink.query.filter_by(household_id=hh.id)
    # Default: only auto-linked pairs (view for household)
    want = status or STATUS_LINKED
    q = q.filter_by(status=want)
    rows = q.order_by(DedupLink.resolved_at.desc().nullslast(), DedupLink.id.desc()).limit(
        200
    ).all()
    return [r.to_dict(include_bills=True) for r in rows]


def _get_link_for_person(person_id: int, link_id: int) -> DedupLink:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise DedupError(exc.message, exc.status_code) from exc
    link = db.session.get(DedupLink, link_id)
    if not link or link.household_id != hh.id:
        raise DedupError("link not found", 404)
    return link


def unlink(*, person_id: int, link_id: int) -> dict[str, Any]:
    link = _get_link_for_person(person_id, link_id)
    primary = db.session.get(Bill, link.primary_bill_id)
    secondary = db.session.get(Bill, link.secondary_bill_id)
    for bill in (primary, secondary):
        if not bill:
            continue
        bill.dedup_status = STATUS_UNMATCHED
        bill.dedup_primary_id = None
    db.session.delete(link)
    db.session.commit()
    return {"ok": True, "link_id": link_id}
