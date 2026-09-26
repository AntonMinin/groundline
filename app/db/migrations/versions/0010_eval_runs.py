"""progress of evaluation runs, kept apart from user data

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON eval_runs TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON eval_runs FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON eval_runs FROM authenticated;
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE eval_runs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_runs DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("eval_runs")
