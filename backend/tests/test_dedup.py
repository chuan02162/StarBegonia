from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.dedup import assign_primary_secondary, match_pair


def _bill(
    *,
    id: int,
    source: str,
    amount: str,
    merchant: str,
    occurred: datetime,
    entry_name: str = "",
    currency: str = "AUD",
    household_id: int = 1,
):
    entry = SimpleNamespace(name=entry_name or merchant)
    return SimpleNamespace(
        id=id,
        source_type=source,
        household_id=household_id,
        currency=currency,
        merchant=merchant,
        occurred_at=occurred,
        total_amount=Decimal(amount),
        entries=[entry],
    )


def test_assign_primary_prefers_coles():
    coles = _bill(
        id=1,
        source="coles",
        amount="84.20",
        merchant="Coles",
        occurred=datetime(2026, 10, 1),
    )
    bank = _bill(
        id=2,
        source="commbank",
        amount="84.20",
        merchant="Coles 0768 Epping",
        occurred=datetime(2026, 10, 1),
    )
    primary, secondary = assign_primary_secondary(bank, coles)
    assert primary.id == 1
    assert secondary.id == 2


def test_match_pair_by_amount_and_time():
    t0 = datetime(2026, 10, 5, 12, 0, 0)
    a = _bill(
        id=10,
        source="coles",
        amount="42.50",
        merchant="Coles Epping",
        occurred=t0,
    )
    b = _bill(
        id=11,
        source="commbank",
        amount="42.50",
        merchant="Card xx7130",
        occurred=t0 + timedelta(hours=5),
    )
    matched = match_pair(a, b)
    assert matched is not None
    delta, reason = matched
    assert delta == 5 * 3600
    assert "amount=42.50" in reason


def test_match_pair_rejects_far_date_or_amount():
    t0 = datetime(2026, 10, 5)
    a = _bill(
        id=1,
        source="coles",
        amount="10.00",
        merchant="Coles",
        occurred=t0,
    )
    b = _bill(
        id=2,
        source="commbank",
        amount="10.00",
        merchant="Coles",
        occurred=t0 + timedelta(days=3),
    )
    assert match_pair(a, b) is None

    c = _bill(
        id=3,
        source="commbank",
        amount="11.00",
        merchant="Coles",
        occurred=t0,
    )
    assert match_pair(a, c) is None


def test_match_pair_requires_bank_leg():
    t0 = datetime(2026, 10, 5)
    a = _bill(
        id=1,
        source="coles",
        amount="10.00",
        merchant="Coles",
        occurred=t0,
    )
    b = _bill(
        id=2,
        source="manual",
        amount="10.00",
        merchant="Coles",
        occurred=t0,
    )
    assert match_pair(a, b) is None
