from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app

from app.sources.base import BillDraft, EntryDraft, RawPayload

BASE_URL = "https://api.banksync.io"
# Marketing docs use bnk_cba; we still auto-detect by bank name if unset.
DEFAULT_BANK_HINTS = ("commbank", "commonwealth", "cba")


class CommBankError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CommBankAdapter:
    """CommBank transactions via BankSync (CDR) REST API."""

    source_type = "commbank"

    def validate_credential(self, cred: dict[str, Any]) -> bool:
        return bool(_resolve_api_key(cred))

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload:
        api_key = _resolve_api_key(cred)
        if not api_key:
            raise CommBankError(
                "BankSync API key missing — set BANKSYNC_API_KEY or credential api_key",
                400,
            )

        client = _BankSyncClient(api_key)
        bank = client.resolve_commbank(cred.get("bank_id"))
        if not bank:
            raise CommBankError(
                "No CommBank connection found in BankSync workspace. "
                "Connect CommBank in the BankSync app first.",
                400,
            )

        accounts = client.list_accounts(bank["id"])
        wanted = cred.get("account_ids") or []
        if isinstance(wanted, str):
            wanted = [w.strip() for w in wanted.split(",") if w.strip()]
        if wanted:
            accounts = [a for a in accounts if a.get("id") in wanted]
        if not accounts:
            raise CommBankError("No matching CommBank accounts to sync", 400)

        lookback_days = int(cred.get("lookback_days") or 90)
        to_date = (cred.get("to") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
        from_date = (
            cred.get("from")
            or (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
                "%Y-%m-%d"
            )
        ).strip()
        skip_pending = bool(cred.get("skip_pending", True))

        all_txns: list[dict[str, Any]] = []
        for account in accounts:
            aid = account["id"]
            page_cursor: str | None = None
            while True:
                payload = client.list_transactions(
                    bank["id"],
                    aid,
                    from_date=from_date,
                    to_date=to_date,
                    cursor=page_cursor,
                )
                rows = payload.get("data") or []
                for row in rows:
                    row["_account"] = account
                    row["_bank"] = bank
                all_txns.extend(rows)
                meta = payload.get("meta") or {}
                if not meta.get("hasMore"):
                    break
                page_cursor = meta.get("cursor")
                if not page_cursor:
                    break

        if skip_pending:
            all_txns = [t for t in all_txns if not t.get("pending")]

        return RawPayload(
            data={
                "bank": bank,
                "accounts": accounts,
                "transactions": all_txns,
                "from": from_date,
                "to": to_date,
            },
            cursor=None,
        )

    def parse(self, raw: RawPayload) -> list[BillDraft]:
        data = raw.data or {}
        drafts: list[BillDraft] = []
        for txn in data.get("transactions") or []:
            draft = _txn_to_draft(txn)
            if draft:
                drafts.append(draft)
        return drafts

    def external_id(self, bill_draft: BillDraft) -> str | None:
        return bill_draft.external_id


def _resolve_api_key(cred: dict[str, Any]) -> str:
    key = (cred.get("api_key") or "").strip()
    if key:
        return key
    try:
        return (current_app.config.get("BANKSYNC_API_KEY") or "").strip()
    except RuntimeError:
        return ""


def _txn_to_draft(txn: dict[str, Any]) -> BillDraft | None:
    txn_id = str(txn.get("id") or "").strip()
    if not txn_id:
        return None

    amount_raw = txn.get("amount")
    try:
        signed = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError):
        return None
    if signed == 0:
        return None

    abs_amount = abs(signed)
    is_income = signed > 0

    date_str = str(txn.get("date") or txn.get("authorizedDate") or "").strip()
    occurred = _parse_date(date_str)
    if not occurred:
        return None

    description = (
        (txn.get("merchantName") or txn.get("description") or txn.get("originalDescription") or "")
        .strip()
        or "Bank transaction"
    )
    merchant = (txn.get("merchantName") or description)[:255]
    currency = (txn.get("currency") or "AUD").upper()
    account = txn.get("_account") or {}
    account_name = account.get("accountName") or txn.get("accountName") or ""

    note_parts = []
    if account_name:
        note_parts.append(f"account={account_name}")
    if txn.get("category"):
        note_parts.append(f"banksync_category={txn.get('category')}")
    if txn.get("reference"):
        note_parts.append(f"ref={txn.get('reference')}")

    entry = EntryDraft(
        name="general",
        amount=abs_amount,
        quantity=Decimal("1"),
        unit_price=abs_amount,
        currency=currency,
        category_id="income" if is_income else None,
        note=(txn.get("description") or description)[:500],
    )

    return BillDraft(
        occurred_at=occurred,
        merchant=merchant,
        currency=currency,
        external_id=f"banksync:{txn_id}",
        note="; ".join(note_parts) if note_parts else None,
        entries=[entry],
    )


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        if "T" in text:
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=None)
    except ValueError:
        return None


class _BankSyncClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def resolve_commbank(self, bank_id: str | None) -> dict[str, Any] | None:
        banks = self.list_banks()
        if bank_id:
            for b in banks:
                if b.get("id") == bank_id:
                    return b
            return None
        for b in banks:
            name = (b.get("name") or "").lower()
            bid = (b.get("id") or "").lower()
            if any(h in name or h in bid for h in DEFAULT_BANK_HINTS):
                return b
        # Fallback: single bank workspace
        if len(banks) == 1:
            return banks[0]
        return None

    def list_banks(self) -> list[dict[str, Any]]:
        payload = self._get("/v1/banks")
        return list(payload.get("data") or [])

    def list_accounts(self, bank_id: str) -> list[dict[str, Any]]:
        payload = self._get(f"/v1/banks/{bank_id}/accounts")
        return list(payload.get("data") or [])

    def list_transactions(
        self,
        bank_id: str,
        account_id: str,
        *,
        from_date: str,
        to_date: str,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"from": from_date, "to": to_date}
        if cursor:
            params["cursor"] = cursor
        return self._get(
            f"/v1/banks/{bank_id}/accounts/{account_id}/transactions",
            params=params,
        )

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        req = Request(
            url,
            method="GET",
            headers={
                "X-API-Key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise CommBankError(f"BankSync HTTP {exc.code}: {detail}", exc.code) from exc
        except URLError as exc:
            raise CommBankError(f"BankSync unreachable: {exc.reason}", 502) from exc
        if not isinstance(body, dict) or body.get("success") is False:
            err = (body or {}).get("error") if isinstance(body, dict) else body
            raise CommBankError(f"BankSync error: {err}", 502)
        return body
