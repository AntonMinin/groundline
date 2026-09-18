"""turn row-level security off on tables that are not tenant tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-18
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP_ROLE = "groundline_app"
NON_TENANT_TABLES = ("users", "otp_codes", "service_usage", "alembic_version")


def upgrade() -> None:
    for table in NON_TENANT_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}') THEN
                EXECUTE 'ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY';
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                  EXECUTE 'REVOKE ALL ON public.{table} FROM anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                  EXECUTE 'REVOKE ALL ON public.{table} FROM authenticated';
                END IF;
              END IF;
            END $$;
            """
        )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON public.users TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE, DELETE ON public.otp_codes TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE, DELETE ON public.service_usage TO {APP_ROLE};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    pass
