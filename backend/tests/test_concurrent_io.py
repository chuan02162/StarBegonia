from __future__ import annotations

import asyncio
import threading
import time
from contextlib import nullcontext

from app import create_app
from app.config import TestConfig
from app.services import classify
from app.sources.coles import ColesAdapter
from app.sources.openfeed import OpenFeedAdapter


def _counter():
    lock = threading.Lock()
    state = {"active": 0, "maximum": 0}

    def enter():
        with lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])

    def leave():
        with lock:
            state["active"] -= 1

    return state, enter, leave


def test_jev_snapshot_requests_use_bounded_concurrency(monkeypatch):
    state, enter, leave = _counter()

    def fake_classify_entry_state(**kwargs):
        enter()
        try:
            time.sleep(0.02)
            return {"category_id": "other", "confidence": 0.9}
        finally:
            leave()

    class FakeApp:
        def app_context(self):
            return nullcontext()

    monkeypatch.setattr(classify, "classify_entry_state", fake_classify_entry_state)
    snapshots = [
        {
            "name": f"entry {i}",
            "amount": "1.00",
            "merchant": "example",
            "source_type": "commbank",
            "note": None,
            "categories": [],
            "household_context": None,
        }
        for i in range(8)
    ]
    results = asyncio.run(
        classify._classify_snapshots(FakeApp(), snapshots, concurrency=3)
    )

    assert len(results) == 8
    assert all(result["category_id"] == "other" for result in results)
    assert 1 < state["maximum"] <= 3


def test_openfeed_fetches_windows_concurrently_and_preserves_order(monkeypatch):
    import app.sources.openfeed as openfeed

    state, enter, leave = _counter()
    app = create_app(TestConfig)
    monkeypatch.setattr(openfeed, "CHUNK_DAYS", 1)
    monkeypatch.setattr(
        openfeed,
        "refresh_access_token",
        lambda refresh: {"access_token": "access", "refresh_token": refresh},
    )
    monkeypatch.setattr(
        openfeed,
        "_list_all",
        lambda access, path: [{"accountId": "account-1"}],
    )

    def fake_api_get(path, *, access_token, params=None):
        enter()
        try:
            time.sleep(0.02)
            day = params["oldestDate"]
            return {"data": [{"transactionId": day}], "links": {}}
        finally:
            leave()

    monkeypatch.setattr(openfeed, "api_get", fake_api_get)
    with app.app_context():
        raw = OpenFeedAdapter().fetch_raw(
            {
                "refresh_token": "refresh",
                "from": "2026-01-01",
                "to": "2026-01-04",
                "skip_pending": False,
            }
        )

    ids = [txn["transactionId"] for txn in raw.data["transactions"]]
    assert ids == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    ]
    assert 1 < state["maximum"] <= 4


def test_coles_fetches_details_concurrently_and_preserves_order(monkeypatch):
    import app.sources.coles as coles

    state, enter, leave = _counter()
    orders = [
        {"orderId": str(i), "transactionId": f"txn-{i}"}
        for i in range(1, 5)
    ]

    class FakeClient:
        refresh_token = "refresh"
        access_token = "access"

        def __init__(self, cred):
            pass

        def authenticate(self):
            pass

        def list_orders(self, *, page_number, page_size):
            return {"orders": orders, "totalNoOfOrders": len(orders)}

        def get_order(self, order_id, transaction_id):
            enter()
            try:
                time.sleep((5 - int(order_id)) * 0.01)
                return {"orderId": order_id, "transactionBarcode": transaction_id}
            finally:
                leave()

    monkeypatch.setattr(coles, "_ColesClient", FakeClient)
    raw = ColesAdapter().fetch_raw({"refresh_token": "refresh"})

    assert [order["orderId"] for order in raw.data["orders"]] == ["1", "2", "3", "4"]
    assert 1 < state["maximum"] <= 4
