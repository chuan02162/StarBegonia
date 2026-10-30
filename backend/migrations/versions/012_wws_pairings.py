"""Add one-time Woolworths credential pairing codes.

Revision ID: 012
Revises: 011
Create Date: 2026-10-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wws_pairings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code_hash", name="uq_wws_pairings_code_hash"),
    )
    op.create_index("ix_wws_pairings_user_id", "wws_pairings", ["user_id"])
    op.create_index("ix_wws_pairings_person_id", "wws_pairings", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_wws_pairings_person_id", table_name="wws_pairings")
    op.drop_index("ix_wws_pairings_user_id", table_name="wws_pairings")
    op.drop_table("wws_pairings")

