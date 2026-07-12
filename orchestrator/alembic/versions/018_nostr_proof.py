"""Nostr-signed split proof

Adds:
  - tenants.nostr_pubkey: the team's Nostr PUBLIC key (x-only, lowercase
    64-hex) that signed proofs verify against. Public key only, by design —
    the signing (private) key lives exclusively in the ORCHESTRATOR_NOSTR_SECKEY
    environment variable and must never get a column.
  - payments.nostr_proof_event: verbatim JSON of the team-signed Nostr event
    (kind 2718, see app/services/nostr_proof.py for the bundle contract).
    TEXT on purpose: JSONB re-serialization could reorder keys and break the
    NIP-01 event-id check — the stored bytes are the proof.

Both nullable, no backfill: existing rows are untouched and payments signed
later get the column stamped at sign time. Informational only — no money
logic reads either column.

Revision ID: 018_nostr_proof
Revises: 017_rule_fingerprint
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "018_nostr_proof"
down_revision = "017_rule_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("nostr_pubkey", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("nostr_proof_event", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "nostr_proof_event")
    op.drop_column("tenants", "nostr_pubkey")
