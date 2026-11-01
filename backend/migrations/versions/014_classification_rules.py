"""Add user-defined classification rules.

Revision ID: 014
Revises: 013
Create Date: 2026-10-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "classification_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id"),
            nullable=False,
        ),
        sa.Column("category_id", sa.String(64), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("match_field", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_classification_rules_household_id",
        "classification_rules",
        ["household_id"],
    )
    op.create_index(
        "ix_classification_rules_category_id",
        "classification_rules",
        ["category_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_classification_rules_category_id", table_name="classification_rules")
    op.drop_index("ix_classification_rules_household_id", table_name="classification_rules")
    op.drop_table("classification_rules")
