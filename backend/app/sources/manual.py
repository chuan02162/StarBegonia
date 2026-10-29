from __future__ import annotations

from typing import Any

from app.sources.base import BillDraft, RawPayload


class ManualAdapter:
    """Manual bills are created via API; adapter exists for registry uniformity."""

    source_type = "manual"

    def validate_credential(self, cred: dict[str, Any]) -> bool:
        return True

    def fetch_raw(self, cred: dict[str, Any], cursor: str | None = None) -> RawPayload:
        raise NotImplementedError("manual source does not support fetch")

    def parse(self, raw: RawPayload) -> list[BillDraft]:
        raise NotImplementedError("manual source does not support parse")

    def external_id(self, bill_draft: BillDraft) -> str | None:
        return bill_draft.external_id
