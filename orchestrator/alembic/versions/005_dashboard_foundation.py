"""dashboard foundation: payout reconciliation, reporting, branding, rule versions

Revision ID: 005_dashboard_foundation
Revises: 004_tenant_btcpay
Create Date: 2026-06-07
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_dashboard_foundation"
down_revision: str | None = "004_tenant_btcpay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payment_splits", sa.Column("btcpay_payout_id", sa.String(128), nullable=True))
    op.add_column("payment_splits", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column(
        "payment_splits",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "payment_splits",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_splits",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("UPDATE payment_splits SET status = 'in_progress' WHERE status = 'executed'")

    op.add_column(
        "split_rules",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "split_rules",
        sa.Column(
            "parent_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("split_rules.id"),
            nullable=True,
        ),
    )

    op.add_column("payments", sa.Column("fiat_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column("payments", sa.Column("fiat_currency", sa.String(3), nullable=True))
    op.add_column(
        "payments",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("tenants", sa.Column("brand_display_name", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("brand_color", sa.String(7), nullable=True))
    op.add_column("tenants", sa.Column("brand_logo_url", sa.String(1024), nullable=True))
    op.add_column("tenants", sa.Column("notify_email", sa.String(320), nullable=True))
    op.add_column("tenants", sa.Column("notify_telegram_chat_id", sa.String(128), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "alert_on_failed_payout",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "users",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE users SET role = 'owner' WHERE role = 'admin'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'owner'")
    op.drop_column("users", "active")
    op.drop_column("tenants", "alert_on_failed_payout")
    op.drop_column("tenants", "notify_telegram_chat_id")
    op.drop_column("tenants", "notify_email")
    op.drop_column("tenants", "brand_logo_url")
    op.drop_column("tenants", "brand_color")
    op.drop_column("tenants", "brand_display_name")
    op.drop_column("payments", "updated_at")
    op.drop_column("payments", "fiat_currency")
    op.drop_column("payments", "fiat_amount")
    op.drop_column("split_rules", "parent_rule_id")
    op.drop_column("split_rules", "version")
    op.execute("UPDATE payment_splits SET status = 'executed' WHERE status = 'in_progress'")
    op.drop_column("payment_splits", "updated_at")
    op.drop_column("payment_splits", "last_checked_at")
    op.drop_column("payment_splits", "retry_count")
    op.drop_column("payment_splits", "failure_reason")
    op.drop_column("payment_splits", "btcpay_payout_id")
