"""initial schema with row level security

Revision ID: 0001
Revises:
Create Date: 2026-09-15
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024
APP_ROLE = "groundline_app"
TENANT_TABLES = ("documents", "chunks", "query_cache", "query_log")


def _id():
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _user_id():
    return sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


def _created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        _created_at(),
    )
    op.create_table(
        "otp_codes",
        _id(),
        sa.Column("email", sa.String(320), nullable=False, index=True),
        sa.Column("ip", sa.String(64), nullable=True, index=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
        _created_at(),
    )
    op.create_table(
        "documents",
        _id(),
        _user_id(),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_table(
        "chunks",
        _id(),
        _user_id(),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("tsv", TSVECTOR, sa.Computed("to_tsvector('simple', content)", persisted=True)),
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunks_embedding", "chunks", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}
    )
    op.create_table(
        "query_cache",
        _id(),
        _user_id(),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("question_embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_index(
        "ix_query_cache_embedding",
        "query_cache",
        ["question_embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"question_embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "query_log",
        _id(),
        _user_id(),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_saved", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
    )

    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT USAGE ON SCHEMA public TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
          END IF;
        END $$;
        """
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in ("query_log", "query_cache", "chunks", "documents", "otp_codes", "users"):
        op.drop_table(table)
