from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from app.sources.base import BillDraft, EntryDraft, RawPayload

GRAPHQL_URL = "https://apigee-prod.api-wr.com/wx/v1/bff/graphql"
ACTIVITY_FIRST_PAGE_QUERY = """
query RewardsActivityHomeFirstPage($featureFlags: ActivityHomeFeatureFlags) {
  activityHome(featureFlags: $featureFlags) {
    __typename
    ... on ActivityHomePage {
      results {
        sections {
          sectionItems {
            __typename
            ... on RewardsActivityItem {
              id
              activityDetailsId
              description
              displayDate
              receipt {
                analytics { partnerName }
                receiptId
                receiptSource
              }
              transactionType
              transaction { amountAsDollars origin }
            }
          }
        }
        nextPageToken
      }
    }
  }
}
"""
ACTIVITY_NEXT_PAGE_QUERY = """
query RewardsActivityHomeNextPage($pageToken: String!, $featureFlags: ActivityHomeFeatureFlags) {
  activityHomeNextPage(pageToken: $pageToken, featureFlags: $featureFlags) {
    sections {
      sectionItems {
        __typename
        ... on RewardsActivityItem {
          id
          activityDetailsId
          description
          displayDate
          receipt {
            analytics { partnerName }
            receiptId
            receiptSource
          }
          transactionType
          transaction { amountAsDollars origin }
        }
      }
    }
    nextPageToken
  }
}
"""
RECEIPT_DETAILS_URL = "https://apigee-prod.api-wr.com/wx/v1/bff/ereceipts/details"
MAX_ACTIVITY_PAGES = 100
MAX_RECEIPT_DETAILS = 2000
DEFAULT_CLIENT_ID = '8h41mMOiDULmlLT28xKSv5ITpp3XBRvH'


