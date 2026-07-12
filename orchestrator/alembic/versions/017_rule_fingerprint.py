"""Rule fingerprint on payments

Adds payments.rule_fingerprint: the hex SHA-256 of the canonical serialization
of the split rule frozen for this payment (see app/services/proof_hash.py for
the exact contract). Captured in the same commit that sets split_rule_id at
split execution / claim time and stored verbatim — never recomputed from the
rule tables later. Nullable: payments settled before this column existed stay
NULL (no backfill). Informational only — no money logic reads it.

Revision ID: 017_rule_fingerprint
Revises: 016_ln_settlement_proof
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "017_rule_fingerprint"
down_revision = "016_ln_settlement_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("rule_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "rule_fingerprint")
