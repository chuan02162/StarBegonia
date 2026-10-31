"""Add bills.net_amount (signed total decoupled from line-item signs).

Revision ID: 013
Revises: 012
Create Date: 2026-10-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("net_amount", sa.Numeric(14, 2), nullable=True))
    # Backfill from the current signed entry sums so existing totals are stable.
    op.execute(
        sa.text(
            """
            UPDATE bills b
            SET net_amount = COALESCE(
                (SELECT SUM(e.amount) FROM entries e WHERE e.bill_id = b.id), 0
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("bills", "net_amount")
