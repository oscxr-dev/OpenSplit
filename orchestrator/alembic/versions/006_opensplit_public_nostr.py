"""OpenSplit public transparency + nostr foundation (additive only)

Adds:
  - split_targets.nostr_pubkey (nullable)
  - tenants.public_slug (nullable, unique)
  - tenants.public_transparency_enabled (bool, default false)
  - tenants.public_show_amounts (bool, default true)

No members table, no member_id FK, no backfill. Existing rows are unaffected
(new columns are nullable or carry safe server defaults). Nothing here touches
payment_splits, split rules, or payout behavior.

Revision ID: 006_opensplit_public_nostr
Revises: 005_dashboard_foundation
Create Date: 2026-06-17
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "006_opensplit_public_nostr"
down_revision: str | None = "005_dashboard_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "split_targets",
        sa.Column("nostr_pubkey", sa.String(128), nullable=True),
    )

    op.add_column("tenants", sa.Column("public_slug", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_tenants_public_slug", "tenants", ["public_slug"])
    op.add_column(
        "tenants",
        sa.Column(
            "public_transparency_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "public_show_amounts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "public_show_amounts")
    op.drop_column("tenants", "public_transparency_enabled")
    op.drop_constraint("uq_tenants_public_slug", "tenants", type_="unique")
    op.drop_column("tenants", "public_slug")
    op.drop_column("split_targets", "nostr_pubkey")
