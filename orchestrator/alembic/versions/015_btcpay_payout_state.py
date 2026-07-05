"""Raw BTCPay payout state on payment_splits

Adds payment_splits.btcpay_payout_state: BTCPay's verbatim payout state
("AwaitingApproval", "AwaitingPayment", "InProgress", ...) captured on every
reconciliation check. Informational only — the mapped `status` column remains
the source of truth for money logic. Powers the dashboard's "Waiting in
BTCPay" surfacing and the /tenants/me/status payout_delivery check.

Revision ID: 015_btcpay_payout_state
Revises: 014_last_webhook_at
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "015_btcpay_payout_state"
down_revision = "014_last_webhook_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_splits",
        sa.Column("btcpay_payout_state", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_splits", "btcpay_payout_state")
