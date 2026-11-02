"""Encrypted per-household API keys (ABR GUID, Jev API key, …)."""

from __future__ import annotations

from app.extensions import db
from app.models import HouseholdSecret
from app.security.crypto import decrypt_payload, encrypt_payload


def get_secret(household_id: int, key: str) -> str | None:
    row = HouseholdSecret.query.filter_by(
        household_id=household_id, key=key
    ).first()
    if not row:
        return None
    try:
        data = decrypt_payload(row.value_encrypted)
    except Exception:  # noqa: BLE001 - corrupt/legacy value → treat as unset
        return None
    value = str(data.get("value") or "").strip()
    return value or None


def set_secret(household_id: int, key: str, value: str | None) -> None:
    value = (value or "").strip()
    row = HouseholdSecret.query.filter_by(
        household_id=household_id, key=key
    ).first()
    if not value:
        if row:
            db.session.delete(row)
            db.session.commit()
        return
    if not row:
        row = HouseholdSecret(household_id=household_id, key=key)
        db.session.add(row)
    row.value_encrypted = encrypt_payload({"value": value})
    db.session.commit()


def configured_keys(household_id: int) -> dict[str, bool]:
    rows = HouseholdSecret.query.filter_by(household_id=household_id).all()
    return {row.key: bool(row.value_encrypted) for row in rows}
