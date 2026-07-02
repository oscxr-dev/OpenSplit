"""public_show_amounts defaults to false (Public Privacy P1)

The public transparency API must not expose sats amounts by default. This flips
the column default from true to false and backfills every existing tenant to
false — showing amounts becomes an explicit opt-in from here on.

Nothing here touches payments, payment_splits, split rules, or payout behavior.

Revision ID: 012_show_amounts_default_false
Revises: 011_payment_split_remainders
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "012_show_amounts_default_false"
down_revision = "011_payment_split_remainders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tenants",
        "public_show_amounts",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    # Backfill: no existing tenant has explicitly opted in (the flag was never
    # user-editable), so force everyone to the private default.
    op.execute("UPDATE tenants SET public_show_amounts = false")


def downgrade() -> None:
    # Restore the old column default only. The backfill is intentionally not
    # reversed: we cannot know which tenants would have wanted amounts public.
    op.alter_column(
        "tenants",
        "public_show_amounts",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
    )
