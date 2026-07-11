"""Lightning settlement proof on payment_splits

Adds payment_splits.ln_preimage and payment_splits.ln_payment_hash: the
Lightning payment preimage (and its hash) that BTCPay exposes on a payout's
paymentProof once it completes. The preimage is cryptographic evidence the
payment settled — sha256(preimage) == payment_hash — verifiable without
trusting this database. Stored verbatim, nullable: on-chain, failed, and
pre-existing payouts simply stay NULL. Informational only — no money logic
reads these columns.

Revision ID: 016_ln_settlement_proof
Revises: 015_btcpay_payout_state
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "016_ln_settlement_proof"
down_revision = "015_btcpay_payout_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_splits",
        sa.Column("ln_preimage", sa.Text(), nullable=True),
    )
    op.add_column(
        "payment_splits",
        sa.Column("ln_payment_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_splits", "ln_payment_hash")
    op.drop_column("payment_splits", "ln_preimage")
