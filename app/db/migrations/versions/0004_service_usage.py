"""usage counters for external service limits

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"


def upgrade() -> None:
    op.create_table(
        "service_usage",
        sa.Column("quota_key", sa.String(200), primary_key=True),
        sa.Column("period_start", sa.Date, primary_key=True),
        sa.Column("used", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON service_usage TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON service_usage FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON service_usage FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("service_usage")
