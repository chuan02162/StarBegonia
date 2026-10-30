from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _key_from_secret() -> str:
    digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _fernet_keys() -> list[str]:
    """Primary CREDENTIAL_FERNET_KEY, then legacy SECRET_KEY-derived key."""
    keys: list[str] = []
    configured = (current_app.config.get("CREDENTIAL_FERNET_KEY") or "").strip()
    if configured:
        keys.append(configured)
    legacy = _key_from_secret()
    if legacy not in keys:
        keys.append(legacy)
    return keys


def _fernet() -> Fernet:
    return Fernet(_fernet_keys()[0].encode("utf-8"))


def encrypt_payload(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_payload(token: str) -> dict[str, Any]:
    """Decrypt credential blob; accepts current Fernet key or legacy SECRET_KEY key."""
    raw_token = token.encode("utf-8")
    last_exc: Exception | None = None
    for key in _fernet_keys():
        try:
            raw = Fernet(key.encode("utf-8")).decrypt(raw_token)
            return json.loads(raw.decode("utf-8"))
        except InvalidToken as exc:
            last_exc = exc
            continue
    raise ValueError("invalid credential payload") from last_exc
