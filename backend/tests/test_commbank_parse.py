from decimal import Decimal

from app.sources.base import RawPayload
from app.sources.commbank import (
    MAX_LOOKBACK_DAYS,
    CommBankAdapter,
    _date_windows,
    _filter_accounts,
)


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
    assert expense.entries[0].name == "Woolworths Surry Hills"
    assert expense.entries[0].amount == Decimal("-84.20")
    assert expense.entries[0].category_id is None

    income = drafts[1]
    assert income.entries[0].name == "Salary"
    assert income.entries[0].amount == Decimal("3200.0")
    assert income.entries[0].category_id is None

    assert adapter.external_id(expense) == "banksync:txn_1"


def test_filter_accounts_by_number():
    accounts = [
        {"id": "opaque_a", "accountName": "Smart Access", "accountNumber": "11070639"},
        {"id": "opaque_b", "accountName": "Smart Access", "accountNumber": "11112501"},
        {"id": "opaque_c", "accountName": "NetBank Saver", "accountNumber": "28721148"},
    ]
    matched = _filter_accounts(accounts, {"account_numbers": ["11070639", "2872-1148"]})
    assert [a["id"] for a in matched] == ["opaque_a", "opaque_c"]


def test_date_windows_chunking():
    wins = _date_windows("2024-01-01", "2024-04-15", 90)
    assert wins[0] == ("2024-01-01", "2024-03-30")
    assert wins[-1][1] == "2024-04-15"
    assert MAX_LOOKBACK_DAYS == 730


def test_title_prefers_merchant_over_generic_description():
    adapter = CommBankAdapter()
    raw = RawPayload(
        data={
            "transactions": [
                {
                    "id": "txn_rent",
                    "date": "2026-08-25",
                    "description": "general",
                    "merchantName": "Transfer To Hopefluent Realty Trust, CommBank App Rent",
                    "amount": -2450.0,
                    "currency": "AUD",
                    "category": "RENT_AND_UTILITIES",
                    "type": "TRANSFER_OUTGOING",
                    "pending": False,
                    "accountId": "acc_1",
                    "bankId": "fiskil_2",
                    "_account": {"accountName": "Smart Access"},
                },
            ]
        }
    )
    draft = adapter.parse(raw)[0]
    assert draft.entries[0].name.startswith("Transfer To Hopefluent")
    assert draft.entries[0].category_id is None
    assert "banksync_category=RENT_AND_UTILITIES" in (draft.note or "")


def test_prefers_provider_posting_datetime():
    adapter = CommBankAdapter()
    raw = RawPayload(
        data={
            "transactions": [
                {
                    "id": "txn_timed",
                    "date": "2026-10-28",
                    "authorizedDate": "2026-10-27",
                    "providerPostingDateTime": "2026-10-28T18:03:33.36Z",
                    "description": "Netflix.com Melbourne",
                    "amount": -16.99,
                    "currency": "AUD",
                    "pending": False,
                    "accountId": "acc_1",
                    "bankId": "fiskil_2",
                },
            ]
        }
    )
    draft = adapter.parse(raw)[0]
    assert draft.occurred_at.year == 2026
    assert draft.occurred_at.month == 10
    assert draft.occurred_at.day == 28
    assert draft.occurred_at.hour == 18
    assert draft.occurred_at.minute == 3
    assert draft.occurred_at.second == 33
