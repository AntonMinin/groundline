"""background ingest jobs with idempotency keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"


def upgrade() -> None:
    op.create_table(
        "ingest_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_ingest_jobs_idempotency_key",
        "ingest_jobs",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ingest_jobs TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON ingest_jobs FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON ingest_jobs FROM authenticated;
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ingest_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON ingest_jobs
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.drop_table("ingest_jobs")
