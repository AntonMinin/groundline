"""a role per user, so evaluation accounts can lift the per-user model budget

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.Text, nullable=False, server_default="user"))
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'eval', 'admin')")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
