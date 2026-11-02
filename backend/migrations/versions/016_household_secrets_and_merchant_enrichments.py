"""Add household secrets and ABR merchant enrichment cache.

Revision ID: 016
Revises: 015
Create Date: 2026-11-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "household_secrets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "key", name="uq_household_secret_key"),
    )
    op.create_index(
        "ix_household_secrets_household_id", "household_secrets", ["household_id"]
    )

    op.create_table(
        "merchant_enrichments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lookup_key", sa.String(length=255), nullable=False),
        sa.Column("entity_name", sa.String(length=255), nullable=True),
        sa.Column("abn", sa.String(length=32), nullable=True),
        sa.Column("business_name", sa.Text(), nullable=True),
        sa.Column(
            "matched_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_merchant_enrichments_lookup_key",
        "merchant_enrichments",
        ["lookup_key"],
        unique=True,
    )
    op.create_index(
        "ix_merchant_enrichments_expires_at", "merchant_enrichments", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_merchant_enrichments_expires_at", table_name="merchant_enrichments")
    op.drop_index("ix_merchant_enrichments_lookup_key", table_name="merchant_enrichments")
    op.drop_table("merchant_enrichments")
    op.drop_index("ix_household_secrets_household_id", table_name="household_secrets")
    op.drop_table("household_secrets")
