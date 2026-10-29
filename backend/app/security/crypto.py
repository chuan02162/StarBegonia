from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet() -> Fernet:
    key = current_app.config.get("CREDENTIAL_FERNET_KEY") or ""
    if not key:
        # Derive a stable-enough key from SECRET_KEY for local/dev only.
        digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_payload(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_payload(token: str) -> dict[str, Any]:
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("invalid credential payload") from exc
    return json.loads(raw.decode("utf-8"))
