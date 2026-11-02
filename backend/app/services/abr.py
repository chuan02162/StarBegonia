"""ABN Lookup (abr.business.gov.au) merchant-name enrichment.

Given a legal merchant name from a bank feed (e.g. ``Bcs Enterprise Pty Ltd
Epping Aus``) this resolves the registered business/trading names via the free
ABN Lookup JSON web service and caches the result locally so each distinct
merchant is looked up once.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.extensions import db
from app.models import MerchantEnrichment
from app.services import secrets as secrets_service

MATCHING_URL = "https://abr.business.gov.au/json/MatchingNames.aspx"
DETAILS_URL = "https://abr.business.gov.au/json/AbnDetails.aspx"
POSITIVE_TTL_DAYS = 90
NEGATIVE_TTL_DAYS = 30
MAX_CANDIDATES = 5
REQUEST_TIMEOUT = 8

# Merchants whose registered business names are a noisy bag of unrelated
# brands — keep the bank's own merchant string instead of enriching.
SKIP_PREFIXES = ("ORIGIN ENERGY",)


class AbrError(Exception):
    pass


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _get_json(url: str) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "StarBegonia/1.0 (ABN Lookup enrichment)",
        },
    )
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AbrError(f"ABR request failed: {exc}") from exc

    body = body.strip()
    start = body.find("(")
    end = body.rfind(")")
    if start != -1 and end > start:
        body = body[start + 1 : end]
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AbrError("ABR returned an unparseable response") from exc


def _score(name: dict[str, Any]) -> float:
    try:
        return float(name.get("Score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _matching_names(guid: str, merchant: str) -> list[dict[str, Any]]:
    url = (
        MATCHING_URL
        + "?"
        + urlencode({"name": merchant, "maxResults": "20", "guid": guid})
    )
    data = _get_json(url)
    if data.get("Message") and "GUID" in str(data.get("Message")).upper():
        raise AbrError(str(data.get("Message")))
    return data.get("Names") or []


def _abn_details(guid: str, abn: str) -> dict[str, Any]:
    url = DETAILS_URL + "?" + urlencode({"abn": abn, "guid": guid})
    data = _get_json(url)
    if data.get("Message") and "GUID" in str(data.get("Message")).upper():
        raise AbrError(str(data.get("Message")))
    return data


def _cache(key: str, entity_name: str | None, abn: str | None, business_name: str | None, *, negative: bool) -> None:
    now = datetime.utcnow()
    ttl_days = NEGATIVE_TTL_DAYS if negative else POSITIVE_TTL_DAYS
    row = MerchantEnrichment.query.filter_by(lookup_key=key).first()
    if not row:
        row = MerchantEnrichment(lookup_key=key)
        db.session.add(row)
    row.entity_name = entity_name
    row.abn = abn
    row.business_name = business_name
    row.matched_at = now
    row.expires_at = now + timedelta(days=ttl_days)
    db.session.commit()


def enrich_merchant(merchant: str | None, household_id: int) -> str | None:
    """Return the merchant's business name, or None to keep the raw merchant."""
    key = _normalize(merchant)
    if not key:
        return None
    if any(key.startswith(prefix) for prefix in SKIP_PREFIXES):
        return None
    guid = secrets_service.get_secret(household_id, "abr_guid")
    if not guid:
        return None

    cached = MerchantEnrichment.query.filter_by(lookup_key=key).first()
    if cached and cached.expires_at and cached.expires_at > datetime.utcnow():
        return cached.business_name or None

    try:
        names = _matching_names(guid, key)
        names.sort(key=_score, reverse=True)
        for candidate in names[:MAX_CANDIDATES]:
            abn = str(candidate.get("Abn") or "").strip()
            if not abn:
                continue
            details = _abn_details(guid, abn)
            entity_name = str(details.get("EntityName") or "").strip()
            if not entity_name:
                continue
            normalized_entity = _normalize(entity_name)
            if not (
                key.startswith(normalized_entity)
                or normalized_entity.startswith(key)
            ):
                continue
            raw_names = details.get("BusinessName") or []
            if isinstance(raw_names, str):
                raw_names = [raw_names]
            business_names = [
                _normalize(n) for n in raw_names if str(n or "").strip()
            ]
            business_name = business_names[0] if business_names else None
            _cache(key, entity_name, abn, business_name, negative=not business_names)
            return business_name

        _cache(key, None, None, None, negative=True)
        return None
    except AbrError:
        # Transient/configuration error: leave uncached so it can retry later.
        return None


def validate_guid(guid: str | None) -> dict[str, Any]:
    """Probe a GUID with a trivial name search. Raises AbrError when invalid."""
    guid = (guid or "").strip()
    if not guid:
        raise AbrError("GUID is empty")
    data = _get_json(
        MATCHING_URL
        + "?"
        + urlencode({"name": "COLES", "maxResults": "1", "guid": guid})
    )
    message = str(data.get("Message") or "")
    if message and "GUID" in message.upper():
        raise AbrError(message)
    return {"names": len(data.get("Names") or [])}
