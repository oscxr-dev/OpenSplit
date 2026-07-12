"""Per-relay Nostr publish results

Adds payments.nostr_relay_results: compact JSON array of per-relay publish
outcomes ({relay, ok, at, error?}) for this payment's signed proof event
(see app/services/nostr_publish.py), refreshed on every (re-)publish attempt.
TEXT like nostr_proof_event: it is our own compact serialization, read back
leniently for display. Nullable, no backfill — NULL means "publish never
attempted". Informational only: publishing is best-effort by design, so no
money logic reads it and relays being down can never affect signing or
payouts.

Revision ID: 019_nostr_relay_results
Revises: 018_nostr_proof
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "019_nostr_relay_results"
down_revision = "018_nostr_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("nostr_relay_results", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "nostr_relay_results")
