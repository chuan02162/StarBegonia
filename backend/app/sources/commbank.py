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
        accounts = _filter_accounts(accounts, cred)
        if not accounts:
            raise CommBankError(
                "No matching CommBank accounts. Check account_numbers "
                "(e.g. 11070639) in your credential.",
                400,
            )

        lookback_days = int(cred.get("lookback_days") or 90)
        to_date = (cred.get("to") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
        # BankSync REST only accepts from/to (YYYY-MM-DD). Prefer explicit `from`,
        # else incremental `since` watermark, else lookback_days (first sync).
        since = _parse_sync_since(cred.get("since"))
        if cred.get("from"):
            from_date = str(cred.get("from")).strip()
            incremental = False
        elif since:
            from_date = since.astimezone(timezone.utc).strftime("%Y-%m-%d")
            incremental = bool(cred.get("incremental"))
        else:
            from_date = (
                datetime.now(timezone.utc) - timedelta(days=lookback_days)
            ).strftime("%Y-%m-%d")
            incremental = False
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
                "incremental": incremental,
                "since": since.isoformat() if since else None,
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


def _resolve_api_key(cred: dict[str, Any] | None = None) -> str:
    cred = cred or {}
    key = (cred.get("api_key") or "").strip()
    if key:
        return key
    try:
        return (current_app.config.get("BANKSYNC_API_KEY") or "").strip()
    except RuntimeError:
        return ""


def _norm_account_number(value: Any) -> str:
    """Digits only — users type 11070639, BankSync may return the same."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _filter_accounts(
    accounts: list[dict[str, Any]], cred: dict[str, Any]
) -> list[dict[str, Any]]:
    """Prefer account_numbers (user-friendly); fall back to opaque account_ids."""
    wanted_numbers = {
        _norm_account_number(n)
        for n in _as_str_list(cred.get("account_numbers") or cred.get("account_number"))
        if _norm_account_number(n)
    }
    wanted_ids = set(_as_str_list(cred.get("account_ids")))
    wanted_names = {
        n.lower() for n in _as_str_list(cred.get("account_names")) if n
    }

    if not wanted_numbers and not wanted_ids and not wanted_names:
        # No filter → all accounts (fine for a solo workspace; multi-user
        # should set account_numbers so each person only syncs theirs).
        return accounts

    matched: list[dict[str, Any]] = []
    for a in accounts:
        aid = a.get("id")
        num = _norm_account_number(a.get("accountNumber"))
        name = (a.get("accountName") or "").lower()
        if wanted_ids and aid in wanted_ids:
            matched.append(a)
            continue
        if wanted_numbers and num in wanted_numbers:
            matched.append(a)
            continue
        if wanted_names and name in wanted_names:
            matched.append(a)
            continue
    return matched


def list_commbank_accounts_for_ui() -> dict[str, Any]:
    """List banks/accounts for credential picker (server uses env API key)."""
    api_key = _resolve_api_key({})
    if not api_key:
        raise CommBankError("BANKSYNC_API_KEY is not configured", 503)
    client = _BankSyncClient(api_key)
    bank = client.resolve_commbank(None)
    if not bank:
        raise CommBankError(
            "No CommBank connection in BankSync. Connect it in the BankSync app first.",
            400,
        )
    accounts = client.list_accounts(bank["id"])
    return {
        "bank": {
            "id": bank.get("id"),
            "name": bank.get("name"),
        },
        "accounts": [
            {
                "id": a.get("id"),
                "account_name": a.get("accountName"),
                "account_number": a.get("accountNumber"),
                "account_type": a.get("accountType"),
                "currency": a.get("currency"),
                "balance": a.get("balance"),
            }
            for a in accounts
        ],
    }


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

    # BankSync exposes CDR postingDateTime as providerPostingDateTime (RFC3339).
    # `date` / `authorizedDate` are date-only fallbacks.
    occurred = _parse_date(
        str(
            txn.get("providerPostingDateTime")
            or txn.get("date")
            or txn.get("authorizedDate")
            or ""
        ).strip()
    )
    if not occurred:
        return None

    from app.services.titles import best_title

    # BankSync often puts a useless description like "general" while the
    # human title lives in merchantName (e.g. "Transfer To Hopefluent…").
    title = best_title(
        txn.get("description"),
        txn.get("merchantName"),
        txn.get("originalDescription"),
    )
    merchant = (txn.get("merchantName") or title)[:255]
    currency = (txn.get("currency") or "AUD").upper()
    account = txn.get("_account") or {}
    account_name = account.get("accountName") or txn.get("accountName") or ""

    note_parts = []
    if account_name:
        note_parts.append(f"account={account_name}")
    if txn.get("category"):
        note_parts.append(f"banksync_category={txn.get('category')}")
    if txn.get("type"):
        note_parts.append(f"type={txn.get('type')}")
    if txn.get("reference"):
        note_parts.append(f"ref={txn.get('reference')}")

    # Category left empty — Jev (or manual) classifies; BankSync labels
    # stay in note as banksync_category=… for debugging only.
    entry = EntryDraft(
        name=title[:255],
        amount=abs_amount,
        quantity=Decimal("1"),
        unit_price=abs_amount,
        currency=currency,
        category_id=None,
        note=None,
    )

    return BillDraft(
        occurred_at=occurred,
        merchant=merchant[:255],
        currency=currency,
        external_id=f"banksync:{txn_id}",
        note="; ".join(note_parts) if note_parts else None,
        entries=[entry],
    )


def _parse_sync_since(value: Any) -> datetime | None:
    """Parse incremental watermark; keep tz-aware UTC for from-date flooring."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            if "T" in text:
                text = _normalize_iso_fractional(text)
                dt = datetime.fromisoformat(text)
            else:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_date(value: str) -> datetime | None:
    """Parse BankSync date or providerPostingDateTime.

    Prefer RFC3339 timestamps (e.g. providerPostingDateTime). Date-only
    YYYY-MM-DD falls back to midnight UTC; the UI shows date-only for those.
    """
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        if "T" in text:
            text = _normalize_iso_fractional(text)
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=None)
    except ValueError:
        return None


def _normalize_iso_fractional(text: str) -> str:
    """Pad fractional seconds to 3/6 digits — Python 3.9 rejects '.36'."""
    if "." not in text:
        return text
    head, rest = text.split(".", 1)
    digits = []
    i = 0
    while i < len(rest) and rest[i].isdigit():
        digits.append(rest[i])
        i += 1
    if not digits:
        return text
    frac = "".join(digits)
    if len(frac) <= 3:
        frac = frac.ljust(3, "0")
    elif len(frac) < 6:
        frac = frac.ljust(6, "0")
    else:
        frac = frac[:6]
    return f"{head}.{frac}{rest[i:]}"


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
