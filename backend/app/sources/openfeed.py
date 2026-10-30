"""Banking transactions via OpenFeed Sharing API (replaces BankSync)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import current_app

from app.sources.base import BillDraft, EntryDraft, RawPayload
from app.services.openfeed_auth import (
    OpenFeedAuthError,
    api_get,
    refresh_access_token,
)

MAX_LOOKBACK_DAYS = 730
CHUNK_DAYS = 90


class OpenFeedError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OpenFeedAdapter:
    source_type = "commbank"

    def validate_credential(self, cred: dict[str, Any]) -> bool:
        return bool((cred.get("refresh_token") or "").strip())

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload:
        refresh = (cred.get("refresh_token") or "").strip()
        if not refresh:
            raise OpenFeedError("OpenFeed refresh_token missing — reconnect the bank source", 400)

        try:
            token = refresh_access_token(refresh)
        except OpenFeedAuthError as exc:
            raise OpenFeedError(exc.message, exc.status_code) from exc

        access = token["access_token"]
        # Persist rotated refresh if present (caller may ignore)
        new_refresh = token.get("refresh_token") or refresh

        lookback_days = int(cred.get("lookback_days") or 90)
        if lookback_days > MAX_LOOKBACK_DAYS:
            raise OpenFeedError(
                f"lookback_days max is {MAX_LOOKBACK_DAYS} (~2 years CDR). Got {lookback_days}.",
                400,
            )
        to_date = (cred.get("to") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
        since = _parse_sync_since(cred.get("since"))
        if cred.get("from"):
            from_date = str(cred.get("from")).strip()[:10]
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
        wanted_accounts = {
            str(a).strip()
            for a in (cred.get("account_ids") or [])
            if str(a).strip()
        }

        try:
            accounts = _list_all(access, "/banking/accounts")
        except OpenFeedAuthError as exc:
            raise OpenFeedError(exc.message, exc.status_code) from exc

        if wanted_accounts:
            accounts = [a for a in accounts if str(a.get("accountId")) in wanted_accounts]

        windows = _date_windows(from_date, to_date, CHUNK_DAYS)
        on_progress = cred.get("_on_progress")
        usable_accounts = [
            a for a in accounts if str(a.get("accountId") or "").strip()
        ]
        fetch_total = max(len(usable_accounts) * max(len(windows), 1), 1)
        try:
            configured_concurrency = int(
                current_app.config.get("SOURCE_SYNC_CONCURRENCY", 4)
            )
        except RuntimeError:
            configured_concurrency = 4
        concurrency = min(max(configured_concurrency, 1), 4)

        async def fetch_window(
            semaphore: asyncio.Semaphore,
            index: int,
            account: dict[str, Any],
            oldest: str,
            newest: str,
        ):
            aid = str(account.get("accountId") or "")
            rows_for_window: list[dict[str, Any]] = []
            offset = 0
            while True:
                async with semaphore:
                    page = await asyncio.to_thread(
                        api_get,
                        f"/banking/accounts/{aid}/transactions",
                        access_token=access,
                        params={
                            "oldestDate": oldest,
                            "newestDate": newest,
                            "limit": "1000",
                            "offset": str(offset),
                        },
                    )
                rows = page.get("data") or []
                if isinstance(rows, dict):
                    rows = [rows]
                rows_for_window.extend(rows)
                links = page.get("links") or {}
                if not links.get("next") or not rows:
                    break
                offset += len(rows) or 1000
            return index, account, rows_for_window

        async def fetch_all_windows():
            semaphore = asyncio.Semaphore(concurrency)
            jobs = [
                (account, oldest, newest)
                for account in usable_accounts
                for oldest, newest in windows
            ]
            tasks = [
                asyncio.create_task(
                    fetch_window(semaphore, index, account, oldest, newest)
                )
                for index, (account, oldest, newest) in enumerate(jobs)
            ]
            completed = 0
            row_count = 0
            results: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
            for task in asyncio.as_completed(tasks):
                index, account, rows = await task
                completed += 1
                row_count += len(rows)
                results[index] = (account, rows)
                if callable(on_progress):
                    try:
                        on_progress(
                            current=completed,
                            total=fetch_total,
                            message=(
                                f"拉取 OpenFeed {completed}/{fetch_total} "
                                f"（已得 {row_count} 笔）…"
                            ),
                        )
                    except Exception:
                        pass
            return [results[index] for index in range(len(jobs))]

        try:
            window_results = asyncio.run(fetch_all_windows())
        except OpenFeedAuthError as exc:
            raise OpenFeedError(exc.message, exc.status_code) from exc
        all_txns: list[dict[str, Any]] = []
        seen: set[str] = set()
        for account, rows in window_results:
            for row in rows:
                tid = str(row.get("transactionId") or "")
                if tid and tid in seen:
                    continue
                if tid:
                    seen.add(tid)
                row["_account"] = account
                all_txns.append(row)

        if skip_pending:
            all_txns = [
                t
                for t in all_txns
                if str(t.get("status") or "").upper() != "PENDING"
            ]

        return RawPayload(
            data={
                "accounts": accounts,
                "transactions": all_txns,
                "from": from_date,
                "to": to_date,
                "windows": len(windows),
                "incremental": incremental,
                "since": since.isoformat() if since else None,
                "refresh_token": new_refresh,
                "access_token": access,
            },
            cursor=None,
        )

    def parse(self, raw: RawPayload) -> list[BillDraft]:
        drafts: list[BillDraft] = []
        for txn in (raw.data or {}).get("transactions") or []:
            draft = _txn_to_draft(txn)
            if draft:
                drafts.append(draft)
        return drafts

    def external_id(self, bill_draft: BillDraft) -> str | None:
        return bill_draft.external_id


def _list_all(access: str, path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = api_get(
            path,
            access_token=access,
            params={"limit": "1000", "offset": str(offset)},
        )
        rows = page.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        out.extend(rows)
        links = page.get("links") or {}
        if not links.get("next"):
            break
        offset += len(rows) or 1000
        if not rows:
            break
    return out


def _date_windows(from_date: str, to_date: str, chunk_days: int) -> list[tuple[str, str]]:
    start = datetime.strptime(from_date[:10], "%Y-%m-%d").date()
    end = datetime.strptime(to_date[:10], "%Y-%m-%d").date()
    if start > end:
        start, end = end, start
    windows: list[tuple[str, str]] = []
    cur = start
    step = max(int(chunk_days), 1)
    while cur <= end:
        chunk_end = min(cur + timedelta(days=step - 1), end)
        windows.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return windows


def _parse_sync_since(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            if "T" in text:
                dt = datetime.fromisoformat(text)
            else:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _pick_datetime(txn: dict[str, Any]) -> datetime | None:
    for key in (
        "postedDateTime",
        "executionDateTime",
        "valueDate",
        "transactionDate",
        "date",
    ):
        raw = txn.get(key)
        if not raw:
            continue
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            if "T" in text:
                dt = datetime.fromisoformat(text)
            else:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None


def _txn_to_draft(txn: dict[str, Any]) -> BillDraft | None:
    txn_id = str(txn.get("transactionId") or "").strip()
    if not txn_id:
        return None
    try:
        signed = Decimal(str(txn.get("amount")))
    except (InvalidOperation, TypeError):
        return None
    if signed == 0:
        return None

    occurred = _pick_datetime(txn)
    if not occurred:
        return None

    from app.services.titles import best_title

    title = best_title(
        txn.get("description"),
        txn.get("merchantName"),
        txn.get("reference"),
    )
    merchant = (txn.get("merchantName") or title)[:255]
    currency = (txn.get("currency") or "AUD").upper()
    account = txn.get("_account") or {}
    account_name = account.get("displayName") or account.get("nickname") or ""
    provider = account.get("providerName") or ""

    note_parts = []
    if provider:
        note_parts.append(f"provider={provider}")
    if account_name:
        note_parts.append(f"account={account_name}")
    if txn.get("status"):
        note_parts.append(f"status={txn.get('status')}")
    if txn.get("reference"):
        note_parts.append(f"ref={txn.get('reference')}")
    if account.get("accountId"):
        note_parts.append(f"account_id={account.get('accountId')}")

    # Keep bank sign: positive = money in, negative = money out.
    # Category (Jev) is separate from income/expense polarity.
    entry = EntryDraft(
        name=title[:255],
        amount=signed,
        quantity=Decimal("1"),
        unit_price=signed,
        currency=currency,
        category_id=None,
        note=None,
    )
    return BillDraft(
        occurred_at=occurred,
        merchant=merchant[:255],
        currency=currency,
        external_id=f"openfeed:{txn_id}",
        note="; ".join(note_parts) if note_parts else None,
        entries=[entry],
    )
