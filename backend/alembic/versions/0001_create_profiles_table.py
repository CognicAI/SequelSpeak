"""create profiles table

Revision ID: 0001
Revises:
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard against pre-existing databases where the table was created by
    # SQLModel.metadata.create_all() before Alembic was introduced.
    bind = op.get_bind()
    if "profiles" in inspect(bind).get_table_names():
        return

    op.create_table(
        "profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("database", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")
