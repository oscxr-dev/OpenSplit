"""add btcpay fields + adapter_type to tenants

Revision ID: 004_tenant_btcpay
Revises: 003_add_ln_address
Create Date: 2026-06-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_tenant_btcpay"
down_revision: str | None = "003_add_ln_address"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # adapter_type: which backend this tenant uses ("lnbits" | "btcpay")
    op.add_column(
        "tenants",
        sa.Column("adapter_type", sa.String(20), nullable=False, server_default="lnbits"),
    )
    # BTCPay connection fields (null for lnbits tenants)
    op.add_column("tenants", sa.Column("btcpay_url", sa.String(512), nullable=True))
    op.add_column("tenants", sa.Column("btcpay_api_key", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("btcpay_store_id", sa.String(64), nullable=True))
    op.add_column("tenants", sa.Column("btcpay_webhook_secret", sa.Text(), nullable=True))
    # LNbits fields become optional (null for btcpay tenants)
    op.alter_column("tenants", "lnbits_admin_key", nullable=True)
    op.alter_column("tenants", "lnbits_url", nullable=True)


def downgrade() -> None:
    op.drop_column("tenants", "btcpay_webhook_secret")
    op.drop_column("tenants", "btcpay_store_id")
    op.drop_column("tenants", "btcpay_api_key")
    op.drop_column("tenants", "btcpay_url")
    op.drop_column("tenants", "adapter_type")
    op.alter_column("tenants", "lnbits_admin_key", nullable=False)
    op.alter_column("tenants", "lnbits_url", nullable=False)
