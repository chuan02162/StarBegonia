"""households.jev_context

Revision ID: 009
Revises: 008
Create Date: 2026-10-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("households")}
    if "jev_context" in cols:
        return
    try:
        op.add_column(
            "households",
            sa.Column("jev_context", sa.Text(), nullable=True),
        )
    except Exception:
        # api/worker may race on first boot; column already present is fine
        bind.rollback()
        inspector = sa.inspect(bind)
        cols = {c["name"] for c in inspector.get_columns("households")}
        if "jev_context" not in cols:
            raise


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("households")}
    if "jev_context" in cols:
        op.drop_column("households", "jev_context")
