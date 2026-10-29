"""m0 m1 initial schema

Revision ID: 001
Revises:
Create Date: 2026-10-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("created_by_person_id", sa.Integer(), nullable=False),
        sa.Column("display_name_hint", sa.String(length=120), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invites_code", "invites", ["code"], unique=True)

    op.create_table(
        "source_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("payload_encrypted", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "source_type", name="uq_person_source"),
    )

    op.create_table(
        "bills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("dedup_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "external_id", name="uq_source_external"),
    )
    op.create_index("ix_bills_source_type", "bills", ["source_type"])
    op.create_index("ix_bills_occurred_at", "bills", ["occurred_at"])

    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("discount", sa.Numeric(12, 4), nullable=False),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("category_id", sa.String(length=64), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entries_bill_id", "entries", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_entries_bill_id", table_name="entries")
    op.drop_table("entries")
    op.drop_index("ix_bills_occurred_at", table_name="bills")
    op.drop_index("ix_bills_source_type", table_name="bills")
    op.drop_table("bills")
    op.drop_table("source_credentials")
    op.drop_index("ix_invites_code", table_name="invites")
    op.drop_table("invites")
    op.drop_table("people")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
