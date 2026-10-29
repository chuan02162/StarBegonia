"""dedup_links + bills.dedup_primary_id

Revision ID: 007
Revises: 006
Create Date: 2026-10-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "dedup_links" not in tables:
        op.create_table(
            "dedup_links",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("household_id", sa.Integer(), nullable=False),
            sa.Column("primary_bill_id", sa.Integer(), nullable=False),
            sa.Column("secondary_bill_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("score", sa.Numeric(6, 4), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
            sa.ForeignKeyConstraint(["primary_bill_id"], ["bills.id"]),
            sa.ForeignKeyConstraint(["secondary_bill_id"], ["bills.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "primary_bill_id",
                "secondary_bill_id",
                name="uq_dedup_primary_secondary",
            ),
        )
        op.create_index("ix_dedup_links_household_id", "dedup_links", ["household_id"])
        op.create_index("ix_dedup_links_status", "dedup_links", ["status"])

    bill_cols = {c["name"] for c in inspector.get_columns("bills")}
    if "dedup_primary_id" not in bill_cols:
        op.add_column(
            "bills",
            sa.Column("dedup_primary_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_bills_dedup_primary_id",
            "bills",
            "bills",
            ["dedup_primary_id"],
            ["id"],
        )
        op.create_index("ix_bills_dedup_primary_id", "bills", ["dedup_primary_id"])

    bill_indexes = {i["name"] for i in inspector.get_indexes("bills")}
    if "ix_bills_dedup_status" not in bill_indexes:
        op.create_index("ix_bills_dedup_status", "bills", ["dedup_status"])


def downgrade() -> None:
    op.drop_index("ix_bills_dedup_status", table_name="bills")
    op.drop_index("ix_bills_dedup_primary_id", table_name="bills")
    op.drop_constraint("fk_bills_dedup_primary_id", "bills", type_="foreignkey")
    op.drop_column("bills", "dedup_primary_id")
    op.drop_index("ix_dedup_links_status", table_name="dedup_links")
    op.drop_index("ix_dedup_links_household_id", table_name="dedup_links")
    op.drop_table("dedup_links")
