"""add login rate limits

Revision ID: a8f1d2c3e4b5
Revises: f5f051fc9433
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8f1d2c3e4b5"
down_revision: str | None = "f5f051fc9433"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("subject_digest", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("subject_digest", "window_start"),
    )


def downgrade() -> None:
    op.drop_table("login_rate_limits")
