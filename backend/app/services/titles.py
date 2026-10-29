"""Prefer human bank titles over BankSync placeholder descriptions."""

from __future__ import annotations

GENERIC_TITLES = frozenset(
    {
        "",
        "general",
        "purchase",
        "payment",
        "transfer",
        "transaction",
        "bank transaction",
    }
)


def is_generic_title(value: str | None) -> bool:
    return (value or "").strip().lower() in GENERIC_TITLES


def best_title(*candidates: object, fallback: str = "Bank transaction") -> str:
    for c in candidates:
        s = str(c or "").strip()
        if s and not is_generic_title(s):
            return s
    for c in candidates:
        s = str(c or "").strip()
        if s:
            return s
    return fallback
