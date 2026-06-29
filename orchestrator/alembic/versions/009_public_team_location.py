"""optional public team location (country / city) for the Public Teams map

Privacy: these are coarse, opt-in, public-facing location labels only. No
precise address or coordinates are stored. NULL means "Unknown location".

Revision ID: 009_public_team_location
Revises: 008_btcpay_default_adapter
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "009_public_team_location"
down_revision = "008_btcpay_default_adapter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("public_country", sa.String(length=80), nullable=True))
    op.add_column("tenants", sa.Column("public_city", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "public_city")
    op.drop_column("tenants", "public_country")
