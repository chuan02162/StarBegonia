from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from flask import current_app


class JevError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def classify_entry_state(
    *,
    name: str,
    amount: str | float | None,
    merchant: str | None,
    source_type: str | None,
    note: str | None,
    categories: list[dict[str, str]],
) -> dict[str, Any]:
    """Call Jev once for category choice. Returns parsed result."""
    api_key = current_app.config.get("JEV_API_KEY") or ""
    if not api_key:
        raise JevError("JEV_API_KEY is not configured", 503)

    criteria = {
        c["id"]: c.get("label") or c["id"] for c in categories if c.get("id")
    }
    if not criteria:
        raise JevError("no categories in vocabulary", 500)

    questions: dict[str, Any] = {
        "category": {
            "type": "choice",
            "instructions": (
                "Classify this household finance line item into exactly one category. "
                "Prefer groceries for food staples from a supermarket; "
                "household for cleaning and non-food essentials; "
                "dining for restaurants/takeaway; other only when nothing else fits."
            ),
            "criteria": criteria,
        }
    }

    state = {
        "name": name,
        "amount": amount,
        "merchant": merchant,
        "source_type": source_type,
        "note": note,
    }
    raw = _post_systemone(state=state, questions=questions)
    return _parse_answers(raw)


def _post_systemone(*, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    url = current_app.config["JEV_API_URL"]
    api_key = current_app.config["JEV_API_KEY"]
    model = current_app.config.get("JEV_MODEL") or "jev-latest"
    body = json.dumps(
        {"state": state, "model": model, "questions": questions}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise JevError(f"Jev HTTP {exc.code}: {detail}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise JevError(f"Jev unreachable: {exc.reason}", 502) from exc
    if not isinstance(payload, dict):
        raise JevError("unexpected Jev response shape", 502)
    return payload


def _parse_answers(payload: dict[str, Any]) -> dict[str, Any]:
    answers = payload.get("answers") or {}
    cat = answers.get("category") or {}
    category_id = cat.get("choice")
    confidence = cat.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_f = None

    return {
        "category_id": category_id,
        "confidence": confidence_f,
        "model": payload.get("model"),
        "raw_answers": answers,
    }
