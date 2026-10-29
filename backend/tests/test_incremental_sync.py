from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.sources.coles import ColesAdapter
from app.sources.commbank import CommBankAdapter, _parse_sync_since


def test_parse_sync_since_date_and_datetime():
    assert _parse_sync_since(None) is None
    d = _parse_sync_since("2026-10-20")
    assert d is not None
    assert d.day == 20
    assert d.tzinfo is not None
    t = _parse_sync_since("2026-10-28T18:03:33.36Z")
    assert t is not None
    assert t.hour == 18


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
    assert detailed == ["1", "2"]
    assert raw.data["listed"] == 3  # scanned until watermark hit on page 2


def test_commbank_uses_since_as_from(monkeypatch):
    adapter = CommBankAdapter()
    calls: list[dict] = []

    class FakeClient:
        def resolve_commbank(self, bank_id):
            return {"id": "fiskil_2", "name": "CommBank"}

        def list_accounts(self, bank_id):
            return [
                {
                    "id": "acc1",
                    "accountName": "Smart Access",
                    "accountNumber": "11070639",
                }
            ]

        def list_transactions(self, bank_id, account_id, *, from_date, to_date, cursor=None):
            calls.append({"from": from_date, "to": to_date, "cursor": cursor})
            return {"data": [], "meta": {"hasMore": False}}

    monkeypatch.setattr(
        "app.sources.commbank._resolve_api_key", lambda cred: "key"
    )
    monkeypatch.setattr(
        "app.sources.commbank._BankSyncClient", lambda key: FakeClient()
    )

    raw = adapter.fetch_raw(
        {
            "account_numbers": ["11070639"],
            "incremental": True,
            "since": "2026-10-26T05:05:15",
            "lookback_days": 90,
        }
    )
    assert raw.data["incremental"] is True
    assert raw.data["from"] == "2026-10-26"
    assert calls and calls[0]["from"] == "2026-10-26"