class WwsError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class WwsAdapter:
    """Woolworths in-store purchases from Everyday Rewards eReceipts."""

    source_type = "wws"

    def validate_credential(self, cred: dict[str, Any]) -> bool:
        authorization = str(cred.get("rewards_authorization") or "").strip()
        return (
            authorization.lower().startswith("bearer ")
            and isinstance(cred.get("user_agent"), str)
            and bool(cred.get("user_agent"))
        )

    def check(self, cred: dict[str, Any]) -> dict[str, Any]:
        client = _RewardsClient(cred)
        client_id = (
            str(current_app.config.get("WWS_REWARDS_CLIENT_ID") or DEFAULT_CLIENT_ID)
            .strip()
        )
        if not client_id:
            raise WwsError("Everyday Rewards API is not configured", 503)
        if not client.authorization:
            raise WwsError("Everyday Rewards session was not captured", 400)
        client.graphql(
            ACTIVITY_FIRST_PAGE_QUERY,
            {"featureFlags": {"isGiftingStoreEnabled": False}},
            client_id=client_id,
        )
        return cred

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload:
        client = _RewardsClient(cred)
        client_id = (
            str(current_app.config.get("WWS_REWARDS_CLIENT_ID") or DEFAULT_CLIENT_ID)
            .strip()
        )
        if not client_id:
            raise WwsError("Everyday Rewards API is not configured", 503)
        if not client.authorization:
            raise WwsError(
                "Everyday Rewards session was not captured; re-link Everyday Rewards",
                400,
            )

        activity_items: list[dict[str, Any]] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        on_progress = cred.get("_on_progress")
        for page in range(MAX_ACTIVITY_PAGES):
            if page == 0:
                data = client.graphql(
                    ACTIVITY_FIRST_PAGE_QUERY,
                    {"featureFlags": {"isGiftingStoreEnabled": False}},
                    client_id=client_id,
                )
                home = (data.get("activityHome") or {}).get("results") or {}
            else:
                assert token is not None
                data = client.graphql(
                    ACTIVITY_NEXT_PAGE_QUERY,
                    {
                        "pageToken": token,
                        "featureFlags": {"isGiftingStoreEnabled": False},
                    },
                    client_id=client_id,
                )
                home = data.get("activityHomeNextPage") or {}

            for section in home.get("sections") or []:
                activity_items.extend(
                    item
                    for item in section.get("sectionItems") or []
                    if item.get("__typename") == "RewardsActivityItem"
                )
            next_token = home.get("nextPageToken")
            if not next_token or next_token in seen_tokens:
                break
            seen_tokens.add(next_token)
            token = next_token
        else:
            raise WwsError("Everyday Rewards activity pagination exceeded its safety limit", 502)

        receipts = [
            item
            for item in activity_items
            if item.get("transactionType") == "purchase"
            and (item.get("receipt") or {}).get("receiptId")
            and (item.get("receipt") or {}).get("analytics", {}).get("partnerName")
            == "Woolworths"
            and _is_in_store_receipt(item)
        ]
        if len(receipts) > MAX_RECEIPT_DETAILS:
            raise WwsError("Everyday Rewards returned an unexpected number of receipts", 502)

        try:
            configured_concurrency = int(
                current_app.config.get("SOURCE_SYNC_CONCURRENCY", 4)
            )
        except (RuntimeError, TypeError, ValueError):
            configured_concurrency = 4
        concurrency = min(max(configured_concurrency, 1), 4)

        async def fetch_details() -> list[dict[str, Any]]:
            semaphore = asyncio.Semaphore(concurrency)

            async def fetch_one(index: int, item: dict[str, Any]):
                async with semaphore:
                    receipt_key = str((item.get("receipt") or {}).get("receiptId"))
                    detail = await asyncio.to_thread(
                        client.get_receipt_details,
                        receipt_key,
                        client_id,
                    )
                return index, {"receiptDetails": detail, "_activity": item}

            tasks = [
                asyncio.create_task(fetch_one(index, item))
                for index, item in enumerate(receipts)
            ]
            ordered: dict[int, dict[str, Any]] = {}
            for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
                index, detail = await task
                ordered[index] = detail
                if callable(on_progress):
                    try:
                        on_progress(
                            current=completed,
                            total=max(len(receipts), 1),
                            message=f"拉取 Woolworths 收据详情 {completed}/{len(receipts)}…",
                        )
                    except Exception:
                        pass
            return [ordered[index] for index in range(len(receipts))]

        details = asyncio.run(fetch_details())
        image_candidates: list[dict[str, Any]] = []
        image_enrichment_available = False
        image_enrichment_error: str | None = None
        image_stats = {
            "images_matched": 0,
            "image_time_matched_receipts": 0,
            "image_name_matches": 0,
        }
        # Past shops image enrichment has been removed; eReceipts are the
        # authoritative source and no longer depend on the Woolworths session.
        return RawPayload(
            data={
                "activity_items": activity_items,
                "receipts": details,
                "image_candidates": image_candidates,
                "image_candidates_count": len(image_candidates),
                "image_enrichment_available": image_enrichment_available,
                "image_enrichment_error": image_enrichment_error,
                **image_stats,
                "listed": len(activity_items),
                "detailed": len(details),
            },
            cursor=None,
        )

    def parse(self, raw: RawPayload) -> list[BillDraft]:
        drafts: list[BillDraft] = []
        for receipt in (raw.data or {}).get("receipts") or []:
            draft = _parse_receipt(receipt)
            if draft:
                drafts.append(draft)
        return drafts

    def external_id(self, bill_draft: BillDraft) -> str | None:
        return bill_draft.external_id


