from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.internal_transfers import (
    bill_direction,
    parse_reference,
    pair_candidates,
)


def _bill(
    *,
    id: int,
    amount: str,
    note: str,
    occurred: datetime,
    category_id: str | None = None,
    household_id: int = 1,
    source: str = "commbank",
):
    entry = SimpleNamespace(category_id=category_id, name="x")
    return SimpleNamespace(
        id=id,
        source_type=source,
        household_id=household_id,
        note=note,
        occurred_at=occurred,
        total_amount=Decimal(amount),
        entries=[entry],
    )


def test_parse_reference():
    note = "account=Smart Access; banksync_category=RENT_AND_UTILITIES; type=PAYMENT; ref=N302064669237"
    assert parse_reference(note) == "N302064669237"
    assert parse_reference("no ref here") is None


def test_bill_direction_from_type():
    out = _bill(
        id=1,
        amount="360",
        note="type=PAYMENT; ref=N1",
        occurred=datetime(2026, 10, 20),
        category_id="rent",
    )
    inn = _bill(
        id=2,
        amount="360",
        note="type=TRANSFER_INCOMING; ref=N1",
        occurred=datetime(2026, 10, 20),
        category_id="salary",
    )
    assert bill_direction(out) == "out"
    assert bill_direction(inn) == "in"


def test_pair_candidates_match_real_rent_share():
    t0 = datetime(2026, 10, 20, 6, 36, 32)
    outgoing = _bill(
        id=10,
        amount="360.00",
        note="account=Smart Access; banksync_category=RENT_AND_UTILITIES; type=PAYMENT; ref=N302064669237",
        occurred=t0 + timedelta(hours=1),
        category_id="rent",
    )
    incoming = _bill(
        id=11,
        amount="360.00",
        note="account=Smart Access; banksync_category=INCOME; type=TRANSFER_INCOMING; ref=N302064669237",
        occurred=t0,
        category_id="salary",
    )
    paired = pair_candidates(outgoing, incoming)
    assert paired is not None
    out, inn, delta = paired
    assert out.id == 10
    assert inn.id == 11
    assert delta == 3600


def test_pair_rejects_amount_time_or_missing_ref():
    t0 = datetime(2026, 10, 20)
    base_out = dict(
        id=1,
        amount="360",
        note="type=PAYMENT; ref=N1",
        occurred=t0,
        category_id="rent",
    )
    base_in = dict(
        id=2,
        amount="360",
        note="type=TRANSFER_INCOMING; ref=N1",
        occurred=t0,
        category_id="salary",
    )
    assert pair_candidates(_bill(**base_out), _bill(**{**base_in, "amount": "361"})) is None
    assert (
        pair_candidates(
            _bill(**base_out),
            _bill(**{**base_in, "occurred": t0 + timedelta(days=3)}),
        )
        is None
    )
    assert (
        pair_candidates(
            _bill(**{**base_out, "note": "type=PAYMENT"}),
            _bill(**base_in),
        )
        is None
    )


def test_pair_rejects_landlord_one_sided_or_same_direction():
    t0 = datetime(2026, 10, 20)
    landlord = _bill(
        id=1,
        amount="1520",
        note="type=PAYMENT; ref=N302065324688",
        occurred=t0,
        category_id="rent",
    )
    other = _bill(
        id=2,
        amount="1520",
        note="type=PAYMENT; ref=N302065324688",
        occurred=t0,
        category_id="rent",
    )
    assert pair_candidates(landlord, other) is None

    # different refs — no pair even if amounts match
    a = _bill(
        id=3,
        amount="360",
        note="type=PAYMENT; ref=AAAA",
        occurred=t0,
    )
    b = _bill(
        id=4,
        amount="360",
        note="type=TRANSFER_INCOMING; ref=BBBB",
        occurred=t0,
    )
    assert pair_candidates(a, b) is None
