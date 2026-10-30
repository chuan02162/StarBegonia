"""Use CommBank as the source type for the OpenFeed bank connection.

Revision ID: 011
Revises: 010
Create Date: 2026-10-30

The retired BankSync CommBank feed is deliberately discarded. OpenFeed
credentials and bills are moved to the CommBank source type.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_COMMBANK_IDS = "SELECT id FROM bills WHERE source_type = 'commbank'"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            DELETE FROM dedup_links
            WHERE primary_bill_id IN ({_OLD_COMMBANK_IDS})
               OR secondary_bill_id IN ({_OLD_COMMBANK_IDS})
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            DELETE FROM internal_transfer_links
            WHERE outgoing_bill_id IN ({_OLD_COMMBANK_IDS})
               OR incoming_bill_id IN ({_OLD_COMMBANK_IDS})
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE bills SET dedup_primary_id = NULL
            WHERE dedup_primary_id IN ({_OLD_COMMBANK_IDS})
            """
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM entries WHERE bill_id IN ({_OLD_COMMBANK_IDS})"
        )
    )
    bind.execute(sa.text("DELETE FROM bills WHERE source_type = 'commbank'"))
    bind.execute(sa.text("DELETE FROM source_credentials WHERE source_type = 'commbank'"))
    bind.execute(
        sa.text(
            """
            UPDATE source_credentials
            SET source_type = 'commbank', label = 'CommBank'
            WHERE source_type = 'openfeed'
            """
        )
    )
    bind.execute(
        sa.text(
            "UPDATE bills SET source_type = 'commbank' WHERE source_type = 'openfeed'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE source_credentials
            SET source_type = 'openfeed', label = 'OpenFeed'
            WHERE source_type = 'commbank'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE bills SET source_type = 'openfeed'
            WHERE source_type = 'commbank' AND external_id LIKE 'openfeed:%'
            """
        )
    )
