"""record which version of the terms a user accepted, and when

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("terms_version", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
