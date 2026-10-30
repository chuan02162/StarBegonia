"""Backfill entry.amount to signed polarity (in +, out -).

Revision ID: 010
Revises: 009
Create Date: 2026-10-30

Previously bank/Coles amounts were stored as absolute values and income was
inferred from category_id. Going forward amount sign is authoritative.
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INCOME_CATS = {"salary", "interest", "income", "income_other"}
_IN_TYPES = {
    "TRANSFER_INCOMING",
    "INTEREST_PAID",
    "CREDIT",
    "DEPOSIT",
}
_OUT_TYPES = {
    "TRANSFER_OUTGOING",
    "PAYMENT",
    "DEBIT",
    "WITHDRAWAL",
}
_TYPE_RE = re.compile(r"(?:^|;\s*)type=([A-Za-z0-9_]+)", re.I)
_BS_RE = re.compile(r"(?:^|;\s*)banksync_category=([A-Za-z0-9_]+)", re.I)


def _is_credit(note: str | None, category_id: str | None, amount) -> bool:
    """Decide whether an abs-stored row should become a positive (money-in)."""
    note = note or ""
    m = _TYPE_RE.search(note)
    txn_type = m.group(1).upper() if m else ""
    if txn_type in _IN_TYPES:
        return True
    if txn_type in _OUT_TYPES:
        return False
    bs = _BS_RE.search(note)
    if bs and bs.group(1).upper() == "INCOME":
        return True
    if category_id in _INCOME_CATS:
        return True
    # Already-negative rows (e.g. old Flybuys discount) are credits under new model
    try:
        if amount is not None and float(amount) < 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT e.id, e.amount, e.category_id, b.note, b.source_type
            FROM entries e
            JOIN bills b ON b.id = e.bill_id
            """
        )
    ).fetchall()

    for row in rows:
        eid, amount, category_id, note, source_type = row
        if amount is None:
            continue
        try:
            val = float(amount)
        except (TypeError, ValueError):
            continue
        if val == 0:
            continue

        if _is_credit(note, category_id, amount):
            new_val = abs(val)
        else:
            new_val = -abs(val)

        if abs(new_val - val) < 1e-9:
            continue
        bind.execute(
            sa.text("UPDATE entries SET amount = :a WHERE id = :id"),
            {"a": new_val, "id": eid},
        )


def downgrade() -> None:
    # Irreversible without losing sign semantics — restore absolute values.
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE entries SET amount = ABS(amount) WHERE amount < 0"))
