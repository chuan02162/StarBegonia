from decimal import Decimal

from app.services.settlements import _minimize_transfers, _money


def test_money_rounds():
    assert _money(Decimal("1.005")) == Decimal("1.01")
    assert _money(Decimal("1.004")) == Decimal("1.00")


def test_minimize_transfers():
    # A +30, B -20, C -10 → B→A 20, C→A 10
    transfers = _minimize_transfers(
        {1: Decimal("30"), 2: Decimal("-20"), 3: Decimal("-10")}
    )
    assert transfers == [(2, 1, Decimal("20.00")), (3, 1, Decimal("10.00"))]
