from __future__ import annotations

from app.sources.coles import ColesAdapter


def test_coles_incremental_stops_before_watermark(monkeypatch):
    adapter = ColesAdapter()
    monkeypatch.setattr("app.sources.coles.PAGE_SIZE", 2)
    pages = {
        1: {
            "totalNoOfOrders": 4,
            "orders": [
                {
                    "orderId": "1",
                    "transactionId": "t1",
                    "orderPlacementTime": "2026-10-28T16:00:00+11:00",
                },
                {
                    "orderId": "2",
                    "transactionId": "t2",
                    "orderPlacementTime": "2026-10-26T10:00:00+11:00",
                },
            ],
        },
        2: {
            "totalNoOfOrders": 4,
            "orders": [
                {
                    "orderId": "3",
                    "transactionId": "t3",
                    "orderPlacementTime": "2026-10-20T10:00:00+11:00",
                },
                {
                    "orderId": "4",
                    "transactionId": "t4",
                    "orderPlacementTime": "2026-09-01T10:00:00+10:00",
                },
            ],
        },
    }
    detailed: list[str] = []

    class FakeClient:
        refresh_token = "r"
        access_token = "a"

        def __init__(self, cred):
            pass

        def authenticate(self):
            return None

        def list_orders(self, *, page_number, page_size):
            return pages[page_number]

        def get_order(self, order_id, transaction_id):
            detailed.append(order_id)
            return {"orderId": order_id, "transactionBarcode": transaction_id, "items": []}

    monkeypatch.setattr("app.sources.coles._ColesClient", FakeClient)

    # since = Oct 25 UTC → keep Oct 28 & Oct 26 local, stop before Oct 20
    raw = adapter.fetch_raw(
        {
            "refresh_token": "x",
            "incremental": True,
            "since": "2026-10-25T00:00:00",
        }
    )
    assert raw.data["incremental"] is True
    assert raw.data["detailed"] == 2
    assert set(detailed) == {"1", "2"}
    assert raw.data["listed"] == 3  # scanned until watermark hit on page 2
