"""add ln_address to split_targets for BTCPay payouts

Revision ID: 003_add_ln_address
Revises: 002_add_wallet_name
Create Date: 2026-06-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_add_ln_address"
down_revision: str | None = "002_add_wallet_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lightning address destination for BTCPay payouts (e.g. barista@walletofsatoshi.com)
    op.add_column(
        "split_targets",
        sa.Column("ln_address", sa.String(255), nullable=True),
    )
    # LNbits wallet fields become optional (not used by BTCPay tenants)
    op.alter_column("split_targets", "lnbits_wallet_id", nullable=True)
    op.alter_column("split_targets", "lnbits_wallet_name", nullable=True)


def downgrade() -> None:
    op.drop_column("split_targets", "ln_address")
    op.alter_column("split_targets", "lnbits_wallet_id", nullable=False)
    op.alter_column("split_targets", "lnbits_wallet_name", nullable=False)
