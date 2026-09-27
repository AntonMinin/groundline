"""anonymous per-question pipeline metrics, readable across tenants for public averages

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"
USED_JEV = """(
    node_metrics @> '[{"node": "jev_sufficiency"}]'
    OR node_metrics @> '[{"node": "check_grounding"}]'
    OR jsonb_path_exists(node_metrics, '$[*].jev')
)"""


def upgrade() -> None:
    op.create_table(
        "query_metrics",
        sa.Column("id", UUID(as_uuid=True), sa.ForeignKey("query_log.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("jev", sa.Boolean, nullable=False),
        sa.Column("cache_hit", sa.Boolean, nullable=False),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_saved", sa.Integer, nullable=False, server_default="0"),
        sa.Column("node_metrics", JSONB, nullable=False, server_default="[]"),
    )
    op.create_index("ix_query_metrics_created_at", "query_metrics", ["created_at"])
    op.execute("ALTER TABLE query_log NO FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        INSERT INTO query_metrics (id, created_at, jev, cache_hit, tokens_used, tokens_saved, node_metrics)
        SELECT id, created_at, {USED_JEV}, cache_hit, tokens_used, tokens_saved, node_metrics FROM query_log
        """
    )
    op.execute("ALTER TABLE query_log FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON query_metrics TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON query_metrics FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON query_metrics FROM authenticated;
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE query_metrics NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE query_metrics DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("query_metrics")
