"""Partial unique index on payments.invoice_id

Enforce uniqueness only WHERE invoice_id IS NOT NULL: invoice_id is nullable
(LNbits payments may not carry one), so a plain unique constraint would reject
all but one null-id row.

Revision ID: 007_payment_invoice_unique
Revises: 006_opensplit_public_nostr
Create Date: 2026-06-24
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "007_payment_invoice_unique"
down_revision: str | None = "006_opensplit_public_nostr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_payments_invoice_id_not_null"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "payments",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("invoice_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="payments")
