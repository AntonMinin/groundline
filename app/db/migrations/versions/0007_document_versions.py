"""a per-user version of the document set, so a stale answer is never cached

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO document_versions (user_id, version) SELECT id, 0 FROM users")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON document_versions TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON document_versions FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON document_versions FROM authenticated;
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON document_versions
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.drop_table("document_versions")
