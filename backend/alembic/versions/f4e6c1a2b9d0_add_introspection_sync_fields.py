"""add introspection sync fields

Revision ID: f4e6c1a2b9d0
Revises: 2ba5f4035e09
Create Date: 2026-09-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f4e6c1a2b9d0"
down_revision: Union[str, Sequence[str], None] = "2ba5f4035e09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("connections", sa.Column("last_sync_error", sa.Text(), nullable=True))
    op.add_column(
        "connections",
        sa.Column("allowed_schemas", postgresql.JSONB(), nullable=False, server_default='["public"]'),
    )
    op.add_column("schema_columns", sa.Column("sensitive_override", sa.Boolean(), nullable=True))
    op.create_table(
        "schema_indexes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("table_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["table_id"], ["schema_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schema_indexes_table_id", "schema_indexes", ["table_id"], unique=False)
    op.create_index("ix_schema_indexes_table_name", "schema_indexes", ["table_id", "name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_schema_indexes_table_name", table_name="schema_indexes")
    op.drop_index("ix_schema_indexes_table_id", table_name="schema_indexes")
    op.drop_table("schema_indexes")
    op.drop_column("schema_columns", "sensitive_override")
    op.drop_column("connections", "allowed_schemas")
    op.drop_column("connections", "last_sync_error")
