from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from app.extensions import db
from app.models import Bill, Entry, HouseholdMembership, Person, Settlement
from app.services import aa_rules as aa_service
from app.services.aa_rules import AaRuleError, require_household
from app.services.analytics import EXCLUDE_IDS, _period_bounds
from app.services.households import exclude_non_external_bills

Granularity = Literal["week", "month", "quarter", "year"]
STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"
STATUS_SETTLED = "settled"

TWOPLACES = Decimal("0.01")


class SettlementError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _member_names(household_id: int) -> dict[int, str]:
    rows = (
        HouseholdMembership.query.filter_by(household_id=household_id, left_at=None)
        .all()
    )
    out: dict[int, str] = {}
    for m in rows:
        person = m.person or db.session.get(Person, m.person_id)
        out[m.person_id] = (
            (person.display_name if person else None) or f"#{m.person_id}"
        )
    return out


def _parse_dt(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "")
    try:
        if len(raw) <= 10:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
            if end:
                # exclusive end: next day 00:00 if date-only
                from datetime import timedelta

                return dt + timedelta(days=1)
            return dt
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SettlementError(f"invalid datetime: {value}") from exc


def compute_settlement_result(
    *,
    household_id: int,
    period_start: datetime,
    period_end: datetime,
    currency: str = "AUD",
) -> dict[str, Any]:
    """Apply enabled AA rules to expense entries in the period."""
    names = _member_names(household_id)
    # Net: positive means others owe this person (they should receive)
    net: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    residual_total = Decimal("0")
    matched_amount = Decimal("0")
    unmatched_amount = Decimal("0")
    matched_entries = 0
    unmatched_entries = 0
    lines: list[dict[str, Any]] = []

    bills = exclude_non_external_bills(
        Bill.query.filter(
            Bill.household_id == household_id,
            Bill.occurred_at >= period_start,
            Bill.occurred_at < period_end,
            Bill.currency == currency,
        )
    ).order_by(Bill.occurred_at.asc(), Bill.id.asc()).all()

    for bill in bills:
        payer_id = bill.person_id
        payer_name = names.get(payer_id, f"#{payer_id}")
        for entry in bill.entries:
            cat = entry.category_id or "other"
            if cat in EXCLUDE_IDS:
                continue
            raw_amount = Decimal(str(entry.amount or 0))
            # AA only on money-out (negative). Credits/income skipped by sign.
            if raw_amount >= 0:
                continue
            amount = abs(raw_amount)

            base_line = {
                "entry_id": entry.id,
                "bill_id": bill.id,
                "name": entry.name,
                "amount": str(_money(amount)),
                "currency": entry.currency or bill.currency or currency,
                "category_id": entry.category_id,
                "source_type": bill.source_type,
                "merchant": bill.merchant,
                "occurred_at": bill.occurred_at.isoformat() + "Z",
                "payer_person_id": payer_id,
                "payer_display_name": payer_name,
            }

            rule = aa_service.resolve_rule(
                household_id, bill.source_type, entry.category_id
            )
            shares_map = (
                {
                    int(pid): Decimal(str(pct))
                    for pid, pct in (rule.shares or {}).items()
                }
                if rule
                else {}
            )
            if not rule or not shares_map:
                unmatched_amount += amount
                unmatched_entries += 1
                lines.append(
                    {
                        **base_line,
                        "matched": False,
                        "reason": "no_rule" if not rule else "empty_shares",
                        "rule_id": rule.id if rule else None,
                        "rule_name": rule.name if rule else None,
                        "residual_amount": "0.00",
                        "member_shares": {},
                    }
                )
                continue

            matched_amount += amount
            matched_entries += 1
            residual_pct = aa_service.residual_percent(
                {str(k): str(v) for k, v in shares_map.items()}
            )
            residual_amt = _money(amount * residual_pct / Decimal("100"))
            residual_total += residual_amt

            member_shares = {
                str(pid): {
                    "display_name": names.get(pid, f"#{pid}"),
                    "percent": str(pct),
                    "amount": str(_money(amount * pct / Decimal("100"))),
                }
                for pid, pct in shares_map.items()
            }
            lines.append(
                {
                    **base_line,
                    "matched": True,
                    "reason": None,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "residual_amount": str(residual_amt),
                    "member_shares": member_shares,
                }
            )

            # Payer paid `amount`; each member owes their share to the pool.
            # Net: payer +amount, each share-holder -share (including payer).
            net[payer_id] += amount
            for pid, pct in shares_map.items():
                share_amt = _money(amount * pct / Decimal("100"))
                net[pid] -= share_amt

    # Round nets and build minimal transfers
    rounded = {pid: _money(val) for pid, val in net.items() if _money(val) != 0}
    transfers = _minimize_transfers(rounded)

    balances = [
        {
            "person_id": pid,
            "display_name": names.get(pid, f"#{pid}"),
            "net": str(val),
        }
        for pid, val in sorted(rounded.items(), key=lambda x: x[0])
    ]
    transfer_rows = [
        {
            "from_person_id": a,
            "from_display_name": names.get(a, f"#{a}"),
            "to_person_id": b,
            "to_display_name": names.get(b, f"#{b}"),
            "amount": str(amt),
        }
        for a, b, amt in transfers
    ]

    return {
        "currency": currency,
        "entry_count_matched": matched_entries,
        "entry_count_unmatched": unmatched_entries,
        "matched_amount": str(_money(matched_amount)),
        "unmatched_amount": str(_money(unmatched_amount)),
        "residual_total": str(_money(residual_total)),
        "aa_residual": aa_service.aa_residual_meta(),
        "balances": balances,
        "transfers": transfer_rows,
        "lines": lines,
    }


