"""track split allocation remainders

Revision ID: 011_payment_split_remainders
Revises: 010_split_rule_public_enabled
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "011_payment_split_remainders"
down_revision = "010_split_rule_public_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("unallocated_store_sats", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "payments",
        sa.Column("pending_remainder_sats", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("payments", "pending_remainder_sats")
    op.drop_column("payments", "unallocated_store_sats")
