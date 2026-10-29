from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass
class EntryDraft:
    name: str
    amount: Decimal
    quantity: Decimal = Decimal("1")
    unit_price: Decimal | None = None
    discount: Decimal = Decimal("0")
    currency: str = "AUD"
    category_id: str | None = None
    tags: list[str] = field(default_factory=list)
    note: str | None = None
    image_url: str | None = None


@dataclass
class BillDraft:
    occurred_at: datetime
    merchant: str | None = None
    currency: str = "AUD"
    external_id: str | None = None
    note: str | None = None
    entries: list[EntryDraft] = field(default_factory=list)


@dataclass
class RawPayload:
    data: Any
    cursor: str | None = None


class SourceAdapter(Protocol):
    source_type: str

    def validate_credential(self, cred: dict[str, Any]) -> bool: ...

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload: ...

    def parse(self, raw: RawPayload) -> list[BillDraft]: ...

    def external_id(self, bill_draft: BillDraft) -> str | None: ...
