"""make BTCPay the default tenant adapter

Revision ID: 008_btcpay_default_adapter
Revises: 007_payment_invoice_unique
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "008_btcpay_default_adapter"
down_revision = "007_payment_invoice_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tenants",
        "adapter_type",
        existing_type=sa.String(length=20),
        server_default="btcpay",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tenants",
        "adapter_type",
        existing_type=sa.String(length=20),
        server_default="lnbits",
        existing_nullable=False,
    )
