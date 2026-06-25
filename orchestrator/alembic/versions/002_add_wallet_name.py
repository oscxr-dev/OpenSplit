"""add lnbits_wallet_name to split_targets

Revision ID: 002_add_wallet_name
Revises: 001_initial
Create Date: 2026-05-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_add_wallet_name"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "split_targets",
        sa.Column("lnbits_wallet_name", sa.String(100), nullable=True),
    )
    # Backfill: copy label into lnbits_wallet_name for existing rows
    op.execute(
        "UPDATE split_targets SET lnbits_wallet_name = label WHERE lnbits_wallet_name IS NULL"
    )
    # Make NOT NULL after backfill
    op.alter_column("split_targets", "lnbits_wallet_name", nullable=False)


def downgrade() -> None:
    op.drop_column("split_targets", "lnbits_wallet_name")
