from decimal import Decimal

from app.sources.base import RawPayload
from app.sources.commbank import CommBankAdapter


def test_parse_bank_transactions():
    adapter = CommBankAdapter()
    raw = RawPayload(
        data={
            "transactions": [
                {
                    "id": "txn_1",
                    "date": "2026-10-08",
                    "description": "Woolworths Surry Hills",
                    "merchantName": "Woolworths",
                    "amount": -84.20,
                    "currency": "AUD",
                    "category": "Groceries",
                    "pending": False,
                    "accountId": "acc_1",
                    "bankId": "bnk_cba",
                    "_account": {"accountName": "Smart Access"},
                },
                {
                    "id": "txn_2",
                    "date": "2026-10-07",
                    "description": "Salary",
                    "amount": 3200.0,
                    "currency": "AUD",
                    "category": "Income",
                    "pending": False,
                    "accountId": "acc_1",
                    "bankId": "bnk_cba",
                },
                {
                    "id": "txn_pending",
                    "date": "2026-10-09",
                    "description": "Pending",
                    "amount": -10,
                    "currency": "AUD",
                    "pending": True,
                    "accountId": "acc_1",
                    "bankId": "bnk_cba",
                },
            ]
        }
    )
    # parse does not filter pending — fetch_raw does; include pending here
    drafts = adapter.parse(raw)
    assert len(drafts) == 3

    expense = drafts[0]
    assert expense.external_id == "banksync:txn_1"
    assert expense.merchant == "Woolworths"
    assert expense.entries[0].name == "general"
    assert expense.entries[0].amount == Decimal("84.20")
    assert expense.entries[0].category_id is None

    income = drafts[1]
    assert income.entries[0].amount == Decimal("3200.0")
    assert income.entries[0].category_id == "income"

    assert adapter.external_id(expense) == "banksync:txn_1"
