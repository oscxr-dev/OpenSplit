"""Exactly one active split rule per tenant

The split engine has always paid with a single rule — the newest active one
(highest version, then latest created_at) — while the API allowed several rules
to be flagged active at once, so the extra "active" rules were display-only and
misleading about money routing. This migration makes the invariant real:

1. Deactivate every active rule except the one the engine already picks, per
   tenant. Selection mirrors the engine's ordering exactly (version DESC,
   created_at DESC), so payment processing behavior does not change.
2. Add a partial unique index so the database rejects a second active rule.

Nothing here touches payments, payment_splits, webhooks, or payout behavior.

Revision ID: 013_single_active_rule
Revises: 012_show_amounts_default_false
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "013_single_active_rule"
down_revision = "012_show_amounts_default_false"
branch_labels = None
depends_on = None

# Keeps, per tenant, only the active rule the split engine already selects
# (version DESC, created_at DESC — id DESC is a determinism tie-break for the
# practically impossible case of identical version and timestamp).
DEDUPE_ACTIVE_RULES_SQL = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY tenant_id
               ORDER BY version DESC, created_at DESC, id DESC
           ) AS rn
    FROM split_rules
    WHERE active
)
UPDATE split_rules
SET active = false
WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
"""


def upgrade() -> None:
    op.execute(DEDUPE_ACTIVE_RULES_SQL)
    op.create_index(
        "uq_split_rules_one_active_per_tenant",
        "split_rules",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    # Drop the constraint only. The deactivation is intentionally not reversed:
    # the surviving rule is the one that was processing payments all along, so
    # restoring the extra "active" flags would only restore the ambiguity.
    op.drop_index("uq_split_rules_one_active_per_tenant", table_name="split_rules")
