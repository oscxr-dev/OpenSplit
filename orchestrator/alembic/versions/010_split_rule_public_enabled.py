"""public visibility flag for split rules

Revision ID: 010_split_rule_public_enabled
Revises: 009_public_team_location
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "010_split_rule_public_enabled"
down_revision = "009_public_team_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "split_rules",
        sa.Column(
            "public_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("split_rules", "public_enabled")