class _RewardsClient:
    def __init__(self, cred: dict[str, Any]):
        self.user_agent = cred["user_agent"][:512]
        authorization = str(cred.get("rewards_authorization") or "").strip()
        self.authorization = authorization if authorization.lower().startswith("bearer ") else ""

    def _request(
        self, url: str, payload: dict[str, Any], *, client_id: str
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.everyday.com.au",
                "Referer": "https://www.everyday.com.au/",
                "User-Agent": self.user_agent,
                "api-version": "2",
                "client_id": client_id,
                **({"Authorization": self.authorization} if self.authorization else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            if status in (401, 403):
                raise WwsError(
                    "Everyday Rewards rejected the request; re-link Everyday Rewards",
                    status,
                ) from exc
            raise WwsError(f"Everyday Rewards request failed (HTTP {status})", status) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise WwsError("Could not reach Everyday Rewards service", 502) from exc

        if not isinstance(response_body, dict):
            raise WwsError("Everyday Rewards returned an invalid response", 502)
        if response_body.get("errors"):
            raise WwsError("Everyday Rewards could not return receipt data", 502)
        data = response_body.get("data")
        if not isinstance(data, dict):
            raise WwsError("Everyday Rewards response did not include data", 502)
        return data

    def graphql(
        self, query: str, variables: dict[str, Any], *, client_id: str
    ) -> dict[str, Any]:
        return self._request(
            GRAPHQL_URL,
            {"query": query, "variables": variables},
            client_id=client_id,
        )

    def get_receipt_details(self, receipt_key: str, client_id: str) -> dict[str, Any]:
        data = self._request(
            RECEIPT_DETAILS_URL,
            {"receiptKey": receipt_key},
            client_id=client_id,
        )
        return data.get("receiptDetails") or {}


def _is_in_store_receipt(item: dict[str, Any]) -> bool:
    """Everyday's details endpoint errors for ONLINE receipts; skip them."""
    source = (item.get("receipt") or {}).get("receiptSource")
    return source is None or str(source).strip().upper() == "INSTORE"


def _parse_receipt(receipt: dict[str, Any]) -> BillDraft | None:
    activity = receipt.get("_activity") or {}
    receipt_id = ((activity.get("receipt") or {}).get("receiptId"))
    details_page = receipt.get("receiptDetails") or {}
    if not receipt_id or not details_page:
        return None

    details = details_page.get("details") or []
    header = next(
        (item for item in details if item.get("__typename") == "ReceiptDetailsHeader"),
        {},
    )
    total_row = next(
        (item for item in details if item.get("__typename") == "ReceiptDetailsTotal"),
        {},
    )
    total = _parse_money(total_row.get("total"))
    footer = next(
        (item for item in details if item.get("__typename") == "ReceiptDetailsFooter"),
        {},
    )
    occurred_at = _parse_receipt_date(
        activity.get("displayDate"), footer.get("transactionDetails")
    )
    if total is None or occurred_at is None:
        return None

    item_block = next(
        (item for item in details if item.get("__typename") == "ReceiptDetailsItems"),
        {},
    )
    entries: list[EntryDraft] = []
    for item in item_block.get("items") or []:
        name = re.sub(r"\s+", " ", str(item.get("description") or "")).strip()
        magnitude = _parse_money(item.get("amount"))
        if not name or magnitude is None or magnitude == 0:
            continue
        prefix = str(item.get("prefixChar") or "").strip()
        # Receipt sign: normal lines positive (money out), "-" lines are
        # discounts / refunds (negative), exactly as printed on the receipt.
        amount = -abs(magnitude) if prefix in {"-", "−", "–"} else abs(magnitude)
        entries.append(
            EntryDraft(
                name=name[:255],
                amount=amount,
                quantity=Decimal("1"),
                currency="AUD",
                tags=["Woolworths"],
            )
        )

    if not entries:
        entries.append(
            EntryDraft(
                name="Woolworths purchase",
                amount=abs(total),
                currency="AUD",
                tags=["Woolworths"],
                note="eReceipt line amounts were unavailable.",
            )
        )

    store_no = str(header.get("storeNo") or "").strip()
    external_id = _receipt_external_id(
        occurred_at=occurred_at,
        store_no=store_no,
        total=total,
        entries=entries,
    )
    return BillDraft(
        occurred_at=occurred_at,
        merchant="Woolworths",
        currency="AUD",
        external_id=external_id,
        net_amount=-abs(total),
        note=f"Everyday Rewards eReceipt{f' · store {store_no}' if store_no else ''}",
        entries=entries,
    )


def _receipt_external_id(
    *,
    occurred_at: datetime,
    store_no: str,
    total: Decimal,
    entries: list[EntryDraft],
) -> str:
    """Stable fingerprint of an eReceipt.

    Everyday's activity feed does not expose a stable per-receipt id (the `id`
    is plain on the first page and encrypted on later pages, and the
    `activityDetailsId` bundle drops `activityId` after the first page), so a
    deterministic content hash is used instead.
    """
    parts = [
        occurred_at.strftime("%Y-%m-%d %H:%M"),
        store_no,
        format(total.quantize(Decimal("0.01")), "f"),
    ]
    for entry in entries:
        parts.append(entry.name)
        parts.append(format(entry.amount.quantize(Decimal("0.01")), "f"))
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"wws-{digest[:24]}"


def _parse_money(value: Any) -> Decimal | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-−]?\s*\$?\s*(\d+(?:\.\d{1,2})?)", text)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if match.group(0).lstrip().startswith(("-", "−")):
        amount = -amount
    return amount


def _parse_receipt_date(value: Any, transaction_details: Any = None) -> datetime | None:
    if isinstance(transaction_details, str):
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", transaction_details)
        time_match = re.search(r"\b(\d{2}:\d{2})\b", transaction_details)
        if date_match:
            text = date_match.group(1)
            if time_match:
                text = f"{text} {time_match.group(1)}"
            for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b-%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # Everyday Rewards list labels omit the year; the receipt footer above is
    # preferred and supplies an exact transaction date for normal responses.
    return None

