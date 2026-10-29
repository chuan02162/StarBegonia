from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app.sources.base import BillDraft, EntryDraft, RawPayload

DEFAULT_SUBSCRIPTION_KEY = "eae83861d1cd4de6bb9cd8a2cd6f041e"
DEFAULT_REDIRECT_URI = "https://www.coles.com.au/"
DEFAULT_CHANNEL = "coles.online.1site.desktop"
BASE_URL = "https://www.coles.com.au"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)
PAGE_SIZE = 20
PRODUCT_IMAGE_BASE = "https://cdn.productimages.coles.com.au/productimages"


class ColesError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ColesAdapter:
    """Coles in-store orders via www.coles.com.au BFF."""

    source_type = "coles"

    def validate_credential(self, cred: dict[str, Any]) -> bool:
        return bool((cred.get("refresh_token") or "").strip())

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload:
        client = _ColesClient(cred)
        client.authenticate()

        start_page = int(cursor) if cursor and str(cursor).isdigit() else 1
        max_pages = int(cred.get("max_pages") or 0)  # 0 = all pages
        summaries: list[dict[str, Any]] = []
        page = start_page
        while True:
            chunk = client.list_orders(page_number=page, page_size=PAGE_SIZE)
            orders = chunk.get("orders") or []
            summaries.extend(orders)
            total = int(chunk.get("totalNoOfOrders") or 0)
            if not orders or len(summaries) >= total:
                break
            page += 1
            if max_pages and (page - start_page + 1) > max_pages:
                break

        details: list[dict[str, Any]] = []
        for summary in summaries:
            order_id = str(summary.get("orderId") or "")
            txn = str(summary.get("transactionId") or "")
            if not order_id or not txn:
                continue
            detail = client.get_order(order_id, txn)
            detail["_summary"] = summary
            details.append(detail)

        return RawPayload(
            data={
                "orders": details,
                "refresh_token": client.refresh_token,
                "access_token": client.access_token,
            },
            cursor=str(page + 1) if summaries else None,
        )

    def parse(self, raw: RawPayload) -> list[BillDraft]:
        orders = (raw.data or {}).get("orders") or []
        drafts: list[BillDraft] = []
        for order in orders:
            draft = _parse_order(order)
            if draft:
                drafts.append(draft)
        return drafts

    def external_id(self, bill_draft: BillDraft) -> str | None:
        return bill_draft.external_id


class _ColesClient:
    def __init__(self, cred: dict[str, Any]):
        self.refresh_token = (cred.get("refresh_token") or "").strip()
        if not self.refresh_token:
            raise ColesError("refresh_token is required")
        self.subscription_key = (
            (cred.get("subscription_key") or DEFAULT_SUBSCRIPTION_KEY).strip()
            or DEFAULT_SUBSCRIPTION_KEY
        )
        self.redirect_uri = (cred.get("redirect_uri") or DEFAULT_REDIRECT_URI).strip()
        self.user_id = (cred.get("user_id") or "").strip() or None
        self.session_id = (cred.get("session_id") or "").strip() or None
        self.visitor_id = (cred.get("visitor_id") or "").strip() or None
        self.access_token: str | None = (cred.get("access_token") or "").strip() or None

        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def authenticate(self) -> None:
        status, body, _ = self._request("GET", "/api/bff/auth")
        if status != 200:
            raise ColesError(f"auth failed: HTTP {status} {body[:200]}", status)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        if data.get("authenticated") is False:
            raise ColesError("auth failed: not authenticated", status)
        if not self.access_token:
            raise ColesError("auth failed: no accessToken cookie")

    def list_orders(self, *, page_number: int, page_size: int) -> dict[str, Any]:
        qs = urlencode(
            {
                "status": "in-store",
                "pageNumber": page_number,
                "pageSize": page_size,
            }
        )
        status, body, _ = self._request("GET", f"/api/bff/orders?{qs}")
        if status == 401:
            self.authenticate()
            status, body, _ = self._request("GET", f"/api/bff/orders?{qs}")
        if status != 200:
            raise ColesError(f"list orders failed: HTTP {status} {body[:200]}", status)
        return json.loads(body)

    def get_order(self, order_id: str, transaction_id: str) -> dict[str, Any]:
        status, body, _ = self._request(
            "GET",
            f"/api/bff/orders/{order_id}",
            extra_headers={"x-transaction-id": transaction_id},
        )
        if status == 401:
            self.authenticate()
            status, body, _ = self._request(
                "GET",
                f"/api/bff/orders/{order_id}",
                extra_headers={"x-transaction-id": transaction_id},
            )
        if status != 200:
            raise ColesError(
                f"order {order_id} failed: HTTP {status} {body[:200]}", status
            )
        return json.loads(body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, str, dict[str, str]]:
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": USER_AGENT,
            "ocp-apim-subscription-key": self.subscription_key,
            "dsch-channel": DEFAULT_CHANNEL,
            "x-api-version": "2",
            "referer": "https://www.coles.com.au/account/orders?status=instore",
            "cusp-redirect-uri": self.redirect_uri,
            "cusp-correlation-id": str(uuid.uuid4()),
        }
        if self.user_id:
            headers["cusp-user-id"] = self.user_id
        if self.session_id:
            headers["cusp-session-id"] = self.session_id
        if self.visitor_id:
            headers["cusp-visitor-id"] = self.visitor_id
        if extra_headers:
            headers.update(extra_headers)

        cookie_parts = [f"refreshToken={self.refresh_token}"]
        if self.access_token:
            cookie_parts.append(f"accessToken={self.access_token}")
        headers["cookie"] = "; ".join(cookie_parts)

        req = Request(urljoin(BASE_URL, path), headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=45) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
                body = raw.decode("utf-8", errors="replace")
                self._capture_tokens(resp.headers)
                return status, body, {}
        except HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            body = raw.decode("utf-8", errors="replace")
            self._capture_tokens(exc.headers)
            return exc.code, body, {}
        except URLError as exc:
            raise ColesError(f"network error: {exc.reason}") from exc

    def _capture_tokens(self, headers: Any) -> None:
        self._capture_from_jar()
        raw_cookies: list[str] = []
        if headers is None:
            return
        if hasattr(headers, "get_all"):
            raw_cookies = headers.get_all("Set-Cookie") or []
        elif hasattr(headers, "getlist"):
            raw_cookies = headers.getlist("Set-Cookie") or []
        else:
            single = headers.get("Set-Cookie")
            if single:
                raw_cookies = [single]
        for item in raw_cookies:
            first = item.split(";", 1)[0]
            if "=" not in first:
                continue
            name, value = first.split("=", 1)
            name = name.strip()
            value = value.strip()
            if name == "accessToken" and value:
                self.access_token = value
            elif name == "refreshToken" and value:
                self.refresh_token = value

    def _capture_from_jar(self) -> None:
        for cookie in self.jar:
            if cookie.name == "accessToken" and cookie.value:
                self.access_token = cookie.value
            elif cookie.name == "refreshToken" and cookie.value:
                self.refresh_token = cookie.value


