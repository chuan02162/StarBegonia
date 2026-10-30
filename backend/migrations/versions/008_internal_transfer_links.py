"""internal_transfer_links

Revision ID: 008
Revises: 007
Create Date: 2026-10-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "internal_transfer_links" not in tables:
        op.create_table(
            "internal_transfer_links",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("household_id", sa.Integer(), nullable=False),
            sa.Column("outgoing_bill_id", sa.Integer(), nullable=False),
            sa.Column("incoming_bill_id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("previous_categories", sa.JSON(), nullable=False),
            sa.Column("matched_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
            sa.ForeignKeyConstraint(["outgoing_bill_id"], ["bills.id"]),
            sa.ForeignKeyConstraint(["incoming_bill_id"], ["bills.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "outgoing_bill_id",
                "incoming_bill_id",
                name="uq_internal_transfer_out_in",
            ),
        )
        op.create_index(
            "ix_internal_transfer_links_household_id",
            "internal_transfer_links",
            ["household_id"],
        )
        op.create_index(
            "ix_internal_transfer_links_outgoing_bill_id",
            "internal_transfer_links",
            ["outgoing_bill_id"],
        )
        op.create_index(
            "ix_internal_transfer_links_incoming_bill_id",
            "internal_transfer_links",
            ["incoming_bill_id"],
        )
        op.create_index(
            "ix_internal_transfer_links_reference",
            "internal_transfer_links",
            ["reference"],
        )
        op.create_index(
            "ix_internal_transfer_links_status",
            "internal_transfer_links",
            ["status"],
        )


def downgrade() -> None:
    op.drop_index("ix_internal_transfer_links_status", table_name="internal_transfer_links")
    op.drop_index(
        "ix_internal_transfer_links_reference", table_name="internal_transfer_links"
    )
    op.drop_index(
        "ix_internal_transfer_links_incoming_bill_id",
        table_name="internal_transfer_links",
    )
    op.drop_index(
        "ix_internal_transfer_links_outgoing_bill_id",
        table_name="internal_transfer_links",
    )
    op.drop_index(
        "ix_internal_transfer_links_household_id",
        table_name="internal_transfer_links",
    )
    op.drop_table("internal_transfer_links")
