"""entry classification status + confidence

Revision ID: 003
Revises: 002
Create Date: 2026-10-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("entries")}
    indexes = {ix["name"] for ix in inspector.get_indexes("entries")}

    if "classification_status" not in cols:
        op.add_column(
            "entries",
            sa.Column(
                "classification_status",
                sa.String(length=32),
                nullable=False,
                server_default="unclassified",
            ),
        )
    if "category_confidence" not in cols:
        op.add_column(
            "entries",
            sa.Column("category_confidence", sa.Numeric(6, 4), nullable=True),
        )
    if "ix_entries_classification_status" not in indexes:
        op.create_index(
            "ix_entries_classification_status",
            "entries",
            ["classification_status"],
        )
    if "ix_entries_category_id" not in indexes:
        op.create_index("ix_entries_category_id", "entries", ["category_id"])

    op.execute(
        """
        UPDATE entries
        SET classification_status = 'confirmed'
        WHERE category_id IS NOT NULL
          AND category_id <> ''
          AND classification_status = 'unclassified'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("entries")}
    indexes = {ix["name"] for ix in inspector.get_indexes("entries")}

    if "ix_entries_category_id" in indexes:
        op.drop_index("ix_entries_category_id", table_name="entries")
    if "ix_entries_classification_status" in indexes:
        op.drop_index("ix_entries_classification_status", table_name="entries")
    if "category_confidence" in cols:
        op.drop_column("entries", "category_confidence")
    if "classification_status" in cols:
        op.drop_column("entries", "classification_status")