def _parse_order(order: dict[str, Any]) -> BillDraft | None:
    summary = order.get("_summary") or {}
    txn = str(order.get("transactionBarcode") or summary.get("transactionId") or "")
    order_id = str(order.get("orderId") or "")
    if not txn and not order_id:
        return None
    external_id = txn or f"order-{order_id}"

    occurred = _parse_dt(order.get("orderPlacementTime") or summary.get("orderPlacementTime"))
    store = (order.get("storeName") or summary.get("storeName") or "").strip()
    if store:
        merchant = store if store.lower().startswith("coles") else f"Coles {store}"
    else:
        merchant = "Coles"

    attrs = order.get("orderAttributes") or {}
    note_parts = []
    if order_id:
        note_parts.append(f"orderId={order_id}")
    if order.get("orderStatus"):
        note_parts.append(f"status={order.get('orderStatus')}")
    if attrs.get("flybuysNumber"):
        note_parts.append(f"flybuys={attrs.get('flybuysNumber')}")

    entries: list[EntryDraft] = []
    for item in order.get("items") or []:
        entry = _parse_item(item)
        if entry:
            entries.append(entry)

    if not entries:
        total = attrs.get("orderTotalPrice")
        if total is None:
            total = (summary.get("orderAttributes") or {}).get("orderTotalPrice")
        if total is None:
            return None
        entries.append(
            EntryDraft(name="Order total", amount=_dec(total), quantity=Decimal("1"))
        )

    return BillDraft(
        occurred_at=occurred,
        merchant=merchant,
        currency="AUD",
        external_id=external_id,
        note="; ".join(note_parts) if note_parts else None,
        entries=entries,
    )


def _parse_item(item: dict[str, Any]) -> EntryDraft | None:
    oi = item.get("orderItem") or {}
    name = (item.get("name") or item.get("description") or "").strip()
    if not name:
        return None
    qty = _dec(oi.get("quantity") if oi.get("quantity") is not None else 1)
    unit = _dec(oi.get("unitPrice")) if oi.get("unitPrice") is not None else None
    amount = _dec(oi.get("itemTotalPrice") if oi.get("itemTotalPrice") is not None else 0)
    saving = _dec(oi.get("itemSaving") if oi.get("itemSaving") is not None else 0)
    notes = []
    if item.get("brand"):
        notes.append(f"brand={item.get('brand')}")
    if item.get("id") is not None:
        notes.append(f"productId={item.get('id')}")
    return EntryDraft(
        name=name[:255],
        amount=amount,
        quantity=qty,
        unit_price=unit,
        discount=saving,
        currency="AUD",
        note="; ".join(notes) if notes else None,
        image_url=_product_image_url(item),
    )


def _product_image_url(item: dict[str, Any]) -> str | None:
    uris = item.get("imageUris") or item.get("images") or []
    if isinstance(uris, dict):
        uris = [uris]
    if not isinstance(uris, list) or not uris:
        return None
    first = uris[0]
    if isinstance(first, str):
        raw = first
    elif isinstance(first, dict):
        raw = first.get("uri") or first.get("url") or first.get("href") or ""
    else:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return f"{PRODUCT_IMAGE_BASE}{raw}"


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.utcnow()
    else:
        dt = datetime.utcnow()
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
