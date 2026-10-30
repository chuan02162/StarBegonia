from __future__ import annotations

from app.sources.base import SourceAdapter
from app.sources.coles import ColesAdapter
from app.sources.manual import ManualAdapter
from app.sources.openfeed import OpenFeedAdapter

_ADAPTERS: dict[str, SourceAdapter] = {
    ManualAdapter.source_type: ManualAdapter(),
    ColesAdapter.source_type: ColesAdapter(),
    OpenFeedAdapter.source_type: OpenFeedAdapter(),
}

def get_adapter(source_type: str) -> SourceAdapter:
    try:
        return _ADAPTERS[source_type]
    except KeyError as exc:
        raise KeyError(f"unknown source_type: {source_type}") from exc


def list_sources() -> list[dict]:
    return [
        {
            "source_type": key,
            "supports_sync": key != "manual",
            "implemented": True,
        }
        for key in _ADAPTERS
    ]


def register_adapter(adapter: SourceAdapter) -> None:
    _ADAPTERS[adapter.source_type] = adapter
