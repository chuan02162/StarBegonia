"""households + memberships + bill.household_id + invite fields

Revision ID: 004
Revises: 003
Create Date: 2026-10-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("owner_person_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "household_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_household_memberships_household_id",
        "household_memberships",
        ["household_id"],
    )
    op.create_index(
        "ix_household_memberships_person_id",
        "household_memberships",
        ["person_id"],
    )
    # At most one active membership per person
    op.create_index(
        "uq_membership_active_person",
        "household_memberships",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
        sqlite_where=sa.text("left_at IS NULL"),
    )

    op.add_column("bills", sa.Column("household_id", sa.Integer(), nullable=True))
    op.create_index("ix_bills_household_id", "bills", ["household_id"])
    op.create_foreign_key(
        "fk_bills_household_id", "bills", "households", ["household_id"], ["id"]
    )

    op.add_column("invites", sa.Column("household_id", sa.Integer(), nullable=True))
    op.add_column("invites", sa.Column("target_email", sa.String(length=255), nullable=True))
    op.add_column(
        "invites",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.create_index("ix_invites_household_id", "invites", ["household_id"])
    op.create_index("ix_invites_target_email", "invites", ["target_email"])
    op.create_foreign_key(
        "fk_invites_household_id",
        "invites",
        "households",
        ["household_id"],
        ["id"],
    )

    # Backfill: one household for earliest person; all people as members; all bills
    conn = op.get_bind()
    people = conn.execute(
        sa.text("SELECT id, display_name FROM people ORDER BY id ASC")
    ).fetchall()
    if people:
        owner_id = people[0][0]
        name = f"{people[0][1]}的家庭"
        conn.execute(
            sa.text(
                "INSERT INTO households (name, owner_person_id, created_at) "
                "VALUES (:name, :owner, NOW())"
            ),
            {"name": name, "owner": owner_id},
        )
        hh = conn.execute(sa.text("SELECT id FROM households ORDER BY id ASC LIMIT 1")).fetchone()
        hh_id = hh[0]
        for i, row in enumerate(people):
            role = "owner" if i == 0 else "member"
            conn.execute(
                sa.text(
                    "INSERT INTO household_memberships "
                    "(household_id, person_id, role, joined_at, left_at) "
                    "VALUES (:hh, :pid, :role, NOW(), NULL)"
                ),
                {"hh": hh_id, "pid": row[0], "role": role},
            )
        conn.execute(
            sa.text("UPDATE bills SET household_id = :hh WHERE household_id IS NULL"),
            {"hh": hh_id},
        )
        conn.execute(
            sa.text(
                "UPDATE invites SET household_id = :hh, status = CASE "
                "WHEN used_at IS NOT NULL THEN 'used' ELSE 'pending' END "
                "WHERE household_id IS NULL"
            ),
            {"hh": hh_id},
        )


def downgrade() -> None:
    op.drop_constraint("fk_invites_household_id", "invites", type_="foreignkey")
    op.drop_index("ix_invites_target_email", table_name="invites")
    op.drop_index("ix_invites_household_id", table_name="invites")
    op.drop_column("invites", "status")
    op.drop_column("invites", "target_email")
    op.drop_column("invites", "household_id")

    op.drop_constraint("fk_bills_household_id", "bills", type_="foreignkey")
    op.drop_index("ix_bills_household_id", table_name="bills")
    op.drop_column("bills", "household_id")

    op.drop_index("uq_membership_active_person", table_name="household_memberships")
    op.drop_index("ix_household_memberships_person_id", table_name="household_memberships")
    op.drop_index("ix_household_memberships_household_id", table_name="household_memberships")
    op.drop_table("household_memberships")
    op.drop_table("households")
