from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_

from app.extensions import db
from app.models import Bill, Entry
from app.services import households as household_service
from app.services.categories import get_vocabulary

Granularity = Literal["week", "month", "quarter", "year"]

# Legacy helpers — polarity is amount sign (positive = in, negative = out).
# Kept for internal-transfer heuristics / settlements filters.
INCOME_IDS = {"salary", "interest", "income", "income_other"}
EXCLUDE_IDS = {"transfer"}


def _period_bounds(granularity: Granularity, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        start = start_of_day - timedelta(days=start_of_day.weekday())
        end = start + timedelta(days=7)
    elif granularity == "month":
        start = start_of_day.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    elif granularity == "quarter":
        q = (start_of_day.month - 1) // 3
        start = start_of_day.replace(month=q * 3 + 1, day=1)
        end_month = start.month + 3
        if end_month > 12:
            end = start.replace(year=start.year + 1, month=end_month - 12)
        else:
            end = start.replace(month=end_month)
    else:  # year
        start = start_of_day.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    return start, end


def _series_starts(granularity: Granularity, count: int, *, now: datetime | None = None) -> list[datetime]:
    """Oldest → newest period start timestamps."""
    now = now or datetime.utcnow()
    cur_start, _ = _period_bounds(granularity, now=now)
    starts = [cur_start]
    for _ in range(count - 1):
        prev_end = starts[0]
        # step one period back from prev_end
        probe = prev_end - timedelta(days=1)
        prev_start, _ = _period_bounds(granularity, now=probe)
        starts.insert(0, prev_start)
    return starts


def _label(granularity: Granularity, start: datetime) -> str:
    if granularity == "week":
        return f"{start.month}/{start.day}"
    if granularity == "month":
        return f"{start.year}-{start.month:02d}"
    if granularity == "quarter":
        q = (start.month - 1) // 3 + 1
        return f"{start.year} Q{q}"
    return str(start.year)


def overview(
    *,
    viewer_person_id: int,
    granularity: Granularity = "month",
    series_count: int = 6,
    currency: str = "AUD",
) -> dict[str, Any]:
    series_count = max(1, min(series_count, 24))
    starts = _series_starts(granularity, series_count)
    window_start = starts[0]
    current_start, current_end = _period_bounds(granularity)

    visible_bills = household_service.visible_bills_query(viewer_person_id).all()
    # Skip cross-source dedup secondaries (bank side of a confirmed link)
    visible_ids = [
        b.id for b in visible_bills if not b.dedup_primary_id
    ]
    if not visible_ids:
        rows = []
    else:
        rows = (
            db.session.query(Entry, Bill)
            .join(Bill, Entry.bill_id == Bill.id)
            .filter(
                and_(
                    Bill.id.in_(visible_ids),
                    Bill.occurred_at >= window_start,
                    Bill.occurred_at < current_end,
                    Entry.currency == currency,
                )
            )
            .all()
        )

    cat_labels: dict[str, str] = {}
    try:
        vocab = get_vocabulary()
        cat_labels = {
            c["id"]: c.get("label") or c["id"]
            for c in (vocab.get("categories") or [])
            if c.get("id")
        }
    except FileNotFoundError:
        pass

    expense_by_bucket: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    income_by_bucket: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_source: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    current_expense = Decimal("0")
    current_income = Decimal("0")

    def bucket_index(occurred: datetime) -> int | None:
        for i, s in enumerate(starts):
            nxt = starts[i + 1] if i + 1 < len(starts) else current_end
            if s <= occurred < nxt:
                return i
        return None

    for entry, bill in rows:
        amount = Decimal(entry.amount or 0)
        if amount == 0:
            continue
        cat = entry.category_id or "other"
        bi = bucket_index(bill.occurred_at)
        if bi is None:
            continue
        in_current = current_start <= bill.occurred_at < current_end

        # Polarity from amount sign; Jev category is orthogonal.
        if amount > 0:
            income_by_bucket[bi] += amount
            if in_current:
                current_income += amount
        else:
            exp = abs(amount)
            expense_by_bucket[bi] += exp
            if in_current:
                current_expense += exp
                # Skip transfer in category pie (internal / 不计收支 label)
                if cat not in EXCLUDE_IDS:
                    by_category[cat] += exp
                    by_source[bill.source_type or "unknown"] += exp

    series = []
    for i, s in enumerate(starts):
        exp = expense_by_bucket[i]
        inc = income_by_bucket[i]
        series.append(
            {
                "start": s.isoformat() + "Z",
                "label": _label(granularity, s),
                "expense": str(exp),
                "income": str(inc),
                "balance": str(inc - exp),
            }
        )

    cat_total = sum(by_category.values(), Decimal("0")) or Decimal("1")
    categories = sorted(
        (
            {
                "id": cid,
                "label": cat_labels.get(cid, cid),
                "amount": str(amt),
                "share": float(amt / cat_total),
            }
            for cid, amt in by_category.items()
        ),
        key=lambda x: Decimal(x["amount"]),
        reverse=True,
    )

    src_total = sum(by_source.values(), Decimal("0")) or Decimal("1")
    sources = sorted(
        (
            {
                "id": sid,
                "amount": str(amt),
                "share": float(amt / src_total),
            }
            for sid, amt in by_source.items()
        ),
        key=lambda x: Decimal(x["amount"]),
        reverse=True,
    )

    return {
        "granularity": granularity,
        "currency": currency,
        "period": {
            "start": current_start.isoformat() + "Z",
            "end": current_end.isoformat() + "Z",
            "expense": str(current_expense),
            "income": str(current_income),
            "balance": str(current_income - current_expense),
        },
        "series": series,
        "by_category": categories,
        "by_source": sources,
    }
