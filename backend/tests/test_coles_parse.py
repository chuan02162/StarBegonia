from decimal import Decimal

from app.sources.base import RawPayload
from app.sources.coles import ColesAdapter


def test_parse_order_detail():
    adapter = ColesAdapter()
    raw = RawPayload(
        data={
            "orders": [
                {
                    "orderId": "7621",
                    "orderStatus": "Completed",
                    "transactionBarcode": "12810260768117762100",
                    "orderPlacementTime": "2026-10-28T16:13:50+11:00",
                    "storeName": "Coles Epping",
                    "orderAttributes": {"orderTotalPrice": 21.81},
                    "items": [
                        {
                            "id": 1,
                            "name": "Coles Full Cream Milk 3L",
                            "brand": "",
                            "imageUris": [{"uri": "/1/2/123.jpg"}],
                            "orderItem": {
                                "quantity": 1,
                                "unitPrice": 4.95,
                                "itemTotalPrice": 4.95,
                                "itemSaving": 0,
                            },
                        },
                        {
                            "id": 2,
                            "name": "Juice",
                            "orderItem": {
                                "quantity": 2,
                                "unitPrice": 1.5,
                                "itemTotalPrice": 3.0,
                                "itemSaving": 0.5,
                            },
                        },
                    ],
                }
            ]
        }
    )
    drafts = adapter.parse(raw)
    assert len(drafts) == 1
    bill = drafts[0]
    assert bill.external_id == "12810260768117762100"
    assert bill.merchant == "Coles Epping"
    assert len(bill.entries) == 2
    assert bill.entries[0].amount == Decimal("4.95")
    assert bill.entries[0].image_url == (
        "https://cdn.productimages.coles.com.au/productimages/1/2/123.jpg"
    )
    assert bill.entries[1].quantity == Decimal("2")
    assert bill.entries[1].discount == Decimal("0.5")
    assert bill.entries[1].image_url is None
    assert adapter.external_id(bill) == bill.external_id


def test_validate_credential():
    adapter = ColesAdapter()
    assert adapter.validate_credential({"refresh_token": "abc"})
    assert not adapter.validate_credential({})
    assert not adapter.validate_credential({"refresh_token": "  "})
