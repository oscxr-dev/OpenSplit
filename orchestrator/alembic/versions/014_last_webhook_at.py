"""Tenant webhook liveness timestamp

Adds tenants.last_webhook_at: set whenever a SIGNATURE-VALID BTCPay webhook
arrives (any event type), NULL until the first one lands and reset to NULL when
the webhook secret is regenerated. Powers the dashboard's "webhook verified"
indicator in the guided webhook setup.

Revision ID: 014_last_webhook_at
Revises: 013_single_active_rule
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "014_last_webhook_at"
down_revision = "013_single_active_rule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "last_webhook_at")