def _minimize_transfers(
    net: dict[int, Decimal],
) -> list[tuple[int, int, Decimal]]:
    debtors = sorted(
        [(pid, -val) for pid, val in net.items() if val < 0],
        key=lambda x: x[1],
        reverse=True,
    )
    creditors = sorted(
        [(pid, val) for pid, val in net.items() if val > 0],
        key=lambda x: x[1],
        reverse=True,
    )
    transfers: list[tuple[int, int, Decimal]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_id, d_amt = debtors[i]
        c_id, c_amt = creditors[j]
        pay = min(d_amt, c_amt)
        if pay > 0:
            transfers.append((d_id, c_id, _money(pay)))
        d_amt -= pay
        c_amt -= pay
        debtors[i] = (d_id, d_amt)
        creditors[j] = (c_id, c_amt)
        if d_amt <= 0:
            i += 1
        if c_amt <= 0:
            j += 1
    return transfers


def list_settlements(*, person_id: int) -> list[dict[str, Any]]:
    hh = require_household(person_id)
    rows = (
        Settlement.query.filter_by(household_id=hh.id)
        .order_by(Settlement.period_start.desc(), Settlement.id.desc())
        .limit(100)
        .all()
    )
    return [r.to_dict() for r in rows]


def get_settlement(*, person_id: int, settlement_id: int) -> dict[str, Any]:
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    return row.to_dict()


def get_settlement_lines(*, person_id: int, settlement_id: int) -> dict[str, Any]:
    """Return per-entry match details; backfill compute if older settlements lack lines."""
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    result = dict(row.result or {})
    lines = result.get("lines")
    if lines is None:
        fresh = compute_settlement_result(
            household_id=hh.id,
            period_start=row.period_start,
            period_end=row.period_end,
            currency=row.currency,
        )
        lines = fresh.get("lines") or []
        # Persist onto draft so UI stays stable; leave confirmed/settled snapshot untouched
        # except injecting lines for display convenience.
        if row.status == STATUS_DRAFT:
            result["lines"] = lines
            for key in (
                "entry_count_matched",
                "entry_count_unmatched",
                "matched_amount",
                "unmatched_amount",
                "residual_total",
                "balances",
                "transfers",
            ):
                if key in fresh:
                    result[key] = fresh[key]
            row.result = result
            db.session.commit()
    matched = [ln for ln in lines if ln.get("matched")]
    unmatched = [ln for ln in lines if not ln.get("matched")]
    return {
        "settlement_id": row.id,
        "currency": row.currency,
        "period_start": row.period_start.isoformat() + "Z",
        "period_end": row.period_end.isoformat() + "Z",
        "status": row.status,
        "matched": matched,
        "unmatched": unmatched,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
    }


def create_settlement(
    *,
    person_id: int,
    granularity: Granularity | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    currency: str = "AUD",
    note: str | None = None,
) -> dict[str, Any]:
    try:
        hh = require_household(person_id)
    except AaRuleError as exc:
        raise SettlementError(exc.message, exc.status_code) from exc

    if granularity:
        if granularity not in ("week", "month", "quarter", "year"):
            raise SettlementError("invalid granularity")
        start, end = _period_bounds(granularity)
        gran = granularity
    else:
        start = _parse_dt(period_start)
        end = _parse_dt(period_end, end=True)
        if not start or not end:
            raise SettlementError("granularity or period_start/period_end required")
        if end <= start:
            raise SettlementError("period_end must be after period_start")
        gran = None

    result = compute_settlement_result(
        household_id=hh.id,
        period_start=start,
        period_end=end,
        currency=(currency or "AUD").upper(),
    )
    row = Settlement(
        household_id=hh.id,
        created_by_person_id=person_id,
        period_start=start,
        period_end=end,
        granularity=gran,
        currency=result["currency"],
        status=STATUS_DRAFT,
        result=result,
        note=(note or "").strip() or None,
    )
    db.session.add(row)
    db.session.commit()
    return row.to_dict()


def confirm_settlement(*, person_id: int, settlement_id: int) -> dict[str, Any]:
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    if row.status not in (STATUS_DRAFT, STATUS_CONFIRMED):
        raise SettlementError("只能确认草稿结算")
    row.status = STATUS_CONFIRMED
    row.confirmed_at = datetime.utcnow()
    db.session.commit()
    return row.to_dict()


def settle_settlement(*, person_id: int, settlement_id: int) -> dict[str, Any]:
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    if row.status == STATUS_DRAFT:
        row.status = STATUS_CONFIRMED
        row.confirmed_at = datetime.utcnow()
    if row.status not in (STATUS_CONFIRMED, STATUS_SETTLED):
        raise SettlementError("状态不允许结清")
    row.status = STATUS_SETTLED
    row.settled_at = datetime.utcnow()
    db.session.commit()
    return row.to_dict()


def delete_settlement(*, person_id: int, settlement_id: int) -> None:
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    if row.status == STATUS_SETTLED:
        raise SettlementError("已结清的结算不能删除")
    db.session.delete(row)
    db.session.commit()


def recompute_settlement(*, person_id: int, settlement_id: int) -> dict[str, Any]:
    hh = require_household(person_id)
    row = db.session.get(Settlement, settlement_id)
    if not row or row.household_id != hh.id:
        raise SettlementError("settlement not found", 404)
    if row.status != STATUS_DRAFT:
        raise SettlementError("只能重算草稿结算")
    row.result = compute_settlement_result(
        household_id=hh.id,
        period_start=row.period_start,
        period_end=row.period_end,
        currency=row.currency,
    )
    db.session.commit()
    return row.to_dict()
